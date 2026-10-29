import json
import threading

import pytest

from tutor_ai.content_trace import sanitize
from tutor_ai.errors import AppError
from tutor_ai.jobs import NetworkJobs
from tutor_ai.preparation import preparation_plan, validate_questions
from tutor_ai.source_import import compatibility
from tests.test_application import family as family_fixture, child_login, PASSWORD
from tests.test_learning_050 import command, wait_job, approved_bank

family = family_fixture


def test_future_topics_and_optional_do_not_grant_mastery(family):
    app, parent, child, _ = family
    request = command(app, "curriculum", student=child["id"], subject="algebra", title="Tree", source="manual",
                      expected_revision=0, topics=[{"title": title, "skills": ["Обосновать результат"], "chapter": "I",
                      "optional": optional} for title, optional in [("A", False), ("B", True), ("C", False)]])
    command(app, "decide", student=child["id"], request=request["id"], expected_revision=0, accept=True, reason="Проверено")
    ctx = command(app, "subject_context", student=child["id"], subject="algebra")
    a, b, c = ctx["topics"]
    assert a["opened"] and not b["opened"] and not c["opened"]
    assert all(t["allowed_actions"]["study"] and t["allowed_actions"]["homework"] for t in ctx["topics"])
    child_login(app, child)
    request = command(app, "studied", student=child["id"], subject="algebra", topics=[c["id"]], expected_revision=1)
    ctx = command(app, "subject_context", student=child["id"], subject="algebra")
    assert ctx["topics"][-1]["studied_requested"] and not ctx["topics"][-1]["allowed_actions"]["topic_confirmation"]
    app.logout()
    app.login(parent["id"], PASSWORD)
    command(app, "decide", student=child["id"], request=request["id"], expected_revision=0, accept=True, reason="Пройдено вне очереди")
    ctx = command(app, "subject_context", student=child["id"], subject="algebra")
    assert ctx["topics"][-1]["allowed_actions"]["topic_confirmation"]
    assert not any(t["knowledge_confirmation"] for t in ctx["topics"])
    assert ctx["next_main"] == c["id"]  # Optional B is not a barrier.


def test_rubric_validation_reports_path_without_question_text():
    secret = "PRIVATE ANSWER"
    with pytest.raises(AppError) as error:
        validate_questions([{"statement": secret, "steps": [], "components": [{"topic": "wrong", "skills": []}]}], {"right": {"s"}})
    assert error.value.details[0]["path"] == "questions[0].steps"
    assert secret not in str(error.value.details)


def test_plan_spans_more_than_300_and_has_combined_scope():
    topics = [{"id": str(i), "skills": [{"id": f"s{i}"}], "title": f"T{i}"} for i in range(46)]
    result = preparation_plan(topics, 40)
    assert result["max_questions"] > 300
    assert all(b["count"] <= 300 for b in result["batches"])
    assert result["batches"][-1]["scope"] == "combined_screening"
    assert result["calls_without_repair"] == 48


def test_method_compatibility_is_not_a_year_guess():
    book = {"year": 2023, "grade": 7, "subject": "algebra", "isbn": "book", "topics": [{"number": "8", "title": "Линейное уравнение"}]}
    method = {"year": 2017, "grade": 7, "subject": "algebra", "topics": [{"number": "8", "title": "Статистические характеристики"}]}
    result = compatibility(book, method)
    assert result["status"] == "incompatible" and result["reasons"]
    assert compatibility(book, {"year": 2017})["status"] == "unknown"
    assert compatibility(book, {**book, "year": 2022, "target_isbn": "book"})["status"] == "compatible"


def test_finisher_called_once_when_publication_throws():
    jobs, done, calls = NetworkJobs(), threading.Event(), []
    def publish(*args):
        calls.append(args)
        done.set()
        raise OSError("synthetic checkpoint")
    jobs.submit("j", lambda _: "answer", publish)
    assert done.wait(5)
    jobs.pool.shutdown(wait=True)
    assert len(calls) == 1 and "j" in jobs.publication_errors


def test_trace_encrypted_opt_in_and_student_cannot_read_references(family):
    app, _, child, _ = family
    state, collection = approved_bank(app, child)
    with pytest.raises(AppError):
        app.developer("enable", enabled=True)
    with pytest.raises(AppError):
        app.developer("unlock", password="God")
    assert not app.developer("unlock", password="god")["enabled"]
    app.developer("enable", enabled=True)
    token = "CANARY-API-SECRET"
    app.content_trace.record(child["id"], "send", {"purpose": "work_check", "job": "j", "message": token,
                              "authorization": "Bearer abcdef", "url": "https://example.org/a?token=private"}, [token])
    app.content_trace.record(child["id"], "send", {"purpose": "generate", "job": "bank", "reference": "FUTURE REFERENCE"})
    app.content_trace.flush()
    files = list(app.content_trace.directory().glob("*.trace"))
    assert len(files) == 2 and all(token.encode() not in p.read_bytes() for p in files)
    own = app.developer("view", student=child["id"])
    assert token not in json.dumps(own) and "?token=" not in json.dumps(own)
    app.logout()
    assert not app.developer()["unlocked"]
    child_login(app, child)
    app.developer("unlock", password="god")
    viewed = app.developer("view", student=child["id"])
    assert len(viewed["events"]) == 1 and "FUTURE REFERENCE" not in json.dumps(viewed)
    with pytest.raises(AppError):
        app.developer("clear")


def test_sanitizer_nested_credentials_and_signed_links():
    result = sanitize({"a": ["Bearer abcdef", "secretcanary"], "api_key": "x", "url": "https://user:pwd@example.org/a?auth=123"}, ["secretcanary"])
    text = json.dumps(result)
    assert all(value not in text for value in ("abcdef", "secretcanary", "pwd", "auth=123"))


def test_generation_validation_failure_is_failed_not_stale(family):
    app, _, child, _ = family
    state, _ = approved_bank(app, child)
    class Bad:
        def __init__(self, config):
            pass
        def send_message(self, messages):
            return {"text": '{"questions":[]}', "usage": None}
        def close(self):
            pass
    app.provider_factory = Bad
    result = wait_job(app, command(app, "generate", student=child["id"], subject="algebra"))
    assert result["status"] == "failed" and result["body"]["code"] == "insufficient_bank"
    assert result["body"]["stage"] == "batch_validation"
    assert app.store.db.execute("SELECT count(*) FROM learning_preparations WHERE status='failed'").fetchone()[0] == 1


def test_source_resume_reuses_only_completed_pages(monkeypatch):
    from tutor_ai.source_import import process
    monkeypatch.setattr("tutor_ai.source_import.inspect", lambda *a, **k: {"pages": 100,
        "selected": [{"pdf_page": 7, "text": "Оглавление T"}], "warnings": []})
    class Fixture:
        def send_message(self, messages):
            return {"text": json.dumps({"metadata": {"grade": 7}, "topics": [{"title": "T", "number": "1", "grade": 7,
                "optional": False, "pdf_page": 7, "skills": ["Обосновать результат"]}]}), "usage": None}
    first, calls = process(b"fixture", "methodical", "algebra", Fixture(), {"kind": "ollama"}, threading.Event())
    calls[0]["source_call"] = "earlier-call"
    class NoNetwork:
        def send_message(self, messages):
            raise AssertionError("Resume must not send the completed page again")
    second, reused = process(b"fixture", "methodical", "algebra", NoNetwork(), {"kind": "ollama"}, threading.Event(), previous=calls)
    assert second["text"] == first["text"] and reused[0]["sent_this_job"] is False
    assert reused[0]["source_call"] == "earlier-call"


def test_trace_resource_failure_does_not_touch_history(family):
    app, _, child, _ = family
    app.developer("unlock", password="god")
    app.developer("enable", enabled=True)
    before = app.store.path.read_bytes()
    app.content_trace.record(child["id"], "send", {"purpose": "work_check", "message": "x"*(4*1024*1024+1)})
    assert app.content_trace.incomplete and not app.content_trace.enabled
    assert app.store.path.read_bytes() == before


def test_confirm_current_opens_next_main_without_confirming_optional(family):
    from tests.test_learning_050 import finish_answers, review_all
    app, parent, child, _ = family
    state, col = approved_bank(app, child, topics=2)
    first, second = app.learning_engine.topics(state["curriculum"])
    # Add an ungraded optional leaf between the two existing ordered leaves.
    with app.store.transaction():
        app.store.db.execute("UPDATE learning_topics SET position=2 WHERE id=?", (second["id"],))
        app.store.db.execute("UPDATE learning_outline_nodes SET position=2 WHERE id=?", (second["id"],))
        app.store.db.execute("INSERT INTO learning_topics VALUES('optional-fixture',?,1,'Дополнительный пункт')", (state["curriculum"],))
        app.store.db.execute("INSERT INTO learning_outline_nodes VALUES('optional-fixture',?,NULL,'optional-fixture',1,'topic',1,NULL,'{}')", (state["curriculum"],))
    child_login(app, child)
    attempt = finish_answers(app, child, col, state)
    app.logout()
    app.login(parent["id"], PASSWORD)
    review_all(app, attempt)
    ctx = app.learning_engine.subject_context(child["id"], "algebra")
    assert ctx["next_main"] == second["id"]
    assert ctx["topics"][2]["opened"] and ctx["topics"][0]["knowledge_confirmation"]
    assert not ctx["topics"][1]["opened"] and not ctx["topics"][1]["knowledge_confirmation"]
    assert not ctx["topics"][1]["studied_approved"]


def test_cancel_request_is_not_a_terminal_success(family):
    app, _, child, _ = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, expected_revision=0, value="x=1", confirm=True)
    gate = threading.Event()
    class Waiting:
        def __init__(self, config):
            pass
        def send_message(self, messages):
            gate.wait(5)
            return {"text": "Fixture response", "usage": None}
        def close(self):
            pass
    app.provider_factory = Waiting
    job = command(app, "work_check", work=work, expected_revision=1)
    result = command(app, "cancel_job", job=job["job"])
    assert result["cancel_requested"] and result["status"] == "running"
    gate.set()
    assert wait_job(app, job)["status"] == "cancelled"
