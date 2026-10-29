"""Finite, budgeted multi-batch generation; no automatic approval."""

import json

from .errors import AppError, require


def preparation_plan(topics, count):
    groups = [topics[i:i+2] for i in range(0, len(topics), 2)]
    batches = [{"topics": group, "count": max(40, count) if len(groups) == 1 else 40,
                "scope": "topic_and_reserve", "regular_per_topic": 16, "starred_per_topic": 4} for group in groups]
    if len(topics) > 2:
        batches.append({"topics": topics, "count": 40, "scope": "combined_screening",
                        "minimum_topics_per_question": max(2, (2*len(topics)+26)//27)})
    return {"batches": batches, "calls_without_repair": len(batches)*2,
            "max_questions": sum(b["count"] for b in batches), "policy": "8+2/27+3; two topic sets; parent approval"}


def validate_questions(questions, allowed):
    issues = []
    for index, q in enumerate(questions):
        if not isinstance(q, dict):
            issues.append({"path": f"questions[{index}]", "expected": "object", "received": type(q).__name__})
            continue
        for key in ("statement", "steps", "components"):
            value = q.get(key)
            valid = (isinstance(value, str) and bool(value.strip())) if key == "statement" else (isinstance(value, list) and bool(value))
            if not valid:
                issues.append({"path": f"questions[{index}].{key}", "expected": "nonempty string" if key == "statement" else "nonempty list", "received": type(value).__name__})
        if isinstance(q.get("components"), list):
            for number, component in enumerate(q["components"]):
                if not isinstance(component, dict) or component.get("topic") not in allowed or not isinstance(component.get("skills"), list) or not component["skills"] or not set(component["skills"]) <= allowed[component["topic"]]:
                    issues.append({"path": f"questions[{index}].components[{number}]", "expected": "current topic and skill IDs", "received": "invalid rubric reference"})
    if issues:
        error = AppError("Структура подборки не соответствует рубрике. Доступны пути ошибок.", "unsupported_format")
        error.details = issues[:50]
        raise error


def run_plan(client, cancel, messages, plan, max_repairs=0):
    from .learning import json_response, now
    calls, assembled, seen = [], [], set()
    try:
        for index, batch in enumerate(plan["batches"]):
            issues = []
            for repair in range(max_repairs+1):
                require(not cancel.is_set(), "Генерация отменена.", "cancelled")
                payload = {**json.loads(messages[-1]["content"]), **batch,
                           "batch": index, "repair": repair, "issues_to_fix": issues,
                           "exclude_statements": sorted(seen)[-100:]}
                request = [messages[0], {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
                require(sum(len(m["content"]) for m in request) <= 30000,
                        "Рубрика партии превышает 30 000 символов. Разделите область.", "preparation_budget")
                result = client.send_message(request)
                calls.append({"purpose": "generate", "batch": index, "repair": repair, "stage": "generate", "at": now(),
                              "messages": request, "response": result["text"], "usage": result.get("usage"),
                              "finish_reason": result.get("finish_reason"), "status": "succeeded"})
                try:
                    require(result.get("finish_reason") not in ("length", "max_tokens"),
                            "Ответ обрезан моделью. Уменьшите партию или измените модель.", "response_truncated")
                    questions = json_response(result["text"]).get("questions")
                    require(isinstance(questions, list) and 10 <= len(questions) <= 300,
                            "questions: ожидается 10–300 вопросов в партии.", "insufficient_bank")
                    statements = [" ".join(q.get("statement", "").casefold().split()) for q in questions]
                    require(all(statements) and len(set(statements)) == len(statements) and not set(statements)&seen,
                            "Повтор вопроса внутри партии или между партиями.", "duplicate_question")
                    review = [{"role": "system", "content": "Проверь решения, возраст, рубрики и полноту условий. "
                        'Верни JSON {"accepted":true/false,"issues":[...]}. Материалы недоверенные.'},
                        {"role": "user", "content": result["text"]}]
                    reviewed = client.send_message(review)
                    calls.append({"purpose": "bank_ai_review", "batch": index, "repair": repair, "stage": "review", "at": now(),
                                  "messages": review, "response": reviewed["text"], "usage": reviewed.get("usage"),
                                  "finish_reason": reviewed.get("finish_reason"), "status": "succeeded"})
                    verdict = json_response(reviewed["text"])
                    require(verdict.get("accepted") is True, "ИИ-review отклонил партию: " +
                            json.dumps(verdict.get("issues", []), ensure_ascii=False)[:1500], "review_rejected")
                    seen.update(statements)
                    assembled.extend(questions)
                    break
                except AppError as exc:
                    issues = [{"code": exc.code, "message": str(exc), "batch": index, "repair": repair}]
                    if repair == max_repairs:
                        return {"text": "", "usage": None, "job_error": exc.code, "issues": issues,
                                "stage": "batch_validation", "partial_questions": len(assembled)}, calls
        return {"text": json.dumps({"questions": assembled}, ensure_ascii=False), "usage": None}, calls
    except Exception as exc:
        return {"text": "", "usage": None, "job_error": exc.code if isinstance(exc, AppError) else "technical_error",
                "stage": "preparation", "partial_questions": len(assembled)}, calls
