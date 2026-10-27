"""Independent whole-feature and boundary probes; synthetic data only."""
import copy
import io
import pytest
from pathlib import Path
from aitutor.documents import import_file, MAX_FILE
from aitutor.education import TOPICS
from aitutor.errors import AppError
from aitutor.crypto import open_seal
from tests.test_application import family as family_fixture, child_login

family = family_fixture

@pytest.mark.parametrize("topic", TOPICS, ids=lambda t:t["id"])
def test_every_catalog_topic_can_complete(family, topic):
    app, _, child, _ = family
    child_login(app, child)
    session = app.start_lesson(topic["id"])
    for index, (_, expected) in enumerate(topic["tasks"]):
        result = app.answer(session["id"], expected, "extended-answer-" + str(index))
        assert result["check"]["status"] == "verified"
    assert result["session"]["status"] == "complete"
    assert result["session"]["correct"] == 3
    assert app.store.all("knowledge", child["id"])[0]["subject"] == topic["subject"]

@pytest.mark.parametrize("ext", ["txt","py","csv","pdf","docx","png","jpg","webp"])
def test_document_formats_and_encrypted_original(family, tmp_path, ext):
    app, _, child, _ = family
    child_login(app, child)
    path = tmp_path / ("qa." + ext)
    if ext in ("txt","py","csv"):
        path.write_text("QA original: x = 3 + 4", encoding="utf-8")
    elif ext == "pdf":
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(path)
    elif ext == "docx":
        from docx import Document
        doc = Document()
        doc.add_paragraph("QA Document")
        doc.save(path)
    else:
        from PySide6.QtGui import QImage, QColor
        image = QImage(16,16,QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        assert image.save(str(path))
    item = import_file(app,path)
    stored = app.store.get("homework",item["id"])
    assert open_seal(app.store.attachment_key(),stored["original"],item["id"].encode()) == path.read_bytes()
    assert "original" not in item and item["confirmed"] is False
    if ext in ("pdf","docx","png","jpg","webp"):
        assert item["warning"]

def test_oversized_document_rejected_without_creating_homework(family,tmp_path):
    app,_,child,_ = family
    child_login(app,child)
    p=tmp_path/"large.txt"
    p.write_bytes(b"x"*(MAX_FILE+1))
    before=app.store.all("homework")
    with pytest.raises(AppError):
        import_file(app,p)
    assert app.store.all("homework") == before

def test_final_answer_write_failure_retains_active_timer(family,monkeypatch):
    app,_,child,clock=family
    child_login(app,child)
    session=app.start_lesson("math-equations")
    app.answer(session["id"],"5","extended-first-answer")
    app.answer(session["id"],"4","extended-second-answer")
    original=app.store.get("session",session["id"])
    real_save=app.store.save
    def fail_final():
        # active() first writes its time checkpoint. Fail only final answer publication.
        current=app.store.get("session",session["id"])
        if current["status"] == "complete":
            raise OSError("QA synthetic disk failure on final answer")
        return real_save()
    monkeypatch.setattr(app.store,"save",fail_final)
    with pytest.raises(OSError):
        app.answer(session["id"],"-3","extended-final-answer")
    assert app.store.get("session",session["id"]) == original
    assert app.active_lesson == session["id"], {
        "persisted_status":app.store.get("session",session["id"])["status"],
        "active_lesson":app.active_lesson}
    clock[0]+=20
    app.tick()
    assert app.daily(child["id"])["seconds"] >= 20

def test_pause_historical_session_does_not_disable_current_timer(family):
    app,_,child,clock=family
    child_login(app,child)
    older=app.start_lesson("math-equations")
    app.pause(older["id"])
    current=app.start_lesson("physics-speed")
    app.dispatch("pause",{"session":older["id"]})
    clock[0]+=30
    app.tick()
    assert app.daily(child["id"])["seconds"] >= 30, {
        "active_lesson":app.active_lesson,"current_status":app.store.get("session",current["id"])["status"],
        "daily_seconds":app.daily(child["id"])["seconds"]}

def test_delayed_tick_charges_only_three_minutes_of_inactivity(family):
    app,_,child,clock=family
    child_login(app,child)
    session=app.start_lesson("math-equations")
    clock[0]+=600
    app.tick()
    stored=app.store.get("session",session["id"])
    assert stored["status"] == "paused"
    assert stored["seconds"] <= 180, {"charged_seconds":stored["seconds"],"idle_threshold":180}

def test_long_text_import_is_complete_or_warns_about_truncation(family,tmp_path):
    app,_,child,_=family
    child_login(app,child)
    p=tmp_path/"long-homework.txt"
    text="x"*30000+"\nFINAL QUESTION: solve 3x+5=20"
    p.write_text(text,encoding="utf-8")
    result=import_file(app,p)
    assert result["text"] == text or result["warning"], {
        "file_characters":len(text),"imported_characters":len(result["text"]),
        "warning":result["warning"],"tail_present":"FINAL QUESTION" in result["text"]}
