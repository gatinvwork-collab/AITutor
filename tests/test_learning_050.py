"""Schema 4 workflows on synthetic encrypted families; no network credentials."""

import json
import threading
import time
import uuid

import pytest

from tutor_ai.assessment import metrics, plan
from tutor_ai.errors import AppError
from tests.test_application import PASSWORD, CHILD_PASSWORD, PROFILE, family as family_fixture, child_login

family = family_fixture


def command(app, action, **args):
    if action not in ("overview", "attempt", "job"):
        args.setdefault("operation_id", str(uuid.uuid4()))
    return app.dispatch("learning", {"action": action, **args})


def publish_program(app, child, count=1):
    student = child["id"]
    request = command(
        app,
        "curriculum",
        student=student,
        subject="algebra",
        title="Тестовая программа",
        source="Тестовый ручной источник",
        topics=[{"title": f"Тема {i}", "skills": ["Метод", "Проверка"]} for i in range(count)],
        expected_revision=0,
    )
    command(
        app,
        "decide",
        student=student,
        request=request["id"],
        expected_revision=0,
        accept=True,
        reason="Проверен состав",
    )
    return app.learning_engine.state(student, "algebra")


class BankProvider:
    def __init__(self, config):
        self.config = config

    def send_message(self, messages):
        if messages[0]["content"].startswith("Проверь решения"):
            return {"text": '{"accepted":true,"issues":[]}', "usage": {"total_tokens": 1}}
        data = json.loads(messages[-1]["content"])
        topics = data["topics"]
        questions = []
        for i in range(40):
            topic = topics[i % len(topics)]
            questions.append(
                {
                    "statement": f"Задание {i}: объясни способ решения и проверку.",
                    "starred": i >= 32,
                    "steps": ["Применить метод", "Проверить результат"],
                    "source": "synthetic-test",
                    "components": [
                        {
                            "topic": topic["id"],
                            "skills": [s["id"] for s in topic["skills"]],
                            "criterion": "Обоснование и проверка",
                            "expected": "Оба шага",
                            "checker": "number",
                        }
                    ],
                }
            )
        return {"text": json.dumps({"questions": questions}), "usage": {"total_tokens": 2}}

    def close(self):
        pass


def wait_job(app, result):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = command(app, "job", job=result["job"])
        if job["status"] not in ("pending", "running"):
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def approved_bank(app, child, topics=1):
    state = publish_program(app, child, topics)
    app.provider_factory = BankProvider
    job = wait_job(app, command(app, "generate", student=child["id"], subject="algebra", count=40))
    assert job["status"] == "succeeded", job
    request = job["body"]["result"]
    command(
        app,
        "decide",
        student=child["id"],
        request=request["id"],
        expected_revision=0,
        accept=True,
        reason="Проверены задания",
    )
    collection = app.learning_engine.body(app.learning_engine.row("requests", request["id"]))["collection"]
    return state, collection


@pytest.mark.parametrize(
    "c,w,u,s,eligible",
    [
        (4, 1, 0, 0, True),
        (1999, 501, 0, 0, False),
        (2, 0, 1, 0, False),
        (0, 0, 0, 0, False),
        (8, 0, 0, 1, False),
        (0, 1, 0, 0, False),
    ],
)
def test_exact_metrics(c, w, u, s, eligible):
    items = [
        {"code": code, "skills": ["skill"], "independent": True}
        for code, n in [("C", c), ("W", w), ("U", u), ("S", s)]
        for _ in range(n)
    ]
    result = metrics(items, ["skill"])
    assert result["eligible"] is eligible
    assert result["N"] == c + w + u + s
    if c == 2:
        assert result["P"] == 100 and result["K"] == pytest.approx(200 / 3)


def test_skill_coverage_not_component_percentage():
    result = metrics([{"code": "C", "skills": ["one"], "independent": True}] * 8, ["one", "two"])
    assert result["K"] == 100 and not result["eligible"]


@pytest.mark.parametrize("topic_count", [0, 1, 2, 3, 13, 14, 15, 16])
def test_planning_mandatory_topics(topic_count):
    topic_skills = {str(i): [f"s{i}"] for i in range(topic_count)}
    questions = [
        {
            "id": str(i),
            "topics": [str(i % max(1, topic_count))],
            "skills": [f"s{i % max(1, topic_count)}"],
            "starred": i >= 40,
        }
        for i in range(43)
    ]
    if topic_count > 13:
        with pytest.raises(AppError, match="помещаются"):
            plan(questions, "subject_screening", topic_skills, topic_skills)
    else:
        selected = plan(questions, "subject_screening", topic_skills, topic_skills)
        assert len(selected) == 30 and sum(q["starred"] for q in selected) == 3


def test_assignment_roles_revision_idempotence(family):
    app, parent, child, _ = family
    args = dict(
        student=child["id"],
        subject="algebra",
        fields={"title": "Книга"},
        expected_revision=0,
        operation_id="save-1",
    )
    assert command(app, "assignment", **args) == {"revision": 1}
    assert command(app, "assignment", **args) == {"revision": 1}
    with pytest.raises(AppError) as error:
        command(app, "assignment", **{**args, "fields": {"title": "Другое"}})
    assert error.value.code == "conflict"
    child_login(app, child)
    args.update(expected_revision=1, operation_id="child-proposal")
    result = command(app, "assignment", **args)
    assert result["status"] == "pending"
    assert app.learning_engine.state(child["id"], "algebra")["revision"] == 1
    app.logout()
    app.login(parent["id"], PASSWORD)
    assert app.notifications()[0]["recipient"] == parent["id"]


def test_current_and_studied_are_not_confirmation(family):
    app, parent, child, _ = family
    state = publish_program(app, child)
    topic = app.learning_engine.topics(state["curriculum"])[0]["id"]
    command(app, "current", student=child["id"], subject="algebra", topic=topic, expected_revision=1)
    request = command(
        app, "studied", student=child["id"], subject="algebra", topics=[topic], expected_revision=2
    )
    command(
        app,
        "decide",
        student=child["id"],
        request=request["id"],
        expected_revision=0,
        accept=True,
        reason="Материал пройден",
    )
    knowledge = command(app, "overview", student=child["id"])["map"][0]
    assert knowledge["studied"] and knowledge["current"] and not knowledge["confirmed"]
    assert not app.store.all("knowledge", child["id"])


def test_generated_bank_approval_no_reference_leak(family):
    app, parent, child, _ = family
    state, col = approved_bank(app, child)
    child_login(app, child)
    overview = command(app, "overview", student=child["id"])
    assert all("questions" not in c for c in overview["collections"])
    assert overview["calls"] == []
    attempt = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )
    view = command(app, "attempt", attempt=attempt["id"])
    assert len(view["slots"]) == 10 and sum(s["starred"] for s in view["slots"]) == 2
    assert all(s["reference"] is None for s in view["slots"])
    assert view["result"]["S"] == 8 and view["result"]["P"] is None


def finish_answers(app, child, col, state, purpose="topic_confirmation"):
    attempt = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose=purpose,
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )["id"]
    for _ in range(35):
        view = command(app, "attempt", attempt=attempt)
        todo = next((s for s in view["slots"] if not s["answers"] and not s["skipped"]), None)
        if not todo:
            break
        if todo["starred"]:
            command(app, "skip", attempt=attempt, slot=todo["id"], expected_revision=view["revision"])
        else:
            args = dict(
                attempt=attempt,
                slot=todo["id"],
                answer="Мой исходный ответ по шагам",
                expected_revision=view["revision"],
                operation_id=uid(),
            )
            first = command(app, "submit", **args)
            assert command(app, "submit", **args) == first
    view = command(app, "attempt", attempt=attempt)
    command(app, "finish", attempt=attempt, expected_revision=view["revision"])
    return attempt


def uid():
    return str(uuid.uuid4())


def review_all(app, attempt):
    for component in app.learning_engine.components(attempt):
        if not component["answer"]:
            continue
        command(
            app,
            "review",
            attempt=attempt,
            answer=component["answer"],
            criterion=component["criterion"],
            code="C",
            reason="Проверены все необходимые шаги",
            scope="Полный обязательный компонент",
            expected_revision=component["observation"]["revision"],
        )


@pytest.mark.parametrize("purpose", ["topic_confirmation", "subject_screening"])
def test_unknown_manual_review_and_purpose(family, purpose):
    app, parent, child, _ = family
    state, col = approved_bank(app, child)
    child_login(app, child)
    attempt = finish_answers(app, child, col, state, purpose)
    value = app.learning_engine.result(attempt)
    assert value["U"] > 0 and not value["confirmed"]
    app.logout()
    app.login(parent["id"], PASSWORD)
    review_all(app, attempt)
    value = app.learning_engine.result(attempt)
    assert value["K"] == 100 and value["P"] == 100 and value["U"] == 0
    assert value["confirmed"] is (purpose == "topic_confirmation")
    # The immutable original answer was not rewritten by the parent's decision.
    assert all(
        app.learning_engine.body(r)["text"] == "Мой исходный ответ по шагам"
        for r in app.store.db.execute("SELECT * FROM learning_answers")
    )


def test_rotation_three_distinct_attempts_and_revision(family):
    app, parent, child, _ = family
    state, col = approved_bank(app, child)
    ids = []
    for i in range(3):
        child_login(app, child)
        attempt = finish_answers(app, child, col, state)
        ids.append(attempt)
        app.logout()
        app.login(parent["id"], PASSWORD)
        review_all(app, attempt)
    assert (
        app.store.db.execute(
            "SELECT max(n) FROM (SELECT count(*) n FROM learning_success GROUP BY student,question)"
        ).fetchone()[0]
        == 3
    )
    first_question = app.learning_engine.row(
        "slots", command(app, "attempt", attempt=ids[0])["slots"][0]["id"]
    )["question"]
    child_login(app, child)
    other = command(
        app,
        "start",
        student=child["id"],
        collection=col,
        purpose="topic_confirmation",
        topic=app.learning_engine.topics(state["curriculum"])[0]["id"],
    )
    assert first_question not in [
        s["question"] for s in command(app, "attempt", attempt=other["id"])["slots"]
    ]


def test_cascade_delete_new_personal_entities(family):
    app, parent, child, _ = family
    approved_bank(app, child)
    command(app, "work", student=child["id"], subject="algebra") if app.user()["role"] == "STUDENT" else None
    app.delete_student(child["id"], child["id"])
    assert not app.store.db.execute("PRAGMA foreign_key_check").fetchall()
    assert not app.store.db.execute("SELECT * FROM learning_collections").fetchall()
    assert not app.store.db.execute("SELECT * FROM learning_jobs").fetchall()


def test_jobs_do_not_hold_service_lock_and_logout_discards_result(family):
    app, parent, child, _ = family
    command(
        app,
        "assignment",
        student=child["id"],
        subject="algebra",
        fields={"title": "Книга"},
        expected_revision=0,
    )
    entered, release = threading.Event(), threading.Event()

    class Blocking:
        def __init__(self, config):
            pass

        def send_message(self, messages):
            entered.set()
            release.wait(5)
            return {"text": "Не публиковать", "usage": None}

        def close(self):
            pass

    app.provider_factory = Blocking
    job = command(app, "normalize", student=child["id"], subject="algebra", expected_revision=1)
    assert entered.wait(3)
    start = time.monotonic()
    command(
        app,
        "assignment",
        student=child["id"],
        subject="algebra",
        fields={"title": "Новее"},
        expected_revision=1,
    )
    assert time.monotonic() - start < 1
    app.logout()
    release.set()
    app.login(parent["id"], PASSWORD)
    assert app.learning_engine.state(child["id"], "algebra")["assignment"]["title"] == "Новее"
    assert command(app, "job", job=job["job"])["status"] == "cancelled"


def test_work_revisions_first_text_and_ai_journal(family):
    app, parent, child, _ = family
    child_login(app, child)
    work = command(app, "work", student=child["id"], subject="algebra")["id"]
    command(app, "work_revision", work=work, value="Исходное решение", expected_revision=0, confirm=True)
    job = wait_job(app, command(app, "work_check", work=work, expected_revision=1, intent="check"))
    assert job["status"] == "succeeded", job
    command(app, "work_revision", work=work, value="Исправленное решение", expected_revision=1, confirm=True)
    versions = app.store.db.execute(
        "SELECT body FROM learning_work_revisions WHERE work=? ORDER BY revision", (work,)
    ).fetchall()
    assert json.loads(versions[1][0])["text"] == "Исходное решение"
    calls = command(app, "overview", student=child["id"])["calls"]
    assert len(calls) == 1 and "Исходное решение" in json.dumps(calls, ensure_ascii=False)
    assert "Authorization" not in json.dumps(calls)


def test_cross_child_acl_and_empty_family(family):
    app, parent, child, _ = family
    other = app.register("Другой", CHILD_PASSWORD, "STUDENT", PROFILE)
    state, col = approved_bank(app, child)
    child_login(app, other)
    for action, args in [
        ("overview", {"student": child["id"]}),
        ("generate", {"student": child["id"], "subject": "algebra"}),
        ("start", {"student": other["id"], "collection": col, "purpose": "topic_confirmation"}),
    ]:
        with pytest.raises(AppError):
            command(app, action, **args)
