"""Build a genuine a1 schema-4 fixture, then verify copies under a2."""

import hashlib
import json
import sys
from pathlib import Path

PASSWORD = "qa051-upgrade-parent"
CHILD_PASSWORD = "qa051-upgrade-child"
BACKUP_PASSWORD = "qa051-upgrade-backup"


def tables(store):
    result = {}
    for row in store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        name = row[0]
        values = sorted([tuple(r) for r in store.db.execute("SELECT * FROM " + name)], key=repr)
        result[name] = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return result


def originals(store):
    from tutor_ai.crypto import open_seal

    return {
        r["id"]: hashlib.sha256(
            open_seal(store.attachment_key(), r["original"], r["id"].encode())
        ).hexdigest()
        for r in store.all("homework")
        if r.get("original")
    }


def seed(directory, source):
    sys.path.insert(0, str(source))
    from tutor_ai import __version__
    from tutor_ai.service import Service
    from tutor_ai.crypto import seal
    from tests.test_learning_050 import approved_bank, command, wait_job, finish_answers
    from tests.test_application import FakeProvider
    from PySide6.QtGui import QImage
    from PySide6.QtCore import QBuffer, QIODevice

    assert __version__ in ("0.5.0a1", "0.5.0a2", "0.5.0a3", "0.5.0a4")
    app = Service(directory / "app-data", provider_factory=FakeProvider)
    parent = app.register("Previous parent", PASSWORD, "PARENT")
    profile = {
        "region": "Region",
        "city": "City",
        "school": "School",
        "grade": 7,
        "address": {"mode": "manual"},
    }
    child = app.register("Previous child", CHILD_PASSWORD, "STUDENT", profile)
    second = app.register("Second parent", PASSWORD, "PARENT")
    invite = app.create_invite(child["id"])["token"]
    app.logout()
    app.login(second["id"], PASSWORD)
    app.link(invite)
    app.register("Second child", CHILD_PASSWORD, "STUDENT", profile)
    app.logout()
    app.login(parent["id"], PASSWORD)
    app.save_provider({"kind": "ollama", "model": "synthetic", "revision": 0})
    state, col = approved_bank(app, child)
    app.logout()
    app.login(child["id"], CHILD_PASSWORD)
    app.provider_factory = FakeProvider
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFF)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    raw = bytes(buffer.data())
    with app.store.transaction():
        app.store.put(
            "homework",
            "old-photo",
            {
                "id": "old-photo",
                "student": child["id"],
                "filename": "old.png",
                "text": "",
                "original": seal(app.store.attachment_key(), raw, b"old-photo"),
            },
            child["id"],
        )
    command(app, "work_original", work=work, homework="old-photo", expected_revision=0)
    command(app, "work_revision", work=work, value="print('old solution')", expected_revision=1, confirm=True)
    for question in ("OLD051 FIRST QUESTION", "Explain my previous question"):
        assert (
            wait_job(
                app,
                command(
                    app, "work_check", work=work, expected_revision=2, intent="follow_up", follow_up=question
                ),
            )["status"]
            == "succeeded"
        )
    app.pause(app.active_lesson)
    a = finish_answers(app, child, col, state)
    with app.store.transaction():
        app.store.db.execute("UPDATE learning_attempts SET status='paused' WHERE id=?", (a,))
    b = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )["id"]
    # Simulate an unexpected exit. No imaginary downtime is billed by a2.
    app.store.close()
    app.network_jobs.shutdown()
    app = Service(directory / "app-data", provider_factory=FakeProvider)
    app.login(parent["id"], PASSWORD)
    old = app.store.get("provider", "family")
    app.save_provider(
        {
            "kind": "gigachat",
            "model": "synthetic-no-live-model",
            "scope": "GIGACHAT_API_PERS",
            "secret": "FAKE-UPGRADE-NOT-A-REAL-KEY",
            "allow_text": True,
            "allow_documents": True,
            "revision": old["revision"],
        }
    )
    app.backup(BACKUP_PASSWORD)
    app.logout()
    app.store.unlock(parent["id"], PASSWORD)
    expected = {
        "source_version": __version__,
        "parent": parent["id"],
        "child": child["id"],
        "recovery": parent["recovery_key"],
        "work": work,
        "attempt": b,
        "vault": app.store.envelope["vault"],
        "tables": tables(app.store),
        "originals": originals(app.store),
    }
    app.store.close()
    (directory / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    print(
        json.dumps(
            {
                "source_version": __version__,
                "table_count": len(expected["tables"]),
                "originals": len(expected["originals"]),
            }
        )
    )


def verify(directory):
    from tutor_ai.service import Service
    from tests.test_learning_050 import command, wait_job
    from tests.test_application import FakeProvider

    expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    app = Service(directory / "app-data", provider_factory=FakeProvider)
    app.store.unlock(expected["parent"], PASSWORD)
    checks = {
        "all_tables_before_writes": tables(app.store) == expected["tables"],
        "original_bytes": originals(app.store) == expected["originals"],
        "vault_id": app.store.envelope["vault"] == expected["vault"],
        "schema_4": app.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 4,
    }
    previous_calls = [
        tuple(r)
        for r in app.store.db.execute(
            "SELECT * FROM learning_calls WHERE work=? ORDER BY rowid", (expected["work"],)
        )
    ]
    app.store.close()
    app.recover(expected["parent"], expected["recovery"], PASSWORD)
    app.login(expected["child"], CHILD_PASSWORD)
    checks["active_requires_resume"] = (
        command(app, "attempt", attempt=expected["attempt"])["status"] == "paused"
    )
    checks["old_subject_not_rewritten"] = (
        app.learning_engine.body(app.learning_engine.work_row(expected["work"]))["subject"] == "algebra"
    )
    copied = command(app, "work_copy", work=expected["work"], subject="informatics", expected_revision=2)
    checks["explicit_copy_unverified"] = not app.learning_engine.body(
        app.learning_engine.work_row(copied["id"])
    )["confirmed"]
    job = wait_job(
        app,
        command(
            app,
            "work_check",
            work=expected["work"],
            expected_revision=2,
            intent="follow_up",
            follow_up="NEW051 QUESTION",
        ),
    )
    checks["new_dialogue_succeeds"] = job["status"] == "succeeded"
    calls = [
        tuple(r)
        for r in app.store.db.execute(
            "SELECT * FROM learning_calls WHERE work=? ORDER BY rowid", (expected["work"],)
        )
    ]
    checks["past_payloads_unchanged"] = calls[: len(previous_calls)] == previous_calls
    checks["old_question_recovered_for_future"] = "OLD051 FIRST QUESTION" in json.dumps(
        json.loads(calls[-1][-1])["messages"]
    )
    app.logout()
    app.login(expected["parent"], PASSWORD)
    backup = app.backup(BACKUP_PASSWORD)["file"]
    app.restore(backup, BACKUP_PASSWORD, expected["parent"], PASSWORD)
    checks["restore_clears_context"] = app.actor is None and app.store.db is None
    app.login(expected["parent"], PASSWORD)
    checks["originals_after_restore"] = originals(app.store) == expected["originals"]
    app.rename_profile("Updated parent")
    app.logout()
    app.login(expected["parent"], PASSWORD)
    checks["new_write_reopens"] = app.user()["name"] == "Updated parent"
    app.logout()
    app.network_jobs.shutdown()
    result = {"passed": all(checks.values()), "source_version": expected["source_version"], "checks": checks}
    (directory / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    folder = Path(sys.argv[2]).resolve()
    assert folder.is_relative_to(Path(__file__).resolve().parent.parent / "build")
    folder.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "seed":
        seed(folder, Path(sys.argv[3]).resolve())
    else:
        raise SystemExit(verify(folder))
