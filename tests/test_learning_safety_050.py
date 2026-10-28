import json
import socket

import httpx
import pytest

from tutor_ai.errors import AppError
from tutor_ai.providers import Provider
from tutor_ai.sources import PublicConnection, fetch
from tutor_ai.verification import formal_value, inspect_steps
from tests.test_application import family as family_fixture, child_login
from tests.test_learning_050 import command, approved_bank

family = family_fixture


@pytest.mark.parametrize(
    "solution,status",
    [
        ("3x+5=20\n3x=15\nx=5", "verified"),
        ("3x+5=20\n3x=25\nx=5", "incorrect"),
        ("(x+1)/2=3\nx+1=6\nx=5", "verified"),
        ("x/0=1\nx=5", "unknown"),
        ('__import__("os").system("whoami")=0\nx=0', "unknown"),
        ("x*x=4\nx=2", "unknown"),
        ("0*x=0\nx=0", "incorrect"),
    ],
)
def test_formal_steps(solution, status):
    assert inspect_steps(solution)["status"] == status


def test_formal_does_not_trust_expected_answer():
    assert formal_value("Вычисли 2 + 3.", "5")["status"] == "verified"
    assert formal_value("Вычисли 2 + 3.", "6")["status"] == "incorrect"
    assert formal_value("Докажи теорему", "5")["status"] == "unknown"
    assert formal_value("Вычисли 50 + 5.", "x=5x=5")["status"] == "unknown"


def test_decimal_literals_are_not_rounded_by_ast_float():
    from tutor_ai.education import arithmetic
    from fractions import Fraction

    assert arithmetic("0.100000000000000000001") == Fraction(100000000000000000001, 10**21)
    assert formal_value("Вычисли 0.1 + 0.2.", "0.300000000000000000001")["status"] == "incorrect"
    assert inspect_steps("x=0.100000000000000000001\nx=0.1")["status"] == "incorrect"
    with pytest.raises(AppError):
        arithmetic("1e-999999999")


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1", "192.168.1.5"]
)
def test_public_loader_rejects_private_dns(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
    )
    with pytest.raises(AppError):
        PublicConnection("example.org").connect()


@pytest.mark.parametrize(
    "url",
    ["http://example.org", "file:///C:/test", "https://user:pass@example.org", "https://example.org:9443"],
)
def test_public_loader_rejects_unsafe_urls(url):
    with pytest.raises(AppError):
        fetch(url)


def test_search_does_not_publish_unrelated_results(monkeypatch):
    from tutor_ai import sources

    raw = (
        "<rss><channel><item><title>Google Maps tips</title><link>https://example.org/maps</link></item>"
        "<item><title>Федеральная рабочая программа: алгебра</title>"
        "<link>https://example.org/algebra</link></item></channel></rss>"
    ).encode()
    monkeypatch.setattr(sources, "fetch", lambda *args: (raw, "application/xml", args[0]))
    results = sources.search("федеральная рабочая программа алгебра 7 класс")
    assert len(results) == 1 and results[0]["url"].endswith("/algebra")


def test_gigachat_upload_chat_cleanup_transport():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/oauth"):
            return httpx.Response(200, json={"access_token": "synthetic-token", "expires_at": 9999999999999})
        if request.url.path.endswith("/files"):
            assert b"general" in request.content and b"page.png" in request.content
            return httpx.Response(200, json={"id": "synthetic-file-id"})
        if request.url.path.endswith("/chat/completions"):
            assert json.loads(request.content)["messages"][-1]["attachments"] == ["synthetic-file-id"]
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "Распознанный текст"}}], "usage": {}}
            )
        return httpx.Response(200, json={"deleted": True})

    client = Provider(
        {"kind": "gigachat", "model": "test", "secret": "synthetic-basic-key"},
        transport=httpx.MockTransport(handler),
    )
    result = client.send_multimodal(
        [{"role": "user", "content": "Распознай"}], [{"bytes": b"synthetic-image", "mime": "image/png"}]
    )
    client.close()
    assert result["text"] == "Распознанный текст" and not result["cleanup_failed"]
    assert paths[-1].endswith("/synthetic-file-id/delete")
    assert sum(p.endswith("/oauth") for p in paths) == 1


def test_gigachat_cleanup_after_chat_error():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/oauth"):
            return httpx.Response(200, json={"access_token": "fake", "expires_at": 9999999999999})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"id": "file-id"})
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(429, json={})
        return httpx.Response(200, json={})

    client = Provider(
        {"kind": "gigachat", "model": "test", "secret": "fake"}, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AppError):
        client.send_multimodal(
            [{"role": "user", "content": "OCR"}], [{"bytes": b"fake", "mime": "image/png"}]
        )
    client.close()
    assert paths[-1].endswith("/file-id/delete")


def test_q9_alternative_does_not_resolve_original_unknown(family):
    app, parent, child, _ = family
    state, col = approved_bank(app, child)
    child_login(app, child)
    original = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )["id"]
    view = command(app, "attempt", attempt=original)
    command(
        app,
        "submit",
        attempt=original,
        slot=view["slots"][0]["id"],
        answer="Первый ответ",
        expected_revision=0,
    )
    view = command(app, "attempt", attempt=original)
    command(app, "pause", attempt=original, expected_revision=view["revision"])
    before = command(app, "attempt", attempt=original)
    alternative = command(
        app, "alternative", attempt=original, collection=col, reason="Новое задание по просьбе ученика"
    )
    after = command(app, "attempt", attempt=original)
    assert after == before and alternative["id"] != original
    assert command(app, "attempt", attempt=alternative["id"])["body"]["alternative"]["attempt"] == original


def test_accepted_answer_parse_error_and_foreign_review(family):
    app, parent, child, _ = family
    state, col = approved_bank(app, child)
    child_login(app, child)
    aid = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )["id"]
    view = command(app, "attempt", attempt=aid)
    with pytest.raises(AppError):
        command(app, "submit", attempt=aid, slot=view["slots"][0]["id"], answer="", expected_revision=0)
    assert command(app, "attempt", attempt=aid)["result"]["S"] == 8
    accepted = command(
        app,
        "submit",
        attempt=aid,
        slot=view["slots"][0]["id"],
        answer="Фото плохо распознано",
        expected_revision=0,
    )
    assert accepted["result"]["U"] == 1 and accepted["result"]["S"] == 7
    c = app.learning_engine.components(aid)[0]
    with pytest.raises(AppError):
        command(
            app,
            "review",
            attempt=aid,
            answer=c["answer"],
            criterion=c["criterion"],
            code="C",
            reason="Я сам",
            scope="Всё",
            expected_revision=0,
        )


def test_new_image_consent_default_false(family):
    app, parent, child, _ = family
    assert app.store.get("provider", "family").get("allow_images") is False


def test_original_preview_is_authorized_and_versioned(family, tmp_path):
    from PySide6.QtGui import QImage, QColor
    from tutor_ai.documents import import_file

    app, parent, child, _ = family
    child_login(app, child)
    image = QImage(40, 40, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    path = tmp_path / "solution.png"
    assert image.save(str(path))
    imported = import_file(app, path)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_original", work=work, homework=imported["id"], expected_revision=0)
    preview = command(app, "preview", work=work, original=imported["id"])
    assert preview["image"].startswith("data:image/png;base64,")
    assert app.store.db.execute("SELECT count(*) FROM learning_originals").fetchone()[0] == 1
    assert not app.store.db.execute("PRAGMA foreign_key_check").fetchall()
    with pytest.raises(AppError):
        command(app, "preview", work=work, original="foreign-original")


def test_exclusion_expiry_revision_and_parent_date(family):
    from tests.test_learning_050 import publish_program
    from datetime import datetime, timedelta, timezone

    app, parent, child, _ = family
    state = publish_program(app, child)
    topic = app.learning_engine.topics(state["curriculum"])[0]["id"]
    end = datetime.now(timezone.utc) + timedelta(days=2)
    request = command(
        app,
        "exclude",
        student=child["id"],
        subject="algebra",
        topic=topic,
        until=end.isoformat(),
        zone="UTC",
        reason="Временно повторяем другую тему",
    )
    assert not app.learning_engine.excluded(child["id"])
    command(
        app,
        "decide",
        student=child["id"],
        request=request["id"],
        expected_revision=0,
        accept=True,
        reason="Согласовано",
        until=(end + timedelta(days=1)).isoformat(),
    )
    assert topic in app.learning_engine.excluded(child["id"])
    with pytest.raises(AppError):
        command(
            app,
            "decide",
            student=child["id"],
            request=request["id"],
            expected_revision=0,
            accept=False,
            reason="Устаревшее решение",
        )
    command(app, "revoke_exclusion", student=child["id"], request=request["id"], expected_revision=1)
    assert not app.learning_engine.excluded(child["id"])


def test_checkpoint_failure_rolls_back_new_answer(family, monkeypatch):
    app, parent, child, _ = family
    state, col = approved_bank(app, child)
    child_login(app, child)
    aid = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )["id"]
    before = app.store.path.read_bytes()
    view = command(app, "attempt", attempt=aid)
    original = app.store.save

    def fail():
        raise OSError("synthetic disk full")

    monkeypatch.setattr(app.store, "save", fail)
    with pytest.raises(OSError):
        command(
            app, "submit", attempt=aid, slot=view["slots"][0]["id"], answer="Сохранить", expected_revision=0
        )
    monkeypatch.setattr(app.store, "save", original)
    assert app.store.path.read_bytes() == before
    assert command(app, "attempt", attempt=aid)["result"]["S"] == 8
