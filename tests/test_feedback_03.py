"""Native boundaries, migrations and durable notifications for feedback 0.3."""
import copy
import json
import shutil

import pytest

from aitutor.crypto import atomic_write, encode, seal
from aitutor.errors import AppError
from aitutor.service import Service
from tests.test_application import PASSWORD, CHILD_PASSWORD, PROFILE, family as family_fixture, child_login
from tests.test_feedback_02 import address_fixture

family = family_fixture


def edit(app, account, **changes):
    profile = app.get_profile(account)
    return app.save_profile(account, profile["revision"], changes)


def second_parent(app, child):
    parent = app.register("Второй родитель", PASSWORD, "PARENT")
    code = app.create_invite(child["id"])["token"]
    app.logout()
    app.login(parent["id"], PASSWORD)
    app.link(code)
    return parent


def test_role_defaults_color_and_explicit_choice_persist(family):
    app, parent, child, _ = family
    assert app.user()["design"] == "strict"
    child_login(app, child)
    assert app.user()["design"] == "modern"
    app.set_theme("dark", "strict")
    app.logout()
    app.login(child["id"], CHILD_PASSWORD)
    assert app.snapshot()["user"]["theme"] == "dark"
    assert app.snapshot()["user"]["design"] == "strict"
    with pytest.raises(AppError):
        app.set_theme("dark", "invalid")
    app.logout()
    app.login(parent["id"], PASSWORD)
    assert app.user()["design"] == "strict"


def test_self_edits_preserve_identity_and_reject_privileged_fields(family):
    app, _, child, _ = family
    child_login(app, child)
    session = app.start_lesson("math-equations")
    app.pause(session["id"])
    before = app.store.get("session", session["id"])
    edit(app, child["id"], name="Новое имя", school="Новая школа")
    assert app.user()["id"] == child["id"]
    assert app.store.get("session", session["id"]) == before
    assert next(p for p in app.status()["accounts"] if p["id"] == child["id"])["name"] == "Новое имя"
    assert not app.snapshot()["notifications"]
    for field in ("role", "password", "design", "grade", "consent", "id", "theme"):
        with pytest.raises(AppError):
            edit(app, child["id"], **{field: "PARENT"})


def test_related_parent_edit_is_direct_and_does_not_grant_child_access(family):
    app, first, child, _ = family
    second = second_parent(app, child)
    other = app.register("Только второй семьи", CHILD_PASSWORD, "STUDENT", PROFILE)
    third = second_parent(app, other)
    app.logout()
    app.login(first["id"], PASSWORD)
    assert {p["id"] for p in app.snapshot()["editable_profiles"]} == {first["id"], child["id"], second["id"]}
    edit(app, second["id"], name="Переименованный родитель")
    with pytest.raises(AppError):
        app.get_profile(third["id"])
    with pytest.raises(AppError):
        app.get_profile(other["id"])
    with pytest.raises(AppError):
        app.reset_password(second["id"], "not-permitted-password")
    event = app.snapshot()["audit"][-1]
    assert event["actor"] == first["id"] and event["target"] == second["id"]
    assert event["fields"] == ["name"]
    child_login(app, child)
    with pytest.raises(AppError):
        app.get_profile(first["id"])


def test_revoked_relationship_blocks_open_form_and_notifications(family):
    app, first, child, _ = family
    second = second_parent(app, child)
    form = app.get_profile(first["id"])
    child_login(app, child)
    edit(app, child["id"], city="Другой город")
    app.logout()
    app.login(second["id"], PASSWORD)
    notification = app.notifications()[0]["id"]
    with app.store.transaction():
        app.store.db.execute("DELETE FROM links WHERE parent_id=?", (second["id"],))
    with pytest.raises(AppError):
        app.save_profile(first["id"], form["revision"], {"name": "Недопустимо"})
    assert not app.notifications()
    with pytest.raises(AppError):
        app.read_notification(notification)


def test_notifications_are_atomic_private_durable_and_independent(family):
    app, first, child, _ = family
    second = second_parent(app, child)
    child_login(app, child)
    result = edit(app, child["id"], region="Новый регион", city="Новый город", school="Новая школа")
    assert result["notifications"] == 2
    assert len(app.store.all("notification")) == 2
    assert not edit(app, child["id"], school="Новая школа")["changed"]
    assert len(app.store.all("notification")) == 2
    raw = app.store.path.read_bytes()
    assert "Новая школа".encode() not in raw
    app.logout()
    app.login(first["id"], PASSWORD)
    item = app.snapshot()["notifications"][0]
    assert set(item["changes"]) == {"region", "city", "school"}
    assert item["changes"]["school"] == {"before": PROFILE["school"], "after": "Новая школа"}
    app.read_notification(item["id"])
    assert app.notifications()[0]["read_at"]
    app.logout()
    app.login(second["id"], PASSWORD)
    assert app.notifications()[0]["read_at"] is None
    with pytest.raises(AppError):
        app.read_notification(item["id"])
    edit(app, child["id"], school="Изменил родитель")
    assert len(app.store.all("notification")) == 2


def test_failed_write_rolls_back_profile_revision_directory_and_notification(family, monkeypatch):
    app, _, child, _ = family
    child_login(app, child)
    before = app.get_profile(child["id"])
    raw = app.store.path.read_bytes()
    envelope = copy.deepcopy(app.store.envelope)
    def fail(*_):
        raise OSError("synthetic disk full")
    monkeypatch.setattr("aitutor.storage.atomic_write", fail)
    with pytest.raises(OSError):
        edit(app, child["id"], name="Не сохранено", school="Не сохранена")
    assert app.get_profile(child["id"]) == before
    assert not app.store.all("notification")
    assert app.store.envelope == envelope and app.store.path.read_bytes() == raw


def test_conflicting_form_rejected_and_partial_edits_preserve_other_fields(family):
    app, _, child, _ = family
    before = app.get_profile(child["id"])
    edit(app, child["id"], name="Изменено родителем")
    with pytest.raises(AppError) as error:
        app.save_profile(child["id"], before["revision"], {"school": "Устаревшая форма"})
    assert error.value.code == "conflict"
    assert app.get_profile(child["id"])["profile"] == before["profile"]


def test_saved_catalog_address_edit_without_search_after_restart(tmp_path):
    directory, clock, _ = address_fixture()
    region = directory.search("region", "Сам")["items"][0]
    clock[0] += 2
    city = directory.search("city", "Сам", region["id"])["items"][0]
    app = Service(tmp_path, address_directory=directory)
    parent = app.register("Родитель", PASSWORD, "PARENT")
    child = app.register("Ребёнок", CHILD_PASSWORD, "STUDENT", {**PROFILE, "address": {
        "mode": "catalog", "region_id": region["id"], "city_id": city["id"]}})
    before = app.get_profile(child["id"])["profile"]
    app.logout()
    app = Service(tmp_path)
    app.login(parent["id"], PASSWORD)
    edit(app, child["id"], name="Имя офлайн", region=before["region"], city=before["city"], school="Школа офлайн",
         address={"mode": "catalog", "region_id": region["id"], "city_id": city["id"]})
    assert app.get_profile(child["id"])["profile"]["address"] == before["address"]
    with pytest.raises(AppError):
        edit(app, child["id"], city="Подменённый город")
    app.store.close()


def legacy_v2(app):
    with app.store.db:
        app.store.db.execute("ALTER TABLE users DROP COLUMN design")
        app.store.db.execute("ALTER TABLE users DROP COLUMN profile_revision")
        app.store.db.execute("DELETE FROM schema_migrations WHERE version=3")
    envelope = copy.deepcopy(app.store.envelope)
    envelope["payload"] = seal(app.store.key, app.store.db.serialize(), envelope["vault"].encode())
    raw = encode(envelope)
    atomic_write(app.store.path, raw)
    app.actor = None
    app.store.close()
    return raw


def test_v2_migration_preserves_records_color_recovery_and_is_idempotent(family):
    app, parent, child, _ = family
    app.set_theme("dark")
    child_login(app, child)
    app.set_theme("light")
    lesson = app.start_lesson("math-equations")
    app.pause(lesson["id"])
    before = app.store.get("session", lesson["id"])
    raw = legacy_v2(app)
    app.login(parent["id"], PASSWORD)
    assert app.user()["theme"] == "dark" and app.user()["design"] == "strict"
    child_user = app.store.user(child["id"])
    assert child_user["theme"] == "light" and child_user["design"] == "modern"
    assert app.store.get("session", lesson["id"]) == before
    assert not app.store.all("notification")
    copies = list((app.store.root / "backups").glob("before-migration-v2-*.aead"))
    assert len(copies) == 1 and copies[0].read_bytes() == raw
    app.logout()
    app.recover(parent["id"], parent["recovery_key"], PASSWORD)
    app.login(parent["id"], PASSWORD)
    assert len(list((app.store.root / "backups").glob("before-migration-v2-*.aead"))) == 1


def test_failed_v2_migration_keeps_original(family, monkeypatch):
    app, parent, _, _ = family
    raw = legacy_v2(app)
    real = atomic_write
    def fail(path, data):
        if path == app.store.path:
            raise OSError("synthetic failure")
        real(path, data)
    monkeypatch.setattr("aitutor.storage.atomic_write", fail)
    with pytest.raises(AppError) as error:
        app.login(parent["id"], PASSWORD)
    assert error.value.code == "migration" and app.store.path.read_bytes() == raw


def test_notifications_and_preferences_survive_portable_and_backup(family, tmp_path):
    app, parent, child, _ = family
    child_login(app, child)
    app.set_theme("dark", "strict")
    edit(app, child["id"], school="Школа переноса")
    app.logout()
    app.login(parent["id"], PASSWORD)
    archive = app.backup(PASSWORD)["file"]
    edit(app, child["id"], school="Последняя школа")
    app.restore(archive, PASSWORD, parent["id"], PASSWORD)
    app.login(parent["id"], PASSWORD)
    assert app.notifications()[0]["changes"]["school"]["after"] == "Школа переноса"
    assert app.store.user(child["id"])["design"] == "strict"
    app.logout()
    moved = tmp_path / "portable-moved"
    shutil.copytree(app.store.root, moved)
    reopened = Service(moved)
    reopened.login(child["id"], CHILD_PASSWORD)
    assert reopened.user()["theme"] == "dark" and reopened.user()["design"] == "strict"
    assert json.loads(reopened.user()["profile"])["school"] == "Школа переноса"
    reopened.logout()
    reopened.login(parent["id"], PASSWORD)
    assert len(reopened.notifications()) == 1
    reopened.store.close()


def test_archives_depend_on_real_student_data_not_empty_catalog(family):
    app, _, child, _ = family
    other = app.register("Другой", CHILD_PASSWORD, "STUDENT", PROFILE)
    assert app.snapshot()["students"][0]["archives"] == {"history": {}, "knowledge": {}, "homework": {}}
    with app.store.transaction():
        for topic_id, attempts in (("unknown", 0), ("known-observation", 2)):
            app.store.put("knowledge", topic_id, {"topic": topic_id, "subject": "math", "attempts_count": attempts}, child["id"])
        app.store.put("session", "old", {"subject": "math", "topic": "unknown", "created": "2020-01-01",
            "status": "complete", "messages": [{"role": "user", "text": "Сохранённая учебная работа"}]}, child["id"])
        app.store.put("session", "algebra", {"subject": "math", "topic": "math-equations", "created": "2020-01-01",
            "status": "complete"}, other["id"])
    students = {s["id"]: s for s in app.snapshot()["students"]}
    assert "math_archive" in students[child["id"]]["archives"]["history"]
    assert "math_archive" in students[child["id"]]["archives"]["knowledge"]
    assert not students[other["id"]]["archives"]["history"]


def test_unlinked_student_can_update_without_false_notifications(tmp_path):
    app = Service(tmp_path)
    child = app.register("Самостоятельный", CHILD_PASSWORD, "STUDENT", PROFILE)
    assert edit(app, child["id"], school="Другая школа")["notifications"] == 0
    assert not app.store.all("notification")
    with pytest.raises(AppError):
        app.start_lesson("math-equations")
    app.store.close()
