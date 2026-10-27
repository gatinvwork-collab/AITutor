"""Timer state, commit boundaries and native historical-command regression."""
import copy

import pytest

from tutor_ai.errors import AppError
from tests.test_application import CHILD_PASSWORD, PROFILE, child_login, family as family_fixture

family = family_fixture


@pytest.mark.parametrize("command", ["pause", "complete"])
@pytest.mark.parametrize("old_status", ["paused", "complete"])
def test_historical_commands_leave_running_timer_untouched(family, command, old_status):
    app, _, child, clock = family
    child_login(app, child)
    old = app.start_lesson("math-equations")
    getattr(app, "pause" if old_status == "paused" else "complete")(old["id"])
    current = app.start_lesson("physics-speed")
    markers = app.last_tick, app.last_action
    result = app.dispatch(command, {"session": old["id"]})
    assert app.active_lesson == current["id"] and (app.last_tick, app.last_action) == markers
    repeated = app.dispatch(command, {"session": old["id"]})
    assert repeated == result
    clock[0] += 30
    app.tick()
    assert app.lesson(current["id"])["seconds"] == app.daily(child["id"])["seconds"] == 30


@pytest.mark.parametrize("command", ["pause", "complete"])
def test_invalid_history_target_does_not_affect_running_session(family, command):
    app, parent, child, clock = family
    other = app.register("Другой", CHILD_PASSWORD, "STUDENT", PROFILE)
    child_login(app, other)
    foreign = app.start_lesson("math-equations")
    app.pause(foreign["id"])
    child_login(app, child)
    current = app.start_lesson("math-powers")
    for target in (foreign["id"], "nonexistent"):
        with pytest.raises(AppError):
            app.dispatch(command, {"session": target})
    assert app.active_lesson == current["id"]
    clock[0] += 20
    app.tick()
    assert app.daily(child["id"])["seconds"] == 20


@pytest.mark.parametrize("mode", ["learn", "diagnose", "subject_diagnose"])
def test_failed_final_answer_is_retryable_with_same_operation(family, monkeypatch, mode):
    app, _, child, clock = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations", mode)
    # Subject diagnosis finishes its current queue; isolate the terminal transition.
    if mode == "subject_diagnose":
        with app.store.transaction():
            item = app.lesson(lesson["id"])
            item["topic_queue"] = []
            app.store.put("session", item["id"], item, child["id"])
    for index in range(2):
        current = app.lesson(lesson["id"])
        from tutor_ai.education import topic
        answer = topic(current["topic"])["tasks"][current["index"]][1]
        app.answer(lesson["id"], answer, f"qa032-pre-answer-{index}")
    previous = copy.deepcopy(app.lesson(lesson["id"]))
    previous_knowledge = copy.deepcopy(app.store.all("knowledge"))
    real_save = app.store.save
    def fail_complete():
        if app.lesson(lesson["id"])["status"] == "complete":
            raise OSError("synthetic completion write failure")
        real_save()
    monkeypatch.setattr(app.store, "save", fail_complete)
    answer = "-3"
    operation = "qa032-final-operation"
    with pytest.raises(OSError):
        app.answer(lesson["id"], answer, operation)
    assert app.lesson(lesson["id"]) == previous
    assert app.store.all("knowledge") == previous_knowledge
    assert app.active_lesson == lesson["id"]
    assert app.store.get("operation", child["id"] + ":" + operation) is None
    clock[0] += 20
    app.tick()
    assert app.daily(child["id"])["seconds"] == 20
    monkeypatch.setattr(app.store, "save", real_save)
    saved = app.answer(lesson["id"], answer, operation)
    assert saved["session"]["status"] == "complete" and app.active_lesson is None
    assert app.answer(lesson["id"], answer, operation) == saved
    assert app.store.all("knowledge", child["id"])[0]["attempts_count"] == 3
    assert len(app.store.all("knowledge_event", child["id"])) == 3


@pytest.mark.parametrize("delay,charged,status", [(179, 179, "active"), (180, 180, "paused"),
                                                   (181, 180, "paused"), (600, 180, "paused")])
def test_idle_boundary_is_capped_before_charging(family, delay, charged, status):
    app, _, child, clock = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    clock[0] += delay
    app.tick()
    stored = app.lesson(lesson["id"])
    assert stored["seconds"] == app.daily(child["id"])["seconds"] == charged
    assert stored["status"] == status
    app.tick()
    assert app.daily(child["id"])["seconds"] == charged


def test_regular_ticks_then_delayed_tick_charge_only_until_idle(family):
    app, _, child, clock = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    for _ in range(3):
        clock[0] += 50
        app.tick()
    clock[0] += 450
    app.tick()
    assert app.lesson(lesson["id"])["seconds"] == 180
    assert app.daily(child["id"])["seconds"] == 180


def test_learning_action_extends_idle_but_history_and_snapshot_do_not(family):
    app, _, child, clock = family
    child_login(app, child)
    old = app.start_lesson("math-equations")
    app.pause(old["id"])
    current = app.start_lesson("math-powers")
    clock[0] += 100
    app.hint(current["id"])
    clock[0] += 100
    app.snapshot()
    app.pause(old["id"])
    clock[0] += 500
    app.tick()
    assert app.lesson(current["id"])["seconds"] == 280


def test_failed_checkpoint_preserves_cursor_and_retry_charges_once(family, monkeypatch):
    app, _, child, clock = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    markers = app.last_tick, app.last_action
    clock[0] += 600
    real_save = app.store.save
    monkeypatch.setattr(app.store, "save", lambda: (_ for _ in ()).throw(OSError("synthetic checkpoint failure")))
    with pytest.raises(OSError):
        app.tick()
    assert (app.last_tick, app.last_action) == markers and app.active_lesson == lesson["id"]
    assert app.lesson(lesson["id"])["seconds"] == 0
    monkeypatch.setattr(app.store, "save", real_save)
    app.tick()
    assert app.lesson(lesson["id"])["status"] == "paused"
    assert app.daily(child["id"])["seconds"] == 180
    app.tick()
    assert app.daily(child["id"])["seconds"] == 180


def test_failed_historical_write_preserves_current_timer(family, monkeypatch):
    app, _, child, clock = family
    child_login(app, child)
    old = app.start_lesson("math-equations")
    app.pause(old["id"])
    current = app.start_lesson("physics-speed")
    real_save = app.store.save
    monkeypatch.setattr(app.store, "save", lambda: (_ for _ in ()).throw(OSError("synthetic history failure")))
    with pytest.raises(OSError):
        app.complete(old["id"])
    assert app.active_lesson == current["id"] and app.lesson(old["id"])["status"] == "paused"
    monkeypatch.setattr(app.store, "save", real_save)
    clock[0] += 15
    app.tick()
    assert app.daily(child["id"])["seconds"] == 15


def test_lost_cache_does_not_allow_second_session_and_tick_recovers(family):
    app, _, child, clock = family
    child_login(app, child)
    old = app.start_lesson("math-equations")
    app.pause(old["id"])
    current = app.start_lesson("physics-speed")
    app.active_lesson = None  # models legacy in-memory inconsistency
    with pytest.raises(AppError):
        app.start_lesson("math-powers")
    with pytest.raises(AppError):
        app.resume(old["id"])
    clock[0] += 20
    app.tick()
    assert app.active_lesson == current["id"] and app.daily(child["id"])["seconds"] == 20


def test_less_remaining_grace_wins_over_idle_boundary(family):
    app, _, child, clock = family
    app.set_controls(child["id"], 5)
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    with app.store.transaction():
        daily = app.daily(child["id"])
        daily["seconds"] = 1190
        app.store.put("daily", child["id"], daily, child["id"])
    clock[0] += 600
    app.tick()
    assert app.daily(child["id"])["seconds"] == 1200
    assert app.lesson(lesson["id"])["seconds"] == 10
    with pytest.raises(AppError):
        app.resume(lesson["id"])


def test_failed_answer_does_not_renew_idle_forever(family, monkeypatch):
    app, _, child, clock = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    real_save = app.store.save
    def fail_answer():
        if app.lesson(lesson["id"])["total"]:
            raise OSError("synthetic answer failure")
        real_save()
    monkeypatch.setattr(app.store, "save", fail_answer)
    clock[0] += 100
    with pytest.raises(OSError):
        app.answer(lesson["id"], "5", "qa032-failed-answer")
    clock[0] += 100
    app.tick()
    assert app.lesson(lesson["id"])["status"] == "paused"
    assert app.daily(child["id"])["seconds"] == 180


def test_restart_after_failed_completion_preserves_history_and_pauses(family, monkeypatch):
    app, parent, child, clock = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    app.answer(lesson["id"], "5", "qa032-restart-first")
    app.answer(lesson["id"], "4", "qa032-restart-second")
    real_save = app.store.save
    def fail_final():
        if app.lesson(lesson["id"])["status"] == "complete":
            raise OSError("synthetic final failure")
        real_save()
    monkeypatch.setattr(app.store, "save", fail_final)
    with pytest.raises(OSError):
        app.answer(lesson["id"], "-3", "qa032-restart-final")
    before = copy.deepcopy(app.store.all("knowledge"))
    app.store.close()  # abrupt process closure, no logout
    app.actor = None
    monkeypatch.setattr(app.store, "save", real_save)
    clock[0] += 3600
    app.login(child["id"], CHILD_PASSWORD)
    assert app.lesson(lesson["id"])["status"] == "paused" and app.active_lesson is None
    assert app.store.all("knowledge") == before
    assert app.daily(child["id"])["seconds"] == 0
    app.resume(lesson["id"])
    clock[0] += 10
    app.tick()
    assert app.daily(child["id"])["seconds"] == 10
