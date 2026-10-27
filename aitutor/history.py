"""Non-destructive historical classification and evidence-based archive presence."""
from .education import SUBJECTS

UNCLASSIFIED = "unclassified"


def text(value):
    return isinstance(value, str) and bool(value.strip())


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def meaningful_result(value):
    return text(value) or (isinstance(value, dict) and (
        value.get("status") in ("verified", "incorrect") or type(value.get("correct")) is bool
        or text(value.get("text")) or text(value.get("answer"))))


def meaningful_session(item):
    messages = item.get("messages") if isinstance(item.get("messages"), list) else []
    return (text(item.get("task")) or text(item.get("answer"))
            or any(isinstance(m, dict) and (text(m.get("text")) or text(m.get("content")))
                   for m in messages)
            or any(positive(item.get(k)) for k in ("total", "attempts", "attempts_count"))
            or meaningful_result(item.get("result")) or meaningful_result(item.get("check")))


def subject_metadata(item, topics, evidence=()):
    """Explicit facts win; only unified legacy math has a documented mapping."""
    known = topics.get(item.get("topic"), {}).get("subject")
    source = item.get("subject")
    source = source.strip() if text(source) else None
    conflict = False
    if source:
        resolved = (known if known in ("algebra", "geometry") else "math_archive") if source == "math" else source
        conflict = bool(known and source != known and not (source == "math" and known in ("algebra", "geometry")))
        basis = "explicit" if source != "math" else "legacy_math"
    else:
        candidates = {s for s in evidence if text(s) and s != UNCLASSIFIED}
        candidates = {(known or "math_archive") if s == "math" else s for s in candidates}
        if known:
            candidates.add(known)
        conflict = len(candidates) > 1
        resolved = next(iter(candidates)) if len(candidates) == 1 else UNCLASSIFIED
        basis = "catalog" if known and not conflict else "linked_evidence" if len(candidates) == 1 else "unknown"
    label = SUBJECTS.get(resolved) or {"math_archive": "Математика — архив",
                                      UNCLASSIFIED: "Предмет не определён"}.get(resolved)
    if not label:
        label = item.get("subject_label") if text(item.get("subject_label")) else f"Предмет «{resolved}» — архив"
    title = topics.get(item.get("topic"), {}).get("title")
    title = title or item.get("topic_title") or ("Историческая тема · " + str(item.get("topic") or "без ID"))
    return {"source_subject": source, "catalog_subject": resolved, "subject_label": label,
            "classification_basis": basis, "classification_conflict": conflict, "topic_title": title}
