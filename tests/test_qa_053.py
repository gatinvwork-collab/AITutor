"""QA-050-06: activity belongs to durable acceptance, never polling/results."""

import pytest

from tutor_ai.errors import AppError
from tests.test_application import family as family_fixture, child_login, CHILD_PASSWORD
from tests.test_learning_050 import command, wait_job

family = family_fixture


def setup_work(app, child):
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, value="3x+5=20; 3x=15; x=5", expected_revision=0, confirm=True)
    return work


def ask(app, work, **args):
    return command(app, "work_check", work=work, expected_revision=1, **args)


@pytest.mark.parametrize("modes", [
    ["check"] * 4, ["hint"] * 4, ["follow_up"] * 4, ["check", "hint", "follow_up", "check"],
])
def test_regular_actions_renew_only_one_lesson(family, modes):
    app, _, child, clock = family
    work = setup_work(app, child)
    for advance, mode in zip([0, 60, 60, 61], modes):
        clock[0] += advance
        assert wait_job(app, ask(app, work, intent=mode, follow_up=f"At {clock[0]}"))["status"] == "succeeded"
        assert app.last_action == clock[0]
    lessons = app.store.all("session", child["id"])
    assert len(lessons) == 1 and lessons[0]["status"] == "active" and lessons[0]["seconds"] == 181
    assert app.daily(child["id"])["seconds"] == 181 and app.active_lesson == lessons[0]["id"]


@pytest.mark.parametrize("idle", [179, 180, 181])
def test_true_idle_and_read_only_calls(family, idle):
    app, _, child, clock = family
    work = setup_work(app, child)
    wait_job(app, ask(app, work))
    clock[0] += 60
    accepted = ask(app, work, intent="hint")
    wait_job(app, accepted)
    action = app.last_action
    clock[0] += idle
    app.snapshot()
    command(app, "overview", student=child["id"])
    command(app, "job", job=accepted["job"])
    assert app.last_action == action
    app.tick()
    lesson = app.lesson(app.store.all("session", child["id"])[0]["id"])
    assert lesson["status"] == ("active" if idle == 179 else "paused")
    assert lesson["seconds"] == 60 + min(idle, 180)
    assert app.daily(child["id"])["seconds"] == lesson["seconds"]
    if idle >= 180:
        before = lesson["seconds"]
        clock[0] += 100
        app.tick()
        assert app.lesson(lesson["id"])["seconds"] == before


def test_replay_and_conflicting_operation_are_not_activity(family):
    app, _, child, clock = family
    work = setup_work(app, child)
    first = ask(app, work, operation_id="accepted-once", intent="hint")
    wait_job(app, first)
    original = (app.last_action, app.last_tick)
    clock[0] += 60
    assert ask(app, work, operation_id="accepted-once", intent="hint") == first
    with pytest.raises(AppError) as error:
        ask(app, work, operation_id="accepted-once", intent="check")
    assert error.value.code == "conflict" and original == (app.last_action, app.last_tick)
    assert app.store.db.execute("SELECT count(*) FROM learning_calls").fetchone()[0] == 1


@pytest.mark.parametrize("invalid", ["revision", "intent", "context", "unconfirmed", "consent"])
def test_refusal_does_not_renew_activity(family, monkeypatch, invalid):
    app, _, child, clock = family
    work = setup_work(app, child)
    wait_job(app, ask(app, work))
    action = app.last_action
    clock[0] += 60
    args = dict(work=work, expected_revision=1)
    if invalid == "revision":
        args["expected_revision"] = 0
    elif invalid == "intent":
        args["intent"] = "invalid"
    elif invalid == "context":
        args["follow_up"] = "x" * 30000
    elif invalid == "unconfirmed":
        command(app, "work_revision", work=work, value="new", expected_revision=1, confirm=False)
        args["expected_revision"] = 2
    else:
        def refuse(**_):
            raise AppError("Synthetic consent refusal", "consent_required")
        monkeypatch.setattr(app, "configured", refuse)
    with pytest.raises(AppError):
        command(app, "work_check", **args)
    assert app.last_action == action
    assert app.store.db.execute("SELECT count(*) FROM learning_calls").fetchone()[0] == 1


@pytest.mark.parametrize("write", [1, 2])
def test_failed_checkpoint_or_acceptance_preserves_successful_boundary(family, monkeypatch, write):
    app, _, child, clock = family
    work = setup_work(app, child)
    wait_job(app, ask(app, work))
    lesson = app.active_lesson
    original_action, original_tick = app.last_action, app.last_tick
    clock[0] += 60
    save, writes = app.store.save, [0]

    def fail_once():
        writes[0] += 1
        if writes[0] == write:
            raise OSError("synthetic write refusal")
        return save()

    with monkeypatch.context() as fault:
        fault.setattr(app.store, "save", fail_once)
        with pytest.raises(OSError):
            ask(app, work, operation_id="retry-acceptance")
    assert app.last_action == original_action and app.active_lesson == lesson
    assert app.last_tick == (original_tick if write == 1 else clock[0])
    assert app.lesson(lesson)["seconds"] == (0 if write == 1 else 60)
    assert app.store.db.execute("SELECT count(*) FROM learning_calls").fetchone()[0] == 1
    assert wait_job(app, ask(app, work, operation_id="retry-acceptance"))["status"] == "succeeded"
    assert app.last_action == clock[0] and app.lesson(lesson)["seconds"] == 60
    assert app.daily(child["id"])["seconds"] == 60


def test_initial_acceptance_failure_has_no_orphan_lesson(family, monkeypatch):
    app, _, child, clock = family
    work = setup_work(app, child)
    original = (app.last_tick, app.last_action, app.active_lesson)
    clock[0] += 60
    def fail():
        raise OSError("synthetic write refusal")
    with monkeypatch.context() as fault:
        fault.setattr(app.store, "save", fail)
        with pytest.raises(OSError):
            ask(app, work)
    assert original == (app.last_tick, app.last_action, app.active_lesson)
    assert app.store.all("session", child["id"]) == []
    assert app.store.db.execute("SELECT count(*) FROM learning_jobs").fetchone()[0] == 0


class HeldJobs:
    """Capture network callbacks and release them under controlled clocks."""
    def submit(self, identity, run, publish):
        self.run, self.publish = run, publish


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled", "stale", "logout"])
def test_completion_never_renews_activity(family, monkeypatch, outcome):
    app, _, child, clock = family
    work = setup_work(app, child)
    wait_job(app, ask(app, work))
    held = HeldJobs()
    monkeypatch.setattr(app.network_jobs, "submit", held.submit)
    clock[0] += 60
    job = ask(app, work, intent="hint")
    action = app.last_action
    assert action == clock[0]
    clock[0] += 181
    app.tick()
    assert app.lesson(app.store.all("session", child["id"])[0]["id"])["status"] == "paused"
    if outcome == "stale":
        command(app, "work_revision", work=work, value="new solution", expected_revision=1, confirm=True)
    if outcome == "logout":
        app.logout()
        app.login(child["id"], CHILD_PASSWORD)
    before = (app.last_action, app.last_tick, app.active_lesson)
    held.publish(({"text": "Synthetic answer", "usage": None}, []),
                 "network" if outcome == "failure" else None, outcome == "cancelled")
    assert before == (app.last_action, app.last_tick, app.active_lesson)
    if outcome != "logout":
        assert app.last_action == action
        status = command(app, "job", job=job["job"])["status"]
        assert status == {"success": "succeeded", "failure": "failed", "cancelled": "cancelled", "stale": "stale"}[outcome]


def test_regular_actions_cannot_extend_grace_or_revive_expired_lesson(family):
    app, _, child, clock = family
    work = setup_work(app, child)
    wait_job(app, ask(app, work))
    lesson = app.active_lesson
    with app.store.transaction():
        daily = app.daily(child["id"])
        daily["seconds"] = 4490
        app.store.put("daily", child["id"], daily, child["id"])
    for mode in ("hint", "follow_up"):
        clock[0] += 4
        wait_job(app, ask(app, work, intent=mode))
    action = app.last_action
    clock[0] += 4
    with pytest.raises(AppError) as error:
        ask(app, work)
    assert error.value.code == "time_limit" and app.last_action == action
    assert app.lesson(lesson)["status"] == "paused" and app.lesson(lesson)["seconds"] == 10
    assert app.daily(child["id"])["seconds"] == 4500
    with pytest.raises(AppError):
        ask(app, work)
    assert len(app.store.all("session", child["id"])) == 1


@pytest.mark.parametrize("elapsed", [180, 181])
def test_new_action_cannot_retroactively_cancel_real_idle(family, elapsed):
    app, _, child, clock = family
    work = setup_work(app, child)
    wait_job(app, ask(app, work))
    action = app.last_action
    lesson = app.active_lesson
    clock[0] += elapsed
    with pytest.raises(AppError) as error:
        ask(app, work)
    assert error.value.code == "time_limit" and app.last_action == action
    assert app.lesson(lesson)["status"] == "paused" and app.lesson(lesson)["seconds"] == 180
    assert app.store.db.execute("SELECT count(*) FROM learning_calls").fetchone()[0] == 1
