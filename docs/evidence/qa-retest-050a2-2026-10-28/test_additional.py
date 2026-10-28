"""Independent assertions for a2 edge cases; product code is unchanged."""
import json

import pytest

from tests.test_application import family as family_fixture, child_login
from tests.test_learning_050 import approved_bank, command, wait_job

family = family_fixture


def test_failed_idle_checkpoint_keeps_attempt_runtime_consistent(family, monkeypatch):
    app, _, child, clock = family
    state, collection = approved_bank(app, child)
    child_login(app, child)
    attempt = command(app, "start", student=child["id"], collection=collection,
                      purpose="topic_confirmation",
                      topic=app.learning_engine.topics(state["curriculum"])[0]["id"])["id"]
    clock[0] += 181

    def fail_save():
        raise OSError("QA injected checkpoint write failure")

    with monkeypatch.context() as fault:
        fault.setattr(app.store, "save", fail_save)
        with pytest.raises(OSError):
            app.tick()
    after_failure = command(app, "attempt", attempt=attempt)
    pointer = app.assessment_active
    app.tick()
    after_retry = command(app, "attempt", attempt=attempt)
    print(json.dumps({"after_failure_status": after_failure["status"],
                      "runtime_still_points_to_attempt": pointer == attempt,
                      "after_retry_status": after_retry["status"],
                      "after_retry_seconds": after_retry["body"]["seconds"],
                      "daily_seconds": app.daily(child["id"])["seconds"]}))
    assert pointer == attempt, "Failed atomic checkpoint cleared runtime despite database rollback"
    assert after_retry["status"] == "paused" and after_retry["body"]["seconds"] == 180


def test_hint_intent_is_transmitted_when_clarification_is_not_empty(family):
    app, _, child, _ = family
    child_login(app, child)
    requests = {}
    for intent in ("check", "hint", "follow_up"):
        work = command(app, "work", student=child["id"], subject="algebra")["id"]
        command(app, "work_revision", work=work, value="3x+5=20\n3x=15\nx=5",
                expected_revision=0, confirm=True)
        job = wait_job(app, command(app, "work_check", work=work, expected_revision=1,
                                   intent=intent, follow_up="Поясни второй шаг"))
        assert job["status"] == "succeeded", job
        call = app.store.db.execute("SELECT * FROM learning_calls WHERE work=?", (work,)).fetchone()
        body = app.learning_engine.body(call)
        assert body["intent"] == intent  # Metadata must not be confused with the sent payload.
        requests[intent] = body["messages"]
        app.pause(app.active_lesson)
    print(json.dumps({"check_equals_hint": requests["check"] == requests["hint"],
                      "hint_equals_follow_up": requests["hint"] == requests["follow_up"],
                      "roles": [m["role"] for m in requests["hint"]]}))
    assert requests["check"] != requests["hint"], "Model receives identical requests for check and hint"
