"""Independent QA probes. Run from project root; synthetic isolated data only."""
import copy
import json
import pytest
from aitutor.service import Service
from aitutor.documents import import_file
from tests.test_application import PASSWORD, CHILD_PASSWORD, PROFILE, FakeProvider, child_login
from tests.test_feedback_03 import legacy_v2, edit
from tests.test_feedback_02 import make_legacy

@pytest.fixture
def family(tmp_path):
    app = Service(tmp_path / "app-data", provider_factory=FakeProvider)
    parent = app.register("QA Parent", PASSWORD, "PARENT")
    child = app.register("QA Student", CHILD_PASSWORD, "STUDENT", copy.deepcopy(PROFILE))
    app.save_provider({"kind": "ollama", "model": "qa-mock-only", "revision": 0})
    yield app, parent, child
    app.store.close()

def test_empty_completed_session_does_not_create_archive(family):
    app, _, child = family
    with app.store.transaction():
        app.store.put("session", "empty", {"id": "empty", "subject": "math",
            "topic": "unknown", "created": "2020-01-01", "status": "complete",
            "messages": [], "task": "", "total": 0}, child["id"])
    actual = app.snapshot()["students"][0]["archives"]["history"]
    assert actual == {}, actual

def test_legacy_known_homework_maps_to_algebra(family):
    app, parent, child = family
    with app.store.transaction():
        app.store.put("homework", "old", {"id": "old", "subject": "math",
            "topic": "math-equations", "text": "3x + 5 = 20",
            "created": "2020-01-01"}, child["id"])
    make_legacy(app, child)
    app.login(parent["id"], PASSWORD)
    student = app.snapshot()["students"][0]
    assert student["homework"][0].get("catalog_subject") == "algebra", student["homework"][0]

def test_legacy_unknown_homework_uses_same_archive_id_as_history(family):
    app, parent, child = family
    with app.store.transaction():
        app.store.put("homework", "old", {"id": "old", "subject": "math",
            "topic": "unknown", "text": "old problem", "created": "2020-01-01"}, child["id"])
    make_legacy(app, child)
    app.login(parent["id"], PASSWORD)
    actual = app.snapshot()["students"][0]["archives"]["homework"]
    assert actual == {"math_archive": "Математика — архив"}, actual

def test_retired_physics_topic_not_reclassified_as_math(family):
    app, _, child = family
    with app.store.transaction():
        app.store.put("knowledge", "old-physics", {"topic": "old-physics",
            "subject": "physics", "attempts_count": 2, "correct_count": 1,
            "mastery_score": 50, "confidence": 0.5}, child["id"])
    actual = app.snapshot()["students"][0]
    assert actual["knowledge"][0]["subject"] == "physics", actual["knowledge"][0]
    assert "math_archive" not in actual["archives"]["knowledge"]

def test_v2_migration_and_school_edit_preserve_complete_content(family, tmp_path):
    app, parent, child = family
    child_login(app, child)
    lesson = app.start_lesson("math-equations")
    app.answer(lesson["id"], "5", "qa-operation-001")
    app.pause(lesson["id"])
    source = tmp_path / "attachment.txt"
    source.write_text("QA attachment: 2+2=4", encoding="utf-8")
    import_file(app, source)
    before = {k: app.store.all(k) for k in ("session","knowledge","homework","operation")}
    links = [tuple(r) for r in app.store.db.execute("SELECT * FROM links")]
    legacy_v2(app)
    app.login(parent["id"], PASSWORD)
    edit(app, child["id"], school="QA New School")
    assert all(app.store.all(k) == v for k,v in before.items())
    assert [tuple(r) for r in app.store.db.execute("SELECT * FROM links")] == links
    assert app.store.user(child["id"])["design"] == "modern"

def test_invalid_profile_changes_are_atomic(family):
    app, _, child = family
    before = app.get_profile(child["id"])
    for changes in ({"name": " "}, {"school": ""}, {"region": "x"*201},
                    {"name": "valid", "role": "PARENT"}):
        from aitutor.errors import AppError
        with pytest.raises(AppError):
            app.save_profile(child["id"], before["revision"], changes)
        assert app.get_profile(child["id"]) == before

def test_catalog_has_four_subjects_and_archive_cannot_start(family):
    app, _, child = family
    from aitutor.errors import AppError
    child_login(app, child)
    assert set(app.snapshot()["subjects"]) == {"algebra","geometry","physics","informatics"}
    with pytest.raises(AppError):
        app.start_lesson("math_archive")
    with pytest.raises(AppError):
        app.prepare_homework("math_archive")

def test_corrupt_and_future_backup_do_not_replace_working_data(family):
    app, parent, _ = family
    backup = app.backup(PASSWORD)["file"]
    path = app.store.root / "backups" / backup
    original = app.store.path.read_bytes()
    raw = json.loads(path.read_bytes())
    raw["format"] = 999
    path.write_text(json.dumps(raw), encoding="utf-8")
    from aitutor.errors import AppError
    with pytest.raises(AppError):
        app.restore(backup, PASSWORD, parent["id"], PASSWORD)
    assert app.store.path.read_bytes() == original
    path.write_bytes(b"broken")
    with pytest.raises(AppError):
        app.restore(backup, PASSWORD, parent["id"], PASSWORD)
    assert app.store.path.read_bytes() == original
