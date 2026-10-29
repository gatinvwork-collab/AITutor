"""Actual input bytes and worker, deterministic recognition fixture. Not live OCR QA."""

import hashlib
import json
from pathlib import Path
import time
import uuid

from tutor_ai.service import Service
from tests.test_learning_050 import command
from tests.upgrade_051 import PASSWORD

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = json.loads((ROOT / "docs/evidence/textbook-analysis-2026-10-29/toc-reference.json").read_text(encoding="utf-8"))


def leaves():
    sections = {s["n"]: s for s in REFERENCE["sections"]}
    chapters = {c["n"]: c["title"] for c in REFERENCE["chapters"]}
    result = []
    for item in REFERENCE["items"]:
        section = sections.get(item.get("section"))
        result.append({"number": str(item["n"]), "title": item["title"],
            "chapter": chapters[item.get("chapter") or section["chapter"]],
            "paragraph": section["title"] if section else None,
            "optional": item["supplementary"], "grade": 7,
            "pdf_page": 255 if item["n"] < 17 else 256 if item["n"] < 33 else 257,
            "printed_label": "254–256", "skills": []})
    return result


class RecognitionFixture:
    def __init__(self, config):
        pass

    def send_multimodal(self, messages, images):
        assert len(images) <= 4
        pages = json.loads(messages[-1]["content"])
        relevant = any(p["pdf_page"] in (255, 256, 257) for p in pages)
        return {"text": json.dumps({"metadata": {k: REFERENCE[k] for k in ("title", "authors", "publisher", "year", "edition", "isbn")},
                                    "topics": leaves() if relevant else [], "warnings": []}), "usage": None}

    def send_message(self, messages):
        data = json.loads(messages[-1]["content"])
        return {"text": json.dumps({"skills": [["Применить метод: " + t["title"], "Обосновать преобразования и проверить результат"] for t in data["topics"]]}), "usage": None}

    def close(self):
        pass


def main():
    folder = ROOT / "build" / ("uf29-source-pipeline-" + uuid.uuid4().hex[:8])
    assert not (folder / "app-data/data/vault.aead").exists(), "Use a new isolated directory"
    app = Service(folder / "app-data", provider_factory=RecognitionFixture)
    app.register("Source fixture parent", PASSWORD, "PARENT")
    child = app.register("Source fixture child", "fixture-child-password", "STUDENT", {"region": "R", "city": "C", "school": "S", "grade": 7})
    app.save_provider({"kind": "ollama", "model": "deterministic-recognition-fixture", "revision": 0})
    path = Path("C:/Users/591053/Downloads/Учебники/Algebra_7_klass.pdf")
    raw = path.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    # Identical opaque handle contract to the native file picker. No HTML path.
    app.source_handles["fixture-handle"] = {"bytes": raw, "student": child["id"], "context": app.context, "created": time.monotonic()}
    started = time.monotonic()
    result = command(app, "import_source", student=child["id"], subject="algebra", kind="book", handle="fixture-handle")
    while time.monotonic()-started < 120:
        job = command(app, "job", job=result["job"])
        if job["status"] not in ("pending", "running"):
            break
        time.sleep(.05)
    assert job["status"] == "succeeded", job
    candidate = job["body"]["result"]["candidate"]
    request = command(app, "curriculum", student=child["id"], subject="algebra", expected_revision=0,
                      title=candidate["title"], source="Fixture recognition over supplied PDF", topics=candidate["topics"])
    command(app, "decide", student=child["id"], request=request["id"], expected_revision=0, accept=True, reason="Synthetic structural acceptance")
    ctx = app.learning_engine.subject_context(child["id"], "algebra")
    counts = {kind: sum(n["kind"] == kind for n in ctx["nodes"]) for kind in ("chapter", "paragraph", "topic")}
    assert counts == {"chapter": 6, "paragraph": 15, "topic": 46}
    assert sum(t["optional"] is True for t in ctx["topics"]) == 6
    assert all(r[0] == "ai_proposed" for r in app.store.db.execute("SELECT origin FROM learning_skill_provenance"))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert app.store.path.stat().st_size < len(raw)//2  # No whole book in vault.
    result = {"passed": True, "source_sha256": before, "bytes": len(raw), "counts": counts, "optional": 6,
              "directory": str(folder),
              "vault_bytes": app.store.path.stat().st_size, "duration": time.monotonic()-started,
              "source_unchanged": True, "recognition": "deterministic fixture, not live AI OCR", "schema": 5}
    app.logout()
    app.network_jobs.shutdown()
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
