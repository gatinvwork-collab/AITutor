"""Q10/Q11: access is derived, never evidence of learning."""

import json


def context(engine, student, subject):
    state = engine.state(student, subject)
    cid = state.get("curriculum")
    topics = engine.topics(cid)
    nodes = [dict(r) for r in engine.db.execute(
        "SELECT * FROM learning_outline_nodes WHERE curriculum=? ORDER BY position", (cid,))]
    by_topic = {n["topic"]: n for n in nodes if n["topic"]}
    main = [t["id"] for t in topics if by_topic.get(t["id"], {}).get("optional") != 1]
    current = state.get("current")
    selected = current or next(iter(main), None)
    position = next((t["position"] for t in topics if t["id"] == selected), -1)
    opened = {t["id"] for t in topics if t["position"] <= position and t["id"] in main}
    if current:
        opened.add(current)
    confirmed = {r[0] for r in engine.db.execute(
        "SELECT DISTINCT topic FROM learning_confirmations c JOIN learning_attempts a ON a.id=c.attempt "
        "WHERE a.student=? AND c.active=1", (student,))}
    successor = next((t["id"] for t in topics if t["position"] > position and t["id"] in main), None)
    if selected in confirmed and successor:
        opened.add(successor)
    pending = {tid for r in engine.db.execute(
        "SELECT body FROM learning_requests WHERE student=? AND kind='studied' AND status='pending'", (student,))
        for tid in json.loads(r[0]).get("topics", [])}
    studied = set(state.get("studied", []))
    excluded = engine.excluded(student)
    leaves = []
    for topic in topics:
        tid = topic["id"]
        allowed = tid in opened or tid in studied
        optional = by_topic.get(tid, {}).get("optional")
        leaves.append({**topic, "outline": json.loads(by_topic[tid]["body"]) if tid in by_topic else {}, "optional": bool(optional) if optional is not None else None,
                       "current": tid == current, "opened": tid in opened,
                       "studied_requested": tid in pending, "studied_approved": tid in studied,
                       "knowledge_confirmation": tid in confirmed, "control_exclusion": tid in excluded,
                       "allowed_actions": {"study": True, "homework": True, "request_studied": True,
                                           "topic_confirmation": allowed},
                       "reasons": {"topic_confirmation": "" if allowed else
                                   "Тема ещё не открыта. Можно изучать и проверять ДЗ либо заявить прохождение родителю."}})
    return {"student": student, "subject": subject, "revision": state["revision"], "curriculum": cid,
            "assignment": state.get("assignment"), "nodes": [{**n, "body": json.loads(n["body"])} for n in nodes],
            "topics": leaves, "current": current, "next_main": successor,
            "main_complete": bool(selected in confirmed and not successor), "policy": "q10a-q11a-v1"}
