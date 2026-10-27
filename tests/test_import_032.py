"""Agreed policy A: reject oversized text, retain originals and legacy history."""
import copy
import io

import pytest

from tutor_ai.crypto import open_seal, seal
from tutor_ai.documents import extract_material, import_file
from tutor_ai.errors import AppError
from tests.test_application import FakeProvider, child_login, family as family_fixture

family = family_fixture


@pytest.mark.parametrize("ext", ["txt", "py", "csv"])
@pytest.mark.parametrize("length", [29999, 30000, 30001])
def test_text_boundaries_reject_without_partial_work(family, tmp_path, ext, length):
    app, _, child, _ = family
    child_login(app, child)
    path = tmp_path / ("work." + ext)
    text = "я" * length
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    before = app.store.all("homework")
    if length > 30000:
        with pytest.raises(AppError) as error:
            import_file(app, path)
        assert error.value.code == "text_limit" and "Разбейте" in str(error.value)
        assert app.store.all("homework") == before
    else:
        item = import_file(app, path)
        assert item["text"] == text and item["extraction"]["characters"] == length
        assert item["extraction"]["status"] == "complete"
        stored = app.store.get("homework", item["id"])
        assert open_seal(app.store.attachment_key(), stored["original"], item["id"].encode()) == path.read_bytes()


def test_unicode_code_points_and_newlines_are_consistent():
    text = "😀" * 30000
    result = extract_material(text.encode(), ".txt")
    assert result["text"] == text and result["extraction"]["characters"] == 30000
    with pytest.raises(AppError):
        extract_material((text + "😀").encode(), ".txt")
    result = extract_material(b"line\r\nother\rlast", ".txt")
    assert result["text"] == "line\nother\nlast"
    assert result["extraction"]["characters"] == len(result["text"])


def test_bad_utf8_is_explicitly_uncertain():
    result = extract_material(b"question \xff", ".txt")
    assert result["extraction"]["status"] == "uncertain"
    assert "UTF-8" in result["warning"] and "\ufffd" in result["text"]


def test_qa008_original_fixture_has_agreed_explicit_refusal(family, tmp_path):
    app, _, child, _ = family
    child_login(app, child)
    source = tmp_path / "long-homework.txt"
    source.write_text("x" * 30000 + "\nFINAL QUESTION: solve 3x+5=20", encoding="utf-8")
    before = copy.deepcopy(app.store.all("homework"))
    with pytest.raises(AppError) as error:
        import_file(app, source)
    assert error.value.code == "text_limit" and "Разбейте" in str(error.value)
    assert app.store.all("homework") == before


def pdf_bytes(length):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 10 Tf 10 700 Td (" + b"x" * length + b") Tj ET")
    page[NameObject("/Contents")] = content
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("length", [6000, 30000, 30001])
def test_pdf_has_no_hidden_per_page_slice(length):
    raw = pdf_bytes(length)
    if length > 30000:
        with pytest.raises(AppError, match="Разбейте"):
            extract_material(raw, ".pdf")
    else:
        result = extract_material(raw, ".pdf")
        assert result["text"] == "x" * length
        assert result["extraction"]["characters"] == length


@pytest.mark.parametrize("length", [30000, 30001])
def test_docx_limit_includes_all_text(length):
    from docx import Document
    document = Document()
    document.add_paragraph("x" * length)
    buffer = io.BytesIO()
    document.save(buffer)
    if length > 30000:
        with pytest.raises(AppError, match="Разбейте"):
            extract_material(buffer.getvalue(), ".docx")
    else:
        assert extract_material(buffer.getvalue(), ".docx")["text"] == "x" * length


def legacy_work(app, child, raw, *, text="old extract", filename="old.txt"):
    hid = "legacy-file-work"
    item = {"id": hid, "student": child["id"], "created": "2026-10-25", "subject": "algebra", "topic": None,
            "text": text, "filename": filename, "confirmed": True, "result": "Исторический ответ ИИ",
            "warning": "", "original": seal(app.store.attachment_key(), raw, hid.encode())}
    with app.store.transaction():
        app.store.put("homework", hid, item, child["id"])
    return copy.deepcopy(item)


@pytest.mark.parametrize("command", ["prepare", "confirm", "check"])
def test_legacy_long_file_cannot_bypass_limit_and_remains_unchanged(family, command):
    app, _, child, _ = family
    child_login(app, child)
    raw = ("x" * 30000 + "\nFINAL QUESTION").encode()
    old = legacy_work(app, child, raw, text="x" * 30000)
    before_calls = len(FakeProvider.calls)
    with pytest.raises(AppError) as error:
        if command == "prepare":
            app.prepare_homework("geometry", homework=old["id"])
        elif command == "confirm":
            app.confirm_homework(old["id"], old["text"])
        else:
            app.check_homework(old["text"], "algebra", old["id"])
    assert error.value.code == "text_limit"
    assert app.store.all("homework") == [old] and not app.store.all("session")
    assert len(FakeProvider.calls) == before_calls
    assert open_seal(app.store.attachment_key(), old["original"], old["id"].encode()) == raw


def test_legacy_shorter_original_gets_new_reviewable_version(family):
    app, _, child, _ = family
    child_login(app, child)
    original = pdf_bytes(6000)
    old = legacy_work(app, child, original, text="x" * 5000, filename="old.pdf")
    with pytest.raises(AppError) as error:
        app.confirm_homework(old["id"], old["text"])
    assert error.value.code == "source_review_required"
    revised = app.prepare_homework("algebra", homework=old["id"])
    assert revised["id"] != old["id"] and revised["previous_homework"] == old["id"]
    assert revised["text"] == "x" * 6000 and revised["text_reextracted"] and not revised["confirmed"]
    assert app.store.get("homework", old["id"]) == old
    again = app.prepare_homework("algebra", homework=revised["id"])
    assert again["id"] == revised["id"] and not again["text_reextracted"]
    app.confirm_homework(revised["id"], revised["text"])
    assert app.store.get("homework", old["id"]) == old
    stored = app.store.get("homework", revised["id"])
    assert open_seal(app.store.attachment_key(), stored["original"], stored["id"].encode()) == original


def test_exact_legacy_boundary_is_not_assumed_truncated(family):
    app, _, child, _ = family
    child_login(app, child)
    old = legacy_work(app, child, b"x" * 30000, text="x" * 30000)
    revised = app.prepare_homework("algebra", homework=old["id"])
    assert revised["extraction"]["status"] == "complete" and revised["text"] == old["text"]
    assert app.store.get("homework", old["id"]) == old


def test_missing_legacy_original_does_not_claim_full_extraction(family):
    app, _, child, _ = family
    child_login(app, child)
    with app.store.transaction():
        app.store.put("homework", "lost", {"id": "lost", "student": child["id"], "filename": "lost.txt",
            "subject": "algebra", "topic": None, "text": "fragment", "confirmed": True}, child["id"])
    before = app.store.all("homework")
    with pytest.raises(AppError) as error:
        app.prepare_homework("algebra", homework="lost")
    assert error.value.code == "source_unavailable" and app.store.all("homework") == before
