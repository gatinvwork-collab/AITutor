"""Independent QA regressions: assertions describe required behavior, no product changes."""
import json

from tests.test_application import family as family_fixture, child_login
from tests.test_learning_050 import (
    approved_bank, command, wait_job,
)

family = family_fixture


def test_finishing_paused_attempt_preserves_other_active_timer(family):
    app, _, child, clock = family
    state, collection = approved_bank(app, child)
    child_login(app, child)
    # Fully answer A, but leave it paused rather than completed.
    old = command(app, "start", student=child["id"], collection=collection,
                  purpose="topic_confirmation",
                  topic=app.learning_engine.topics(state["curriculum"])[0]["id"])["id"]
    for _ in range(10):
        view = command(app, "attempt", attempt=old)
        slot = next(s for s in view["slots"] if not s["answers"] and not s["skipped"])
        if slot["starred"]:
            command(app, "skip", attempt=old, slot=slot["id"], expected_revision=view["revision"])
        else:
            command(app, "submit", attempt=old, slot=slot["id"], answer="Исходный ответ",
                    expected_revision=view["revision"])
    view = command(app, "attempt", attempt=old)
    command(app, "pause", attempt=old, expected_revision=view["revision"])
    current = command(app, "start", student=child["id"], collection=collection,
                      purpose="topic_confirmation",
                      topic=app.learning_engine.topics(state["curriculum"])[0]["id"])["id"]
    view = command(app, "attempt", attempt=old)
    command(app, "finish", attempt=old, expected_revision=view["revision"])
    pointer = app.assessment_active
    clock[0] += 30
    app.tick()
    active = command(app, "attempt", attempt=current)
    print(json.dumps({"active_status": active["status"], "pointer_is_active": pointer == current,
                      "active_seconds_after_30": active["body"]["seconds"]}))
    assert pointer == current, "Finishing paused A discarded active B's runtime pointer"
    assert active["body"]["seconds"] == 30


def test_follow_up_keeps_previous_user_clarification(family):
    app, _, child, _ = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, value="3x+5=20\n3x=15\nx=5",
            expected_revision=0, confirm=True)
    first = wait_job(app, command(app, "work_check", work=work, expected_revision=1,
                                 intent="follow_up", follow_up="QA_CONTEXT: объясни вычитание пяти"))
    assert first["status"] == "succeeded"
    second = wait_job(app, command(app, "work_check", work=work, expected_revision=1,
                                  intent="follow_up", follow_up="Поясни мой предыдущий вопрос подробнее"))
    assert second["status"] == "succeeded"
    calls = [app.learning_engine.body(c) for c in app.store.db.execute(
        "SELECT * FROM learning_calls WHERE work=? ORDER BY rowid", (work,))]
    sent = calls[-1]["messages"]
    print(json.dumps({"roles": [m["role"] for m in sent],
                      "previous_user_turn_present": "QA_CONTEXT" in json.dumps(sent),
                      "previous_turn_still_in_journal": "QA_CONTEXT" in json.dumps(calls[0])}))
    assert "QA_CONTEXT" in json.dumps(sent), "Previous user clarification lost after one follow-up"
