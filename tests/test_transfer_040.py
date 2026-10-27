"""Real encrypted schema 1/2/3 fixtures, publication faults and source immutability."""
import json

import pytest

from tutor_ai.crypto import open_seal, seal
from tutor_ai.errors import AppError
from tutor_ai.service import Service
from tutor_ai.transfer import Transfer, JOURNAL, digest, inventory, installation_lock
from tests.test_application import PASSWORD, CHILD_PASSWORD, PROFILE
from tests.test_feedback_02 import make_legacy
from tests.test_feedback_03 import legacy_v2


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "Старая установка AI-Tutor"
    app = Service(root / "app-data")
    parent = app.register("Родитель AI-Tutor", PASSWORD, "PARENT")
    child = app.register("Ученик", CHILD_PASSWORD, "STUDENT", PROFILE)
    with app.store.transaction():
        app.store.put("homework", "original", {"id": "original", "student": child["id"],
            "filename": "history.txt", "text": "AI-Tutor: неизменная история", "result": "Прежний результат",
            "original": seal(app.store.attachment_key(), b"AITutor original", b"original")}, child["id"])
        app.store.put("session", "active", {"id": "active", "student": child["id"], "status": "active",
            "created": "2026-10-26T12:00:00+00:00", "title": "Старая тема", "topic": "math-equations",
            "subject": "algebra", "mode": "learn", "seconds": 42,
            "messages": [{"role": "user", "text": "AI Tutor"}]}, child["id"])
    (app.store.root / "unknown.bin").write_bytes(b"unknown persistent data")
    (app.store.root / "attachments" / "legacy.aead").write_bytes(b"preserve unknown encrypted file")
    (app.store.root / "cache" / "ignored").write_bytes(b"runtime cache")
    yield root, app, parent, child
    app.store.close()


def perform(root, target, account, password=PASSWORD, executable=None):
    transfer = Transfer(target, executable)
    plan = transfer.prepare(root)
    result = transfer.execute(plan["id"], account, password)
    return transfer, result


@pytest.mark.parametrize("schema", [1, 2, 3])
def test_copy_migration_history_originals_recovery_and_source_unchanged(source, tmp_path, schema):
    root, old, parent, child = source
    original = old.store.get("homework", "original")
    if schema == 1:
        make_legacy(old, child)
    elif schema == 2:
        legacy_v2(old)
    else:
        old.store.close()
    before = inventory(root / "app-data")
    target = tmp_path / "Tutor-AI новая"
    _, result = perform(root, target, parent["id"])
    assert result["ok"] and inventory(root / "app-data") == before
    assert not (target / "app-data" / "cache" / "ignored").exists()
    copied = Service(target / "app-data")
    copied.store.unlock(parent["id"], PASSWORD)
    assert all(copied.store.get("homework", "original")[k] == v for k, v in original.items())
    assert open_seal(copied.store.attachment_key(), original["original"], b"original") == b"AITutor original"
    assert copied.store.get("session", "active")["status"] == "paused"
    assert copied.store.get("session", "active")["seconds"] == 42
    assert copied.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 3
    assert (copied.store.root / "unknown.bin").read_bytes() == b"unknown persistent data"
    assert copied.store.user(child["id"])["design"] == "modern"
    copied.store.close()
    copied.recover(parent["id"], parent["recovery_key"], PASSWORD)
    copied.login(parent["id"], PASSWORD)
    assert copied.snapshot()["students"][0]["id"] == child["id"]
    copied.logout()
    with pytest.raises(AppError):
        Transfer(target).prepare(root)
    assert inventory(root / "app-data") == before


@pytest.mark.parametrize("schema", [1, 2, 3])
def test_scenario_a_old_data_in_place(source, schema):
    _, app, parent, child = source
    if schema == 1:
        make_legacy(app, child)
    elif schema == 2:
        legacy_v2(app)
    app.store.close()
    app.actor = None
    assert len(app.status()["accounts"]) == 2
    app.login(child["id"], CHILD_PASSWORD)
    assert app.store.get("session", "active")["status"] == "paused"
    assert not app.active_lesson
    assert app.store.get("homework", "original")["text"] == "AI-Tutor: неизменная история"
    app.logout()


def test_wrong_password_recovery_blocks_registration_and_retry(source, tmp_path):
    root, _, parent, _ = source
    target = tmp_path / "new"
    transfer = Transfer(target)
    plan = transfer.prepare(root)
    before = inventory(root / "app-data")
    with pytest.raises(AppError):
        transfer.execute(plan["id"], parent["id"], "incorrect")
    host = Service(target / "app-data")
    assert host.status()["transfer_pending"]
    with pytest.raises(AppError):
        host.dispatch("register", {"name": "No overwrite", "role": "PARENT", "password": PASSWORD})
    assert not host.store.exists
    assert Transfer.recover(host.store.root) == {"ok": True, "published": False}
    plan = transfer.prepare(root)
    assert transfer.execute(plan["id"], parent["id"], PASSWORD)["ok"]
    assert inventory(root / "app-data") == before


@pytest.mark.parametrize("failure", ["copy", "publish", "cancel", "disk", "verify", "migration"])
def test_interruption_and_safe_cleanup(source, tmp_path, monkeypatch, failure):
    import tutor_ai.transfer as module
    root, app, parent, child = source
    if failure == "migration":
        legacy_v2(app)
    target = tmp_path / "new"
    transfer = Transfer(target)
    plan = transfer.prepare(root)
    before = inventory(root / "app-data")
    if failure == "copy":
        monkeypatch.setattr(module.shutil, "copy2", lambda *_: (_ for _ in ()).throw(OSError("disk")))
    elif failure == "publish":
        real = module.publish_file
        calls = []
        def fail(a, b):
            calls.append(b)
            if len(calls) == 2:
                raise OSError("publication stopped")
            real(a, b)
        monkeypatch.setattr(module, "publish_file", fail)
    elif failure == "cancel":
        monkeypatch.setattr(transfer, "checkpoint", lambda: (_ for _ in ()).throw(AppError("cancelled")))
    elif failure == "disk":
        class Space:
            free = 0
        monkeypatch.setattr(module.shutil, "disk_usage", lambda _: Space())
    elif failure == "verify":
        monkeypatch.setattr(module, "validate_store", lambda _: (_ for _ in ()).throw(AppError("integrity")))
    else:
        monkeypatch.setattr("tutor_ai.storage.atomic_write", lambda *_: (_ for _ in ()).throw(OSError("migration")))
    with pytest.raises((OSError, AppError)):
        transfer.execute(plan["id"], parent["id"], PASSWORD)
    monkeypatch.undo()
    assert inventory(root / "app-data") == before
    Transfer.recover(target / "app-data")
    assert not (target / "app-data" / "data" / "vault.aead").exists()
    assert not (target / "app-data" / JOURNAL).exists()
    plan = transfer.prepare(root)
    assert transfer.execute(plan["id"], parent["id"], PASSWORD)["ok"]


def test_complete_publication_interrupted_before_cleanup(source, tmp_path, monkeypatch):
    root, _, parent, _ = source
    target = tmp_path / "new"
    transfer = Transfer(target)
    plan = transfer.prepare(root)
    original = Transfer.finish
    monkeypatch.setattr(Transfer, "finish", lambda *_: (_ for _ in ()).throw(OSError("stopped")))
    with pytest.raises(OSError):
        transfer.execute(plan["id"], parent["id"], PASSWORD)
    monkeypatch.setattr(Transfer, "finish", original)
    assert Transfer.recover(target / "app-data")["published"]
    app = Service(target / "app-data")
    app.login(parent["id"], PASSWORD)
    app.logout()


@pytest.mark.parametrize("conflict", ["vault", "unknown", "config", "symlink", "nested", "same", "locked", "changed"])
def test_conflicts_links_lock_and_changed_source(source, tmp_path, conflict):
    root, _, parent, _ = source
    target = tmp_path / "new"
    data = target / "app-data"
    data.mkdir(parents=True)
    if conflict in ("vault", "unknown", "config"):
        path = data / {"vault": "data/vault.aead", "unknown": "unknown.txt", "config": "config/settings.json"}[conflict]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"do not overwrite")
        before = digest(path)
        with pytest.raises(AppError):
            Transfer(target).prepare(root)
        assert digest(path) == before
    elif conflict == "symlink":
        # Junctions work on Windows without symlink privileges.
        import subprocess
        link = data / "linked"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(root)], check=True, capture_output=True)
        try:
            with pytest.raises(AppError):
                Transfer(target).prepare(root)
        finally:
            link.rmdir()
    elif conflict in ("nested", "same"):
        with pytest.raises(AppError):
            Transfer(root if conflict == "same" else root / "nested").prepare(root)
    elif conflict == "locked":
        with installation_lock(root / "app-data"):
            with pytest.raises(AppError):
                Transfer(target).prepare(root)
    else:
        transfer = Transfer(target)
        plan = transfer.prepare(root)
        (root / "app-data" / "unknown.bin").write_bytes(b"changed")
        with pytest.raises(AppError):
            transfer.execute(plan["id"], parent["id"], PASSWORD)
        Transfer.recover(data)


@pytest.mark.parametrize("problem", ["missing", "corrupt", "schema"])
def test_bad_source_does_not_publish(source, tmp_path, problem):
    root, app, parent, child = source
    with app.store.transaction():
        if problem == "missing":
            work = app.store.get("homework", "original")
            del work["original"]
            app.store.put("homework", "original", work, child["id"])
        elif problem == "schema":
            app.store.db.execute("INSERT INTO schema_migrations VALUES(99)")
    if problem == "corrupt":
        app.store.path.write_bytes(b"broken")
    target = tmp_path / "new"
    transfer = Transfer(target)
    with pytest.raises(AppError):
        plan = transfer.prepare(root)
        transfer.execute(plan["id"], parent["id"], PASSWORD)
    if (target / "app-data" / JOURNAL).exists():
        Transfer.recover(target / "app-data")
    assert not (target / "app-data" / "data" / "vault.aead").exists()


def test_separate_portable_executable_and_no_overwrite(source, tmp_path):
    root, _, parent, _ = source
    host = tmp_path / "host"
    host.mkdir()
    executable = host / "Tutor-AI-0.4.0.exe"
    executable.write_bytes(b"test executable artifact")
    destination = tmp_path / "separate"
    transfer = Transfer(host, executable)
    plan = transfer.prepare(root, destination)
    assert transfer.execute(plan["id"], parent["id"], PASSWORD)["current"] is False
    assert digest(destination / executable.name) == digest(executable)
    assert (destination / "app-data" / "data" / "vault.aead").exists()


def test_cleanup_never_removes_replaced_destination_file(source, tmp_path, monkeypatch):
    import tutor_ai.transfer as module
    root, _, parent, _ = source
    target = tmp_path / "new"
    transfer = Transfer(target)
    plan = transfer.prepare(root)
    real = module.publish_file
    def fail(a, b):
        real(a, b)
        raise OSError("crash")
    monkeypatch.setattr(module, "publish_file", fail)
    with pytest.raises(OSError):
        transfer.execute(plan["id"], parent["id"], PASSWORD)
    data = target / "app-data"
    manifest = json.loads((data / JOURNAL).read_bytes())["files"]
    published = next(data / name for name in manifest if (data / name).exists())
    published.unlink()
    published.write_bytes(b"external change")
    with pytest.raises(AppError):
        Transfer.recover(data)
    assert published.read_bytes() == b"external change"


def test_source_preview_does_not_create_missing_directories(source, tmp_path):
    root, _, _, _ = source
    (root / "app-data" / "secure").rmdir()
    Transfer(tmp_path / "new").prepare(root)
    assert not (root / "app-data" / "secure").exists()


def test_each_post_unlock_write_is_durable_and_failed_write_restores_ram(source, monkeypatch):
    _, app, parent, _ = source
    app.store.close()
    app.store.unlock(parent["id"], PASSWORD)
    for number in range(3):
        with app.store.transaction():
            app.store.put("sentinel", "durable", {"value": number})
        app.store.close()
        app.store.unlock(parent["id"], PASSWORD)
        assert app.store.get("sentinel", "durable") == {"value": number}
    before = app.store.path.read_bytes()
    monkeypatch.setattr("tutor_ai.storage.atomic_write", lambda *_: (_ for _ in ()).throw(OSError("write")))
    with pytest.raises(OSError):
        with app.store.transaction():
            app.store.put("sentinel", "durable", {"value": "lost"})
    assert app.store.get("sentinel", "durable") == {"value": 2}
    assert app.store.path.read_bytes() == before
