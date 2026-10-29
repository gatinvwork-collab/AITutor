"""Read-only probe of the supplied PDFs through the bounded product worker."""

import hashlib
import json
from pathlib import Path
import time

from tutor_ai.pdf_worker import inspect


def main():
    folder = Path(__file__).resolve().parent.parent / "build/uf29-pdf-probe"
    folder.mkdir(exist_ok=True)
    source = Path("C:/Users/591053/Downloads/Учебники")
    result = []
    for name in ("Algebra_7_klass.pdf", "N_G_Mindyuk_I_S_Shlykova_Metodicheskie_rekomendatsii_Algebra_7_klass.pdf"):
        raw = (source / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        started = time.monotonic()
        data = inspect(raw)
        observation = {"name": name, "sha256": digest, "bytes": len(raw), "pages": data["pages"],
                       "selected_pages": [p["pdf_page"] for p in data["selected"]],
                       "nonempty_selected": sum(bool(p["text"].strip()) for p in data["selected"]),
                       "duration": time.monotonic()-started}
        if name == "Algebra_7_klass.pdf":
            assert {255, 256, 257} <= set(observation["selected_pages"])
            pages = inspect(raw, pages=[254, 255, 256], render=True)
            for page in pages["selected"]:
                (folder / f"book-page-{page['pdf_page']}.png").write_bytes(page["image"])
            observation["rendered"] = [p["pdf_page"] for p in pages["selected"]]
        else:
            observation["toc_discovered"] = 175 in observation["selected_pages"]
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest
        observation["source_unchanged"] = True
        result.append(observation)
    (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
