"""Independent active-dialogue timer regression; synthetic clock and provider only."""
import json

from tests.test_application import family as family_fixture, child_login
from tests.test_learning_050 import command, wait_job
from tutor_ai.errors import AppError

family = family_fixture


def test_regular_homework_dialogue_does_not_trigger_idle(family):
    app, _, child, clock = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, value="3x+5=20\n3x=15\nx=5",
            expected_revision=0, confirm=True)
    results = []
    for index, advance in enumerate((0, 60, 60, 61)):
        clock[0] += advance
        try:
            value = wait_job(app, command(app, "work_check", work=work, expected_revision=1,
                                         intent="follow_up", follow_up=f"Поясни шаг {index+1}"))
            results.append({"at": clock[0], "status": value["status"], "last_action": app.last_action})
        except AppError as error:
            results.append({"at": clock[0], "error": error.code, "last_action": app.last_action})
    sessions = app.store.all("session", child["id"])
    print(json.dumps({"requests": results, "session_status": sessions[0]["status"],
                      "charged_seconds": sessions[0]["seconds"],
                      "daily_seconds": app.daily(child["id"])["seconds"]}, ensure_ascii=False))
    assert all(r.get("status") == "succeeded" for r in results), "Regular accepted dialogue was classified as idle"
    assert sessions[0]["status"] == "active" and sessions[0]["seconds"] == 181
