"""Verify additive schema 5 against a genuine frozen a4 synthetic source."""

import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from tutor_ai.service import Service
from tutor_ai.errors import AppError
from tests.test_application import FakeProvider
from tests.test_learning_050 import command, wait_job
from tests.upgrade_051 import PASSWORD, CHILD_PASSWORD, BACKUP_PASSWORD, tables, originals


def verify(source, destination):
    before = (source / "app-data/data/vault.aead").read_bytes()
    expected = json.loads((source / "expected.json").read_text(encoding="utf-8"))
    shutil.copytree(source / "app-data", destination / "app-data")
    app = Service(destination / "app-data", provider_factory=FakeProvider)
    app.store.unlock(expected["parent"], PASSWORD)
    actual = tables(app.store)
    checks = {"old_tables_unchanged": all(actual[k] == v for k, v in expected["tables"].items() if k != "schema_migrations"),
              "schema_5": app.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 5,
              "original_bytes": originals(app.store) == expected["originals"],
              "vault_id": app.store.envelope["vault"] == expected["vault"],
              "snapshot_matches_source": any(p.read_bytes() == before for p in (destination / "app-data/backups").glob("before-migration-v4-*.aead")),
              "trace_default_off": not app.content_trace.unlocked and not app.content_trace.enabled,
              "foreign_keys": not app.store.db.execute("PRAGMA foreign_key_check").fetchall()}
    app.store.close()
    app.recover(expected["parent"], expected["recovery"], PASSWORD)
    app.login(expected["child"], CHILD_PASSWORD)
    checks["crashed_attempt_requires_resume"] = command(app, "attempt", attempt=expected["attempt"])["status"] == "paused"
    old = [tuple(r) for r in app.store.db.execute("SELECT * FROM learning_calls ORDER BY rowid")]
    job = wait_job(app, command(app, "work_check", work=expected["work"], expected_revision=2, intent="follow_up", follow_up="New post-migration question"))
    checks["dialogue_continues"] = job["status"] == "succeeded"
    after = [tuple(r) for r in app.store.db.execute("SELECT * FROM learning_calls ORDER BY rowid")]
    checks["past_payloads_unchanged"] = after[:len(old)] == old
    app.logout()
    app.login(expected["parent"], PASSWORD)
    backup = app.backup(BACKUP_PASSWORD)["file"]
    app.restore(backup, BACKUP_PASSWORD, expected["parent"], PASSWORD)
    checks["restore_clears_context"] = not app.actor and not app.store.db and not app.content_trace.unlocked
    app.login(expected["parent"], PASSWORD)
    checks["originals_after_restore"] = originals(app.store) == expected["originals"]
    app.rename_profile("Migrated parent")
    app.logout()
    app.login(expected["parent"], PASSWORD)
    checks["new_write_reopens"] = app.user()["name"] == "Migrated parent"
    app.logout()
    app.network_jobs.shutdown()
    checks["source_unchanged"] = (source / "app-data/data/vault.aead").read_bytes() == before
    result = {"passed": all(checks.values()), "source_version": expected["source_version"], "checks": checks,
              "source_sha256": hashlib.sha256(before).hexdigest()}
    (destination / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return result


def fault(source, destination):
    shutil.copytree(source / "app-data", destination / "app-data")
    expected = json.loads((source / "expected.json").read_text(encoding="utf-8"))
    vault = destination / "app-data/data/vault.aead"
    before = vault.read_bytes()
    app = Service(destination / "app-data")
    import tutor_ai.crypto as crypto
    original = crypto.atomic_write
    def fail(path, data):
        if Path(path).resolve() == vault.resolve():
            raise OSError("synthetic migration checkpoint")
        return original(path, data)
    refused = False
    with patch("tutor_ai.crypto.atomic_write", fail), patch("tutor_ai.storage.atomic_write", fail):
        try:
            app.store.unlock(expected["parent"], PASSWORD)
        except AppError as error:
            refused = error.code == "migration"
    assert refused and vault.read_bytes() == before and app.store.db is None
    app.store.unlock(expected["parent"], PASSWORD)
    assert app.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 5
    app.store.close()
    return {"refused": True, "source_unchanged_on_failure": True, "retry_succeeded": True}


if __name__ == "__main__":
    import sys
    source, target = map(lambda p: Path(p).resolve(), sys.argv[1:3])
    target.mkdir(parents=True)
    result = verify(source, target)
    failure = fault(source, target.with_name(target.name + "-fault"))
    (target / "fault.json").write_text(json.dumps(failure), encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)
