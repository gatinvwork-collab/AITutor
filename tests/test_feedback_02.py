import copy
import json

import httpx
import pytest

from tutor_ai.addresses import AddressDirectory
from tutor_ai.crypto import atomic_write, encode, seal
from tutor_ai.education import SUBJECTS, catalog, check_answer, subjects_for_grade, topic
from tutor_ai.errors import AppError
from tutor_ai.service import Service
from tests.test_application import CHILD_PASSWORD, PASSWORD, PROFILE, FakeProvider, child_login
from tests.test_application import family as family


def feature(oid, kind, name, state=None):
    return {"properties": {"countrycode": "RU", "osm_id": oid, "osm_type": "R",
                           "type": kind, "name": name, **({"state": state} if state else {})}}


def address_fixture():
    clock, requests = [0.0], []
    def handler(request):
        requests.append(request)
        if request.url.path.startswith("/structured"):
            values = [feature(2, "city", "Самара", "Самарская область"),
                      feature(3, "city", "Другой город", "Другая область")]
        else:
            values = [feature(1, "state", "Самарская область"), feature(4, "state", "Другая область")]
        return httpx.Response(200, json={"features": values})
    directory = AddressDirectory(transport=httpx.MockTransport(handler), clock=lambda: clock[0])
    return directory, clock, requests


def test_address_search_hierarchy_native_validation_and_privacy():
    directory, clock, requests = address_fixture()
    regions = directory.search("region", "Сам")
    region = regions["items"][0]
    assert directory.search("region", "Сам") == regions  # no extra HTTP request
    clock[0] += 2
    cities = directory.search("city", "Сам", region["id"])["items"]
    assert [c["name"] for c in cities] == ["Самара"]
    validated = directory.validate_profile({**PROFILE, "region": "подменено", "city": "подменено",
        "address": {"mode": "catalog", "region_id": region["id"], "city_id": cities[0]["id"]}})
    assert validated["region"] == "Самарская область" and validated["city"] == "Самара"
    with pytest.raises(AppError):
        directory.validate_profile({**PROFILE, "address": {"mode": "catalog",
            "region_id": regions["items"][1]["id"], "city_id": cities[0]["id"]}})
    with pytest.raises(AppError):
        directory.search("city", "Сам", "forged-id")
    assert set(requests[0].url.params) == {"countrycode", "limit", "lang", "q", "layer"}
    assert set(requests[1].url.params) == {"countrycode", "limit", "lang", "state", "city", "layer"}
    assert len(requests) == 2


def test_address_network_error_manual_mode_and_throttle():
    directory = AddressDirectory(transport=httpx.MockTransport(lambda _: httpx.Response(503)), clock=lambda: 0)
    with pytest.raises(AppError) as error:
        directory.search("region", "Сам")
    assert error.value.code == "address_network"
    with pytest.raises(AppError) as error:
        directory.search("region", "Моск")
    assert error.value.code == "rate_limit"
    profile = directory.validate_profile({**PROFILE, "address": {"mode": "manual"}})
    assert profile["address"]["verification"] == "manual_unverified"
    assert profile["city"] == PROFILE["city"]


def test_registration_stores_native_address_ids(tmp_path):
    directory, clock, _ = address_fixture()
    region = directory.search("region", "Сам")["items"][0]
    clock[0] += 2
    city = directory.search("city", "Сам", region["id"])["items"][0]
    app = Service(tmp_path, address_directory=directory)
    app.register("Родитель", PASSWORD, "PARENT")
    child = app.register("Ученик", CHILD_PASSWORD, "STUDENT", {**PROFILE, "address": {
        "mode": "catalog", "region_id": region["id"], "city_id": city["id"]}})
    app.logout()
    app.login(child["id"], CHILD_PASSWORD)
    saved = app.snapshot()["students"][0]["profile"]
    assert saved["address"]["city"]["id"] == city["id"]
    assert saved["address"]["source"] == "Photon / OpenStreetMap"
    app.logout()


def test_public_names_roles_do_not_replace_authorization(family):
    app, _, child, _ = family
    app.logout()
    accounts = app.status()["accounts"]
    assert next(p for p in accounts if p["id"] == child["id"])["name"] == "Ученик"
    envelope = json.loads(app.store.path.read_bytes())
    for p in envelope["directory"]["profiles"]:
        if p["id"] == child["id"]:
            p.update(name="Подменённый родитель", role="PARENT")
    atomic_write(app.store.path, encode(envelope))
    result = app.login(child["id"], CHILD_PASSWORD)
    assert result["directory_warning"]
    assert app.user()["role"] == "STUDENT"
    with pytest.raises(AppError):
        app.backup(PASSWORD)
    assert next(p for p in app.status()["accounts"] if p["id"] == child["id"])["role"] == "STUDENT"


def test_audit_separates_author_and_target_and_old_event(family):
    app, parent, child, _ = family
    event = next(e for e in app.snapshot()["audit"] if e["target"] == child["id"])
    assert event["actor"] == parent["id"]
    assert event["actor_display"]["name"] == "Родитель"
    assert event["target_display"]["name"] == "Ученик"
    assert event["label"] == "Создан профиль"
    with app.store.transaction():
        app.store.put("audit", "legacy-audit", {"id": "legacy-audit", "event": "register",
            "actor": parent["id"], "target": child["id"], "at": "2026-10-25T10:00:00+00:00"})
    event = next(e for e in app.snapshot()["audit"] if e["id"] == "legacy-audit")
    assert event["actor_display"]["name"] == "Родитель"
    assert event["target_display"]["name"] == "Ученик"


def test_four_subjects_geometry_bank_and_degree_verification():
    assert set(SUBJECTS) == {"algebra", "geometry", "physics", "informatics"}
    assert subjects_for_grade(6) == {"math": "Математика"}
    assert topic("math-equations")["subject"] == "algebra"
    geometry = [t for t in catalog() if t["subject"] == "geometry"]
    assert len(geometry) >= 3
    assert all(len(topic(t["id"])["tasks"]) == 3 for t in geometry)
    assert check_answer("55 градусов", "55 °")["status"] == "verified"
    assert check_answer("55 м/с", "55 °")["status"] == "incorrect"
    expected = [90-35, 180-65, 90-20-35, 180-70, 48, 180*2/5, 180-50-60, (180-40)/2, 90-27]
    answers = [answer for t in geometry for _, answer in topic(t["id"])["tasks"]]
    assert all(check_answer(str(value) + " °", answer)["status"] == "verified"
               for value, answer in zip(expected, answers, strict=True))


def test_homework_requires_subject_and_matching_topic(family):
    app, _, child, _ = family
    child_login(app, child)
    before = len(FakeProvider.calls)
    with pytest.raises(AppError, match="предмет"):
        app.check_homework("2+2=5")
    with pytest.raises(AppError, match="Тема"):
        app.prepare_homework("geometry", "math-equations")
    assert len(FakeProvider.calls) == before


def create_work(app, subject, text="Условие и решение", topic_id=None):
    work = app.prepare_homework(subject, topic_id)
    app.confirm_homework(work["id"], text)
    return work


def test_homework_does_not_reuse_different_mode_or_subject(family):
    app, _, child, _ = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    work = create_work(app, "geometry")
    before = len(FakeProvider.calls)
    with pytest.raises(AppError) as error:
        app.check_homework("Условие и решение", subject="geometry", homework=work["id"])
    assert error.value.code == "session_conflict" and len(FakeProvider.calls) == before
    app.pause(lesson["id"])
    app.check_homework("Условие и решение", subject="geometry", homework=work["id"])
    session = app.lesson(app.active_lesson)
    assert session["subject"] == "geometry" and session["topic"] is None and session["mode"] == "homework"
    assert "Геометрия" in FakeProvider.calls[-1][0]["content"]
    assert app.store.get("session", lesson["id"])["subject"] == "algebra"


def test_subject_change_preserves_old_result_and_clones_original(family, tmp_path):
    from tutor_ai.documents import import_file
    from tutor_ai.crypto import open_seal
    app, _, child, _ = family
    child_login(app, child)
    path = tmp_path / "original.txt"
    path.write_text("original attachment", encoding="utf-8")
    original = import_file(app, path)
    work = app.prepare_homework("algebra", homework=original["id"])
    app.confirm_homework(work["id"], "Условие и решение")
    app.check_homework("Условие и решение", subject="algebra", homework=work["id"])
    other = app.prepare_homework("geometry", homework=work["id"])
    assert other["id"] != work["id"] and not other["confirmed"]
    assert app.store.get("homework", work["id"])["subject"] == "algebra"
    assert app.store.get("homework", work["id"])["result"]
    stored = app.store.get("homework", other["id"])
    assert open_seal(app.store.attachment_key(), stored["original"], other["id"].encode()) == path.read_bytes()


def test_python_native_gate_uses_homework_owner_and_subject(family):
    app, _, child, _ = family
    other = app.register("Другой", CHILD_PASSWORD, "STUDENT", PROFILE)
    child_login(app, child)
    geometry = app.prepare_homework("geometry")
    with pytest.raises(AppError):
        app.analyze_code("print(1)", homework=geometry["id"])
    with pytest.raises(AppError):
        app.analyze_code("print(1)")
    work = app.prepare_homework("informatics")
    assert "не исполнялся" in app.analyze_code("print(1)", work["id"])["text"]
    app.logout()
    app.login(other["id"], CHILD_PASSWORD)
    with pytest.raises(AppError):
        app.analyze_code("print(1)", work["id"])


def test_independent_programs_and_lesson_snapshots(family):
    app, parent, child, _ = family
    child_login(app, child)
    algebra = app.request_program({"subject": "algebra", "title": "Алгебра"})
    geometry = app.request_program({"subject": "geometry", "title": "Геометрия"})
    app.logout()
    app.login(parent["id"], PASSWORD)
    app.approve_program(algebra["id"], True)
    app.approve_program(geometry["id"], True)
    child_login(app, child)
    lesson = app.start_lesson("geometry-basics")
    assert lesson["program_snapshot"]["title"] == "Геометрия"
    assert app.store.get("program", child["id"] + ":algebra")["title"] == "Алгебра"


def make_legacy(app, child):
    """Construct an actual v1 encrypted container, not a mock migration flag."""
    with app.store.db:
        from tests.legacy_schema import before_v4
        before_v4(app.store.db)
        app.store.db.execute("DELETE FROM schema_migrations WHERE version>=2")
        app.store.db.execute("ALTER TABLE users DROP COLUMN design")
        app.store.db.execute("ALTER TABLE users DROP COLUMN profile_revision")
        app.store.put("session", "old-session", {"id": "old-session", "student": child["id"],
            "subject": "math", "topic": "math-equations", "title": "Старое занятие", "created": "2026-10-25",
            "status": "complete", "program_snapshot": {"subject": "math", "title": "Старый учебник"}}, child["id"])
        app.store.put("session", "unknown-session", {"id": "unknown-session", "student": child["id"],
            "subject": "math", "topic": "unknown", "title": "Неизвестная тема", "created": "2026-10-25",
            "status": "complete", "program_snapshot": {}}, child["id"])
        app.store.put("knowledge", child["id"] + ":math-equations", {"topic": "math-equations",
            "attempts_count": 5, "correct_count": 3, "mastery_score": 50}, child["id"])
        app.store.put("knowledge_event", "legacy-event", {"topic": "math-equations"}, child["id"])
        app.store.put("program", child["id"], {"subject": "math", "title": "Старый учебник"}, child["id"])
    envelope = copy.deepcopy(app.store.envelope)
    envelope.pop("directory", None)
    envelope.pop("directory_mac", None)
    envelope["payload"] = seal(app.store.key, app.store.db.serialize(), envelope["vault"].encode())
    raw = encode(envelope)
    atomic_write(app.store.path, raw)
    app.actor = None
    app.store.close()
    return raw


def test_v1_migration_is_atomic_idempotent_and_preserves_history(family):
    app, parent, child, _ = family
    raw = make_legacy(app, child)
    assert all(p["name"] is None for p in app.status()["accounts"])
    app.login(parent["id"], PASSWORD)
    student = app.snapshot()["students"][0]
    sessions = {s["id"]: s for s in student["sessions"]}
    assert sessions["old-session"]["subject"] == "math"
    assert sessions["old-session"]["catalog_subject"] == "algebra"
    assert sessions["unknown-session"]["catalog_subject"] == "math_archive"
    assert sessions["old-session"]["program_snapshot"] == {"subject": "math", "title": "Старый учебник"}
    assert student["knowledge"][0]["attempts_count"] == 5
    assert student["program"]["needs_subject_confirmation"]
    assert len(app.store.all("knowledge_event")) == 1
    backups = list((app.store.root / "backups").glob("before-migration-v1-*.aead"))
    assert len(backups) == 1 and backups[0].read_bytes() == raw
    app.logout()
    app.login(parent["id"], PASSWORD)
    assert len(list((app.store.root / "backups").glob("before-migration-v1-*.aead"))) == 1
    assert len(app.store.all("knowledge_event")) == 1
    assert all(p["name"] for p in app.status()["accounts"])


def test_failed_migration_keeps_original_container(family, monkeypatch):
    app, parent, child, _ = family
    raw = make_legacy(app, child)
    real_write = atomic_write
    def fail_vault(path, data):
        if path == app.store.path:
            raise OSError("synthetic migration failure")
        real_write(path, data)
    monkeypatch.setattr("tutor_ai.storage.atomic_write", fail_vault)
    with pytest.raises(AppError):
        app.login(parent["id"], PASSWORD)
    assert app.store.path.read_bytes() == raw


def test_rename_and_delete_sync_public_directory_and_keep_actor_identity(family):
    app, parent, child, _ = family
    app.rename_profile("Новое имя")
    assert next(p for p in app.status()["accounts"] if p["id"] == parent["id"])["name"] == "Новое имя"
    event = next(e for e in app.snapshot()["audit"] if e["event"] == "register" and e["target"] == child["id"])
    assert event["actor_display"]["name"] == "Родитель"
    assert event["actor_current_name"] == "Новое имя"
    app.delete_student(child["id"], child["id"])
    assert child["id"] not in {p["id"] for p in app.status()["accounts"]}


def test_restore_legacy_backup_migrates_before_replacing(family):
    import secrets
    from tutor_ai.crypto import wrap
    app, parent, child, _ = family
    legacy = make_legacy(app, child)
    archive_key = secrets.token_bytes(32)
    record = {"format": 1, "mode": "password", "key": wrap(archive_key, PASSWORD, b"aitutor-backup-key-v1"),
              "content": seal(archive_key, legacy, b"aitutor-backup-v1")}
    archive_path = app.store.root / "backups" / "legacy.aitbackup"
    atomic_write(archive_path, encode(record))
    app.login(parent["id"], PASSWORD)
    app.set_controls(child["id"], 10)
    app.restore("legacy.aitbackup", PASSWORD, parent["id"], PASSWORD)
    app.login(parent["id"], PASSWORD)
    assert app.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 4
    assert app.controls(child["id"])["minutes"] == 60
    assert app.snapshot()["students"][0]["knowledge"][0]["attempts_count"] == 5
    assert all(p["name"] for p in app.status()["accounts"])


def test_homework_failure_does_not_start_empty_session(family):
    app, _, child, _ = family
    child_login(app, child)
    work = create_work(app, "geometry")
    class FailingProvider(FakeProvider):
        def send_message(self, messages):
            raise AppError("Сервис недоступен", "network")
    app.provider_factory = FailingProvider
    with pytest.raises(AppError):
        app.check_homework("Условие и решение", subject="geometry", homework=work["id"])
    assert app.active_lesson is None
    assert app.store.all("session", child["id"]) == []
    assert app.store.get("homework", work["id"])["confirmed"]


def test_retried_homework_is_idempotent(family):
    app, _, child, _ = family
    child_login(app, child)
    work = create_work(app, "geometry")
    first = app.check_homework("Условие и решение", subject="geometry", homework=work["id"])
    before = len(FakeProvider.calls)
    second = app.check_homework("Условие и решение", subject="geometry", homework=work["id"])
    assert first == second and len(FakeProvider.calls) == before
    assert len(app.lesson(app.active_lesson)["messages"]) == 2
