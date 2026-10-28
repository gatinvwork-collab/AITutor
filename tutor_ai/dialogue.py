"""Nonrecursive reconstruction of work turns, including pre-0.5.0a2 journals."""

import json

from .errors import require


INTENTS = {"check": "Проверь решение.", "hint": "Дай подсказку.", "follow_up": "Продолжи разбор решения."}


def work_messages(system, subject, solution, revision, intent, follow_up, calls):
    require(intent in INTENTS, "Выберите действие.")
    # The native-selected mode is trusted control; learner text is only data.
    # Historical turns must not override the current request's mode.
    control = (
        f"\nТекущее действие (intent): {intent}. {INTENTS[intent]} "
        "Этот режим относится к последнему вопросу и имеет приоритет над режимами истории. "
        "Уточнение ученика дополняет действие, но не меняет выбранный режим."
    )
    messages = [
        {"role": "system", "content": system + control},
        {
            "role": "user",
            "content": json.dumps(
                {"subject": subject, "solution": solution, "work_revision": revision}, ensure_ascii=False
            ),
        },
    ]
    sources, unresolved, historical = [], [], set()
    for call in calls:
        if call.get("purpose") != "work_check":
            continue  # OCR is data extraction, not a tutoring turn.
        saved = call.get("messages", [])
        base = {}
        if len(saved) > 1 and saved[1].get("role") == "user":
            try:
                base = json.loads(saved[1]["content"])
                if not isinstance(base, dict):
                    base = {}
            except (ValueError, TypeError):
                pass
        turn = call.get("dialogue_user")
        if turn is None:
            # Old logs contain only one new question, at the end; their earlier
            # messages are snapshots and must not be concatenated recursively.
            turn = saved[-1]["content"] if len(saved) > 2 and saved[-1].get("role") == "user" else None
            if turn is None and base.get("intent") in INTENTS:
                turn = "Режим сохранённого запроса: " + base["intent"]
        if not isinstance(turn, str) or not turn:
            continue  # Unknown text cannot be invented.
        if call.get("intent") in INTENTS:
            # This is provenance, not a claim that a legacy model received it.
            turn = f"[Режим по метаданным прошлого вызова: {call['intent']}]\n" + turn
        old_revision = call.get("work_revision", "legacy_unspecified")
        old_solution = call.get("solution_snapshot", base.get("solution"))
        if old_revision != revision:
            key = (old_revision, old_solution)
            label = f"[Историческая версия решения: {old_revision}]\n"
            if key not in historical and isinstance(old_solution, str) and old_solution != solution:
                label += "Сохранённое решение той версии:\n" + old_solution + "\n"
                historical.add(key)
            turn = label + turn
        status = call.get("status", "unknown")
        if status != "succeeded" or not call.get("response"):
            messages.append(
                {"role": "user", "content": f"[Запрос со статусом {status}; учебного ответа нет]\n" + turn}
            )
            unresolved.append(call.get("source_call"))
        else:
            messages.extend(
                [{"role": "user", "content": turn}, {"role": "assistant", "content": call["response"]}]
            )
        sources.append(call.get("source_call"))
    current = follow_up.strip() or INTENTS[intent]
    messages.append({"role": "user", "content": current})
    require(
        sum(len(m["content"]) for m in messages) <= 30000,
        "Контекст превышает 30 000 символов. Разбейте решение или создайте отдельную работу. "
        "Черновик и история сохранены; запрос не отправлен.",
        "text_limit",
    )
    return messages, {
        "dialogue_user": current,
        "intent": intent,
        "work_revision": revision,
        "solution_snapshot": solution,
        "context_sources": sources,
        "unresolved_calls": unresolved,
        "context_policy": "ordered-work-turns-v2-explicit-intent",
    }
