"""Acceptance regressions for QA-050-01/02/03 (native part)."""

import copy
import json

import pytest

from tutor_ai.dialogue import work_messages
from tutor_ai.errors import AppError
from tests.test_application import family as family_fixture, child_login
from tests.test_learning_050 import approved_bank, command, wait_job, finish_answers

family = family_fixture


def two_attempts(app, child):
    state, col = approved_bank(app, child)
    child_login(app, child)
    aid = finish_answers(app, child, col, state)
    # Deliberately construct the ready paused state, without changing its answers.
    with app.store.transaction():
        app.store.db.execute("UPDATE learning_attempts SET status='paused' WHERE id=?", (aid,))
    bid = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )["id"]
    return aid, bid


@pytest.mark.parametrize("advance", [30, 179, 181])
def test_historical_finish_does_not_renew_idle(family, advance):
    app, _, child, clock = family
    a, b = two_attempts(app, child)
    original_action = app.last_action
    clock[0] += 10
    view = command(app, "attempt", attempt=a)
    command(app, "finish", attempt=a, expected_revision=view["revision"], operation_id="finish-old")
    assert app.assessment_active == b and app.last_action == original_action
    clock[0] += advance
    app.tick()
    after = command(app, "attempt", attempt=b)
    assert after["body"]["seconds"] == min(180, 10 + advance)
    assert app.daily(child["id"])["seconds"] == after["body"]["seconds"]
    assert after["status"] == ("paused" if 10 + advance >= 180 else "active")


def test_finish_failure_and_replay_preserve_other_runtime(family, monkeypatch):
    app, _, child, clock = family
    a, b = two_attempts(app, child)
    view = command(app, "attempt", attempt=a)
    args = dict(attempt=a, expected_revision=view["revision"], operation_id="atomic-finish")
    original = app.store.save
    writes = [0]

    def fail_mutation():
        writes[0] += 1
        if writes[0] == 2:
            raise OSError("synthetic write failure")
        return original()

    monkeypatch.setattr(app.store, "save", fail_mutation)
    with pytest.raises(OSError):
        command(app, "finish", **args)
    assert app.assessment_active == b and command(app, "attempt", attempt=a)["status"] == "paused"
    monkeypatch.setattr(app.store, "save", original)
    result = command(app, "finish", **args)
    stamp = (app.last_tick, app.last_action)
    assert command(app, "finish", **args) == result and stamp == (app.last_tick, app.last_action)
    assert app.assessment_active == b
    clock[0] += 30
    app.tick()
    assert command(app, "attempt", attempt=b)["body"]["seconds"] == 30


def test_finish_old_near_grace_limit_preserves_cap(family):
    app, _, child, clock = family
    a, b = two_attempts(app, child)
    with app.store.transaction():
        daily = app.daily(child["id"])
        daily["seconds"] = 60 * 60 + 895
        app.store.put("daily", child["id"], daily, child["id"])
    command(app, "finish", attempt=a, expected_revision=command(app, "attempt", attempt=a)["revision"])
    clock[0] += 30
    app.tick()
    assert command(app, "attempt", attempt=b)["body"]["seconds"] == 5
    assert command(app, "attempt", attempt=b)["status"] == "paused"
    assert app.daily(child["id"])["seconds"] == 4500


def test_context_pairs_versions_and_failure_are_explicit():
    calls = [
        {
            "source_call": "old",
            "purpose": "work_check",
            "status": "succeeded",
            "messages": [
                {"role": "system", "content": "old system"},
                {"role": "user", "content": json.dumps({"solution": "old text", "intent": "check"})},
                {"role": "user", "content": "FIRST QUESTION"},
            ],
            "response": "FIRST ANSWER",
        }
    ]
    original = copy.deepcopy(calls)
    messages, meta = work_messages("system", "algebra", "new text", 2, "follow_up", "SECOND QUESTION", calls)
    assert [m["role"] for m in messages] == ["system", "user", "user", "assistant", "user"]
    assert "old text" in messages[2]["content"] and "legacy_unspecified" in messages[2]["content"]
    assert messages[-1]["content"] == "SECOND QUESTION" and calls == original
    calls.append(
        {
            **meta,
            "source_call": "new",
            "purpose": "work_check",
            "status": "succeeded",
            "response": "SECOND ANSWER",
            "messages": messages,
        }
    )
    third, _ = work_messages("system", "algebra", "new text", 2, "follow_up", "THIRD QUESTION", calls)
    assert sum(m["content"].count("FIRST QUESTION") for m in third) == 1
    assert sum(m["content"].count("SECOND QUESTION") for m in third) == 1
    assert [m["role"] for m in third] == ["system", "user", "user", "assistant", "user", "assistant", "user"]
    calls.append(
        {
            "source_call": "bad",
            "purpose": "work_check",
            "status": "cancelled",
            "dialogue_user": "UNANSWERED",
            "work_revision": 2,
            "response": "DO NOT USE THIS AS AN ANSWER",
        }
    )
    final, meta = work_messages("system", "algebra", "new text", 2, "hint", "", calls)
    assert (
        "DO NOT USE" not in str(final) and "UNANSWERED" in str(final) and meta["unresolved_calls"] == ["bad"]
    )


def test_dialogue_rejects_whole_context_without_truncating():
    with pytest.raises(AppError) as error:
        work_messages(
            "system",
            "algebra",
            "solution",
            1,
            "check",
            "",
            [
                {
                    "source_call": "big",
                    "purpose": "work_check",
                    "status": "succeeded",
                    "dialogue_user": "x" * 16000,
                    "response": "y" * 16000,
                    "work_revision": 1,
                }
            ],
        )
    assert error.value.code == "text_limit"


def test_persisted_dialogue_survives_reopen_and_old_records_unchanged(family):
    app, _, child, _ = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, value="solution", expected_revision=0, confirm=True)
    for i in range(4):
        job = wait_job(
            app,
            command(
                app,
                "work_check",
                work=work,
                expected_revision=1,
                intent="follow_up",
                follow_up=f"QUESTION_{i}",
            ),
        )
        assert job["status"] == "succeeded"
    before = [tuple(r) for r in app.store.db.execute("SELECT * FROM learning_calls ORDER BY rowid")]
    app.logout()
    app.login(child["id"], "student-password-123")
    wait_job(app, command(app, "work_check", work=work, expected_revision=1, intent="hint"))
    after = [tuple(r) for r in app.store.db.execute("SELECT * FROM learning_calls ORDER BY rowid")]
    assert after[:4] == before
    sent = json.loads(after[-1][-1])["messages"]
    assert all(
        sum(m["content"].count(f"QUESTION_{i}") for m in sent if m["role"] == "user") == 1 for i in range(4)
    )


def test_explicit_subject_copy_preserves_original_and_operations(family):
    app, _, child, _ = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, value="print(1)", expected_revision=0, confirm=True)
    old = app.learning_engine.work_row(work)
    args = dict(work=work, subject="informatics", expected_revision=1, operation_id="copy-context")
    copied = command(app, "work_copy", **args)
    assert command(app, "work_copy", **args) == copied and app.learning_engine.work_row(work) == old
    value = app.learning_engine.body(app.learning_engine.work_row(copied["id"]))
    assert (
        value["subject"] == "informatics" and not value["confirmed"] and value["copied_from"]["work"] == work
    )
    assert not app.store.db.execute("SELECT * FROM learning_calls WHERE work=?", (copied["id"],)).fetchall()
