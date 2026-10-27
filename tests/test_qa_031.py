"""Regression for QA-001..004 and non-destructive historical compatibility."""
import copy

import pytest

from tutor_ai.errors import AppError
from tests.test_application import PASSWORD, child_login, family as family_fixture
from tests.test_application import CHILD_PASSWORD
from tests.qa_fixtures import foreign_backup

family = family_fixture


@pytest.mark.parametrize("status", ["active", "paused", "complete"])
@pytest.mark.parametrize("extra", [{}, {"messages": []}, {"messages": [{}]}, {"messages": [{"text": " \n"}]},
                                  {"messages": [{"usage": {"tokens": 10}}], "seconds": 123},
                                  {"task": " ", "total": 0, "result": {"usage": 10}}])
def test_empty_archives_never_depend_on_status(family, status, extra):
    app, _, child, _ = family
    record = {"id": "empty", "subject": "math", "topic": "unknown", "status": status,
              "created": "2020-01-01", **extra}
    with app.store.transaction():
        app.store.put("session", "empty", record, child["id"])
    assert app.snapshot()["students"][0]["archives"]["history"] == {}
    assert app.store.get("session", "empty") == record


@pytest.mark.parametrize("extra", [{"messages": [{"text": "0"}]}, {"task": "Сохранённое задание"},
                                  {"total": 1, "correct": 0}, {"check": {"status": "incorrect"}},
                                  {"result": {"correct": False}}])
def test_meaningful_paused_archive_retains_content(family, extra):
    app, _, child, _ = family
    with app.store.transaction():
        app.store.put("session", "saved", {"id": "saved", "subject": "math", "topic": "old",
            "created": "2020-01-01", "status": "paused", **extra}, child["id"])
    assert app.snapshot()["students"][0]["archives"]["history"] == {"math_archive": "Математика — архив"}


@pytest.mark.parametrize(("record", "expected", "conflict"), [
    ({"subject": "physics", "topic": "retired-physics"}, "physics", False),
    ({"subject": "informatics", "topic": "retired"}, "informatics", False),
    ({"subject": "geometry", "topic": "retired"}, "geometry", False),
    ({"subject": "biology", "topic": "retired", "subject_label": "Биология — архив"}, "biology", False),
    ({"subject": "math", "topic": "math-equations"}, "algebra", False),
    ({"subject": "math", "topic": "unknown"}, "math_archive", False),
    ({"topic": "math-equations"}, "algebra", False),
    ({"topic": "unknown"}, "unclassified", False),
    ({"subject": "physics", "topic": "math-equations"}, "physics", True),
])
def test_classification_preserves_explicit_subject_and_original(family, record, expected, conflict):
    app, _, child, _ = family
    original = {**record, "attempts_count": 2, "correct_count": 1, "mastery_score": 50, "confidence": .5}
    with app.store.transaction():
        app.store.put("knowledge", "legacy", original, child["id"])
    snapshot = app.snapshot()["students"][0]
    item = snapshot["knowledge"][0]
    assert item["catalog_subject"] == item["subject"] == expected
    assert item["source_subject"] == record.get("subject")
    assert item["classification_conflict"] is conflict
    assert item["attempts_count"] == 2 and item["mastery_score"] == 50
    assert app.store.get("knowledge", "legacy") == original
    if expected == "physics":
        assert not snapshot["archives"]["knowledge"]


@pytest.mark.parametrize("subjects", [["physics"], ["physics", "informatics"]])
def test_missing_subject_uses_unambiguous_owned_evidence(family, subjects):
    app, _, child, _ = family
    with app.store.transaction():
        app.store.put("knowledge", "old", {"topic": "old", "attempts_count": 1}, child["id"])
        for index, subject in enumerate(subjects):
            app.store.put("knowledge_event", str(index), {"topic": "old", "subject": subject,
                          "status": "incorrect"}, child["id"])
    actual = app.snapshot()["students"][0]["knowledge"][0]
    assert actual["subject"] == (subjects[0] if len(subjects) == 1 else "unclassified")
    assert actual["classification_conflict"] is (len(subjects) > 1)


def test_new_observations_keep_subject_after_catalog_removal(family, monkeypatch):
    app, _, child, _ = family
    child_login(app, child)
    lesson = app.start_lesson("physics-speed")
    app.answer(lesson["id"], "100 м/с", "qa031-stable-operation-1")
    original = copy.deepcopy(app.store.all("knowledge", child["id"]))
    assert original[0]["subject"] == "physics"
    event = app.store.all("knowledge_event", child["id"])[0]
    assert event["subject"] == "physics" and event["session"] == lesson["id"]
    monkeypatch.setattr("tutor_ai.service.catalog", lambda: [])
    assert app.snapshot()["students"][0]["knowledge"][0]["subject"] == "physics"
    assert app.store.all("knowledge", child["id"]) == original


def test_restore_rotates_context_even_for_same_vault_and_actor(family):
    app, parent, _, _ = family
    context = app.status()["context"]
    vault = app.store.envelope["vault"]
    assert app.snapshot()["context"] == context
    backup = app.backup(PASSWORD)["file"]
    app.restore(backup, PASSWORD, parent["id"], PASSWORD)
    restored = app.status()["context"]
    assert restored != context and not app.status()["authenticated"]
    app.login(parent["id"], PASSWORD)
    assert app.status()["context"] not in (context, restored)
    assert app.store.envelope["vault"] == vault


def test_failed_restore_keeps_context_and_all_working_records(family):
    app, parent, _, _ = family
    before = {"context": app.status()["context"], "users": app.store.db.execute("SELECT * FROM users").fetchall(),
              "records": app.store.db.execute("SELECT * FROM records").fetchall(), "raw": app.store.path.read_bytes()}
    path = app.store.root / "backups" / "broken.aitbackup"
    path.write_bytes(b"broken")
    with pytest.raises(AppError):
        app.restore(path.name, PASSWORD, parent["id"], PASSWORD)
    assert app.status()["context"] == before["context"]
    assert app.store.path.read_bytes() == before["raw"]
    assert app.store.db.execute("SELECT * FROM users").fetchall() == before["users"]
    assert app.store.db.execute("SELECT * FROM records").fetchall() == before["records"]


def test_open_v3_never_rewrites_subjects_or_changes_schema(family):
    app, parent, child, _ = family
    with app.store.transaction():
        app.store.put("knowledge", "past", {"topic": "retired", "subject": "physics", "attempts_count": 1}, child["id"])
    original = copy.deepcopy(app.store.all("knowledge"))
    app.logout()
    app.login(parent["id"], PASSWORD)
    assert app.store.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 3
    app.snapshot()
    assert app.store.all("knowledge") == original


def test_theme_write_failure_preserves_saved_preferences(family, monkeypatch):
    app, _, _, _ = family
    before = app.user()
    raw = app.store.path.read_bytes()
    def fail(*_):
        raise OSError("synthetic theme disk failure")
    monkeypatch.setattr("tutor_ai.storage.atomic_write", fail)
    with pytest.raises(OSError):
        app.set_theme("dark", "modern")
    assert app.user() == before and app.store.path.read_bytes() == raw


def test_foreign_restore_with_colliding_ids_invalidates_context(family, tmp_path):
    app, parent, child, _ = family
    vault, context = app.store.envelope["vault"], app.context
    with app.store.transaction():
        app.store.put("session", "late", {"id": "late", "student": child["id"], "subject": "physics",
            "messages": [{"text": "Only original vault"}], "created": "2026-10-26"}, child["id"])
    filename, other_vault = foreign_backup(app, tmp_path / "foreign", {
        parent["id"]: PASSWORD, child["id"]: CHILD_PASSWORD}, PASSWORD)
    app.restore(filename, PASSWORD, parent["id"], PASSWORD)
    assert app.context != context and other_vault != vault
    app.login(parent["id"], PASSWORD)
    assert app.store.envelope["vault"] == other_vault
    assert app.user()["id"] == parent["id"] and app.user()["name"].startswith("Foreign ")
    assert app.store.get("session", "late") is None
