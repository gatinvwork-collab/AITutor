"""Strict diagnostic policy. No model's assertion is itself a verified observation."""

import hashlib
import json
import re
from collections import Counter

from .errors import require

POLICY = "cwus-independent-v1"
REASONS = {"technical_error", "unsupported_format", "awaiting_manual_review", "ambiguous_result"}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def equivalent(statement):
    # Changing numbers/names alone is not accepted as a new structural variant.
    return re.sub(r"\s+", " ", re.sub(r"\d+(?:[.,]\d+)?", "#", statement.casefold())).strip()


def metrics(components, required_skills):
    counts = Counter(c["code"] for c in components)
    n = len(components)
    checked = counts["C"] + counts["W"]
    proven = {
        s for c in components if c["code"] in ("C", "W") and c.get("independent") for s in c.get("skills", [])
    }
    return {
        "N": n,
        **{k: counts[k] for k in "CWUS"},
        "P": 100 * counts["C"] / checked if checked else None,
        "K": 100 * checked / n if n else None,
        "covered_skills": sorted(proven),
        "required_skills": sorted(required_skills),
        "eligible": bool(
            n
            and checked == n
            and 5 * counts["C"] >= 4 * checked
            and set(required_skills) <= proven
            and all(c.get("independent") for c in components)
        ),
    }


def plan(questions, purpose, topic_skills, mandatory_topics=(), priorities=()):
    """Exact, bounded coverage search. Never silently drop a mandatory topic."""
    require(purpose in ("topic_confirmation", "subject_screening"), "Выберите цель диагностики.")
    quota, stars = (8, 2) if purpose == "topic_confirmation" else (27, 3)
    required_topics = set(topic_skills) if purpose == "topic_confirmation" else set(mandatory_topics)
    require(
        required_topics <= set(topic_skills),
        "Обязательная тема отсутствует в программе.",
        "mandatory_topics_overflow",
    )
    required = (
        {s for skills in topic_skills.values() for s in skills} if purpose == "topic_confirmation" else set()
    )
    priority = {t: i for i, t in enumerate(priorities)}
    ordered = sorted(
        questions, key=lambda q: min((priority.get(t, 10000) for t in q["topics"]), default=10000)
    )
    regular = [q for q in ordered if not q["starred"]]
    optional = [q for q in ordered if q["starred"]]
    require(
        len(regular) >= quota and len(optional) >= stars,
        "Недостаточно допущенных разных заданий. Подготовьте и утвердите подборку/резерв.",
        "insufficient_bank",
    )
    if purpose == "subject_screening" and required_topics:
        max_topics = max((len(set(q["topics"]) & required_topics) for q in regular), default=0)
        require(
            max_topics and 2 * len(required_topics) <= quota * max_topics,
            "Все обязательные темы не помещаются в план.",
            "mandatory_topics_overflow",
        )
    # Bitmask set-cover: two distinct physical questions per mandatory screening topic.
    needs = {t: 2 for t in required_topics} if purpose == "subject_screening" else {}
    # Common large curricula need no exponential search. First construct a
    # complete greedy cover; use the bounded exact search only if it cannot fit.
    covered, amounts, greedy = set(), {t: 0 for t in needs}, []
    remaining = list(regular)
    while not (required <= covered and all(n >= 2 for n in amounts.values())):

        def gain(q):
            return len((set(q["skills"]) & required) - covered) + sum(
                1 for t in q["topics"] if t in amounts and amounts[t] < 2
            )

        best = max(remaining, key=gain, default=None)
        if best is None or gain(best) == 0:
            break
        greedy.append(best)
        remaining.remove(best)
        covered.update(set(best["skills"]) & required)
        for t in set(best["topics"]) & set(amounts):
            amounts[t] += 1
    if required <= covered and all(n >= 2 for n in amounts.values()) and len(greedy) <= quota:
        chosen_ids = {q["id"] for q in greedy}
        return (
            greedy
            + [q for q in regular if q["id"] not in chosen_ids][: quota - len(greedy)]
            + optional[:stars]
        )
    states = {(frozenset(), tuple(0 for _ in needs)): []}
    need_keys = sorted(needs)
    for q in regular:
        for (covered, amounts), chosen in list(states.items()):
            if len(chosen) >= quota:
                continue
            new = (
                covered | (set(q["skills"]) & required),
                tuple(min(2, amounts[i] + int(t in q["topics"])) for i, t in enumerate(need_keys)),
            )
            candidate = chosen + [q]
            if new not in states or len(candidate) < len(states[new]):
                states[new] = candidate
        require(
            len(states) <= 100000,
            "План слишком сложен. Разделите область проверки.",
            "mandatory_topics_overflow",
        )
    chosen = states.get((frozenset(required), tuple(2 for _ in need_keys)))
    require(
        chosen is not None and len(chosen) <= quota,
        "Все обязательные темы/навыки не помещаются в план. План не создан.",
        "mandatory_topics_overflow",
    )
    chosen_ids = {q["id"] for q in chosen}
    chosen += [q for q in regular if q["id"] not in chosen_ids][: quota - len(chosen)]
    # Among nonmandatory topics only report coverage actually achieved, never confirmation.
    return chosen + optional[:stars]
