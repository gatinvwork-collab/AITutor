"""Create via frozen 0.4.1 sources, verify via new runtime; no real user data."""

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "upgrade050-parent-password"
CHILD_PASSWORD = "upgrade050-child-password"


def seed(directory, source):
    sys.path.insert(0, str(source))
    from tutor_ai import __version__
    from tutor_ai.crypto import open_seal
    from tutor_ai.service import Service
    from tests.qa_fixtures import seed_import_032

    assert __version__ == "0.4.1"
    app = Service(directory / "app-data")
    parent = app.register("0.4.1 parent", PASSWORD, "PARENT")
    child = app.register(
        "0.4.1 child",
        CHILD_PASSWORD,
        "STUDENT",
        {"region": "Region", "city": "City", "school": "School", "grade": 7, "address": {"mode": "manual"}},
    )
    second = app.register("Second parent", PASSWORD, "PARENT")
    invite = app.create_invite(child["id"])["token"]
    app.logout()
    app.login(second["id"], PASSWORD)
    app.link(invite)
    app.register(
        "Second child",
        CHILD_PASSWORD,
        "STUDENT",
        {"region": "Region", "city": "City", "school": "School", "grade": 7, "address": {"mode": "manual"}},
    )
    app.set_theme("dark", "modern")
    app.save_provider(
        {
            "kind": "gigachat",
            "model": "synthetic-offline",
            "scope": "GIGACHAT_API_PERS",
            "secret": "FAKE-UPGRADE-KEY-NOT-A-CREDENTIAL",
            "allow_text": True,
            "allow_documents": True,
            "revision": 0,
        }
    )
    app.backup("upgrade050-backup-password")
    backup = app.store.get("settings", "backup")["last_file"]
    seed_import_032(app, child["id"])
    # Seed helper manages its own transaction; further explicit historical facts.
    with app.store.transaction():
        app.store.put(
            "session",
            "past",
            {
                "id": "past",
                "student": child["id"],
                "subject": "math",
                "topic": "math-equations",
                "title": "Previous AI-Tutor history",
                "status": "complete",
                "created": "2026-10-25T10:00:00+00:00",
                "seconds": 121,
                "total": 3,
                "correct": 2,
                "hints_used": 2,
                "messages": [{"role": "user", "text": "Historical answer"}],
                "program_snapshot": {"title": "Previous textbook"},
                "operation_ids": ["past-operation"],
            },
            child["id"],
        )
        app.store.put(
            "knowledge",
            "past-knowledge",
            {
                "topic": "math-equations",
                "subject": "math",
                "attempts_count": 3,
                "correct_count": 2,
                "mastery_score": 61,
                "confidence": 0.75,
                "hints_used": 2,
                "next_review_at": "2026-11-01",
            },
            child["id"],
        )
        app.store.put(
            "notification",
            "read-notification",
            {
                "id": "read-notification",
                "recipient": parent["id"],
                "student": child["id"],
                "actor": child["id"],
                "student_name": "0.4.1 child",
                "actor_name": "0.4.1 child",
                "at": "2026-10-26",
                "read_at": "2026-10-27",
                "changes": {"school": {"before": "A", "after": "B"}},
            },
            child["id"],
        )
        app.store.put("settings", "backup", {"last_file": backup, "last_auto": time.time()})
    # Archive containing all learning records, produced by the original code.
    backup = app.backup("upgrade050-backup-password")["file"]
    with app.store.transaction():
        settings = app.store.get("settings", "backup")
        settings["last_auto"] = time.time()
        app.store.put("settings", "backup", settings)
    app.logout()
    app.store.unlock(parent["id"], PASSWORD)
    users = [dict(row) for row in app.store.db.execute("SELECT * FROM users ORDER BY id")]
    links = [list(row) for row in app.store.db.execute("SELECT * FROM links ORDER BY parent_id,student_id")]
    records = [
        dict(row)
        for row in app.store.db.execute(
            "SELECT * FROM records WHERE kind NOT IN ('audit','settings') ORDER BY kind,id"
        )
    ]
    originals = {
        work["id"]: hashlib.sha256(
            open_seal(app.store.attachment_key(), work["original"], work["id"].encode())
        ).hexdigest()
        for work in app.store.all("homework")
        if work.get("original")
    }
    expected = {
        "source_version": __version__,
        "parent": parent["id"],
        "child": child["id"],
        "recovery": parent["recovery_key"],
        "backup": backup,
        "users": users,
        "links": links,
        "records": records,
        "originals": originals,
        "vault": app.store.envelope["vault"],
    }
    app.store.close()
    (directory / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    print(
        json.dumps(
            {
                "source_version": __version__,
                "users": len(users),
                "records": len(records),
                "originals": len(originals),
            }
        )
    )


def verify(directory):
    from tutor_ai.crypto import open_seal
    from tutor_ai.service import Service

    expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    app = Service(directory / "app-data")
    app.store.unlock(expected["parent"], PASSWORD)
    checks = {
        "schema": app.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 5,
        "vault_identity": app.store.envelope["vault"] == expected["vault"],
        "users": [dict(row) for row in app.store.db.execute("SELECT * FROM users ORDER BY id")]
        == expected["users"],
        "links": [
            list(row) for row in app.store.db.execute("SELECT * FROM links ORDER BY parent_id,student_id")
        ]
        == expected["links"],
        "records": [
            dict(row)
            for row in app.store.db.execute(
                "SELECT * FROM records WHERE kind NOT IN ('audit','settings') ORDER BY kind,id"
            )
        ]
        == expected["records"],
        "originals": {
            work["id"]: hashlib.sha256(
                open_seal(app.store.attachment_key(), work["original"], work["id"].encode())
            ).hexdigest()
            for work in app.store.all("homework")
            if work.get("original")
        }
        == expected["originals"],
    }
    app.store.close()
    app.recover(expected["parent"], expected["recovery"], PASSWORD)
    app.login(expected["parent"], PASSWORD)
    app.restore(expected["backup"], "upgrade050-backup-password", expected["parent"], PASSWORD)
    checks["restore_clears_context"] = app.actor is None and app.store.db is None
    app.login(expected["parent"], PASSWORD)
    checks["old_backup_history"] = app.store.get("session", "past")["seconds"] == 121
    checks["old_backup_originals"] = {
        work["id"]: hashlib.sha256(
            open_seal(app.store.attachment_key(), work["original"], work["id"].encode())
        ).hexdigest()
        for work in app.store.all("homework")
        if work.get("original")
    } == expected["originals"]
    app.rename_profile("New persisted name")
    app.logout()
    app.login(expected["parent"], PASSWORD)
    checks["new_write_after_reopen"] = app.user()["name"] == "New persisted name"
    app.logout()
    result = {"passed": all(checks.values()), "checks": checks, "source_version": "0.4.1"}
    (directory / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    folder = Path(sys.argv[2]).resolve()
    assert folder.is_relative_to(ROOT / "build")
    folder.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "seed":
        seed(folder, Path(sys.argv[3]).resolve())
    else:
        raise SystemExit(verify(folder))
