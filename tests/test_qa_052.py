"""QA-050-04/05: failed checkpoints, explicit current intent and legacy logs."""

import copy

import pytest

from tutor_ai.dialogue import INTENTS, work_messages
from tutor_ai.errors import AppError
from tests.test_application import family as family_fixture, child_login
from tests.test_learning_050 import approved_bank, command, wait_job

family = family_fixture


@pytest.mark.parametrize("advance,near_cap,expected,status", [
    (30, False, 30, "active"), (181, False, 180, "paused"),
    (30, True, 5, "paused"), (181, True, 5, "paused"),
])
def test_checkpoint_failures_retry_same_interval(family, monkeypatch, advance, near_cap, expected, status):
    app, _, child, clock = family
    state, col = approved_bank(app, child)
    child_login(app, child)
    attempt = command(app, "start", student=child["id"], collection=col,
                      purpose="topic_confirmation", topic=app.learning_engine.topics(state["curriculum"])[0]["id"])["id"]
    baseline = 4495 if near_cap else 0
    if near_cap:
        with app.store.transaction():
            daily = app.daily(child["id"])
            daily["seconds"] = baseline
            app.store.put("daily", child["id"], daily, child["id"])
    runtime = (app.assessment_active, app.last_tick, app.last_action)
    original = app.store.path.read_bytes()
    row = command(app, "attempt", attempt=attempt)
    clock[0] += advance

    def fail():
        raise OSError("synthetic checkpoint failure")

    with monkeypatch.context() as fault:
        fault.setattr(app.store, "save", fail)
        for _ in range(3):
            with pytest.raises(OSError):
                app.tick()
            assert runtime == (app.assessment_active, app.last_tick, app.last_action)
            assert row == command(app, "attempt", attempt=attempt)
            assert app.daily(child["id"])["seconds"] == baseline
            assert app.store.path.read_bytes() == original
        # A failed checkpoint must not allow conflicting homework.
        with pytest.raises(AppError, match="диагностику"):
            app.start_lesson("algebra-equations")
    app.tick()
    after = command(app, "attempt", attempt=attempt)
    assert after["status"] == status and after["body"]["seconds"] == expected
    assert app.daily(child["id"])["seconds"] == baseline + expected
    assert app.last_action == runtime[2]
    app.tick()
    assert command(app, "attempt", attempt=attempt) == after
    assert app.daily(child["id"])["seconds"] == baseline + expected


@pytest.mark.parametrize("intent", INTENTS)
@pytest.mark.parametrize("question", ["", "   ", "Поясни второй шаг"])
def test_actual_sent_intent_and_replay(family, intent, question):
    app, _, child, _ = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, expected_revision=0, value="3x+5=20; 3x=15; x=5", confirm=True)
    args = dict(work=work, expected_revision=1, intent=intent, follow_up=question, operation_id="same-request")
    first = command(app, "work_check", **args)
    assert wait_job(app, first)["status"] == "succeeded"
    assert command(app, "work_check", **args) == first
    calls = app.store.db.execute("SELECT * FROM learning_calls WHERE work=?", (work,)).fetchall()
    assert len(calls) == 1
    body = app.learning_engine.body(calls[0])
    assert body["intent"] == intent
    assert f"Текущее действие (intent): {intent}. {INTENTS[intent]}" in body["messages"][0]["content"]
    assert body["messages"][-1]["content"] == (question.strip() or INTENTS[intent])
    assert app.provider_factory.calls[-1] == body["messages"]
    with pytest.raises(AppError) as error:
        command(app, "work_check", **{**args, "intent": "invalid"})
    assert error.value.code == "conflict"
    with pytest.raises(AppError):
        command(app, "work_check", **{**args, "intent": "invalid", "operation_id": "new"})
    assert len(app.store.db.execute("SELECT * FROM learning_calls WHERE work=?", (work,)).fetchall()) == 1


def test_history_modes_are_provenance_not_current_control():
    calls = [{"source_call": "a2", "purpose": "work_check", "intent": "hint",
              "dialogue_user": "OLD QUESTION", "messages": [], "response": "OLD ANSWER",
              "status": "succeeded", "work_revision": 1}]
    original = copy.deepcopy(calls)
    messages, meta = work_messages("system", "algebra", "solution", 2, "check", "NEW QUESTION", calls)
    assert "Текущее действие (intent): check. Проверь решение." in messages[0]["content"]
    assert "Режим по метаданным прошлого вызова: hint" in messages[2]["content"]
    assert "Историческая версия решения: 1" in messages[2]["content"]
    assert [m["role"] for m in messages] == ["system", "user", "user", "assistant", "user"]
    assert calls == original and meta["intent"] == "check"
    # The trusted instruction is part of the budget, not free overhead.
    size = sum(len(m["content"]) for m in work_messages("", "algebra", "x", 1, "hint", "", [])[0])
    accepted, _ = work_messages("s" * (30000-size), "algebra", "x", 1, "hint", "", [])
    assert sum(len(m["content"]) for m in accepted) == 30000
    with pytest.raises(AppError) as error:
        work_messages("s" * (30001-size), "algebra", "x", 1, "hint", "", [])
    assert error.value.code == "text_limit"
