"""Compare identical click->RAF definitions; do not label them display latency."""
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    output = Path(sys.argv[1]).resolve()
    assert output.is_relative_to(ROOT / "build")
    baseline = ROOT / "docs/evidence/user-feedback-2026-10-27"
    comparison = []
    for label in ("small", "history1500"):
        for version, directory in (("0.4.0", baseline), ("0.4.1", output)):
            data = json.loads((directory / (label + "-navigation.json")).read_text(encoding="utf-8"))
            for design in ("strict", "modern"):
                for route in ("notifications", "home", "students"):
                    items = [row for row in data["clicks"] if "iteration" in row and row["design"] == design
                             and row.get("requested", row.get("route")) == route]
                    values = sorted(row["elapsed_ms"] for row in items)
                    assert len(values) == 100
                    comparison.append({"fixture": label, "version": version, "design": design, "route": route,
                                       "n": len(values), "median_ms": statistics.median(values),
                                       "p95_ms": values[math.ceil(.95 * len(values)) - 1], "max_ms": max(values)})
    result = {"metric": "JS click handler to second requestAnimationFrame; excludes physical screen latency",
              "candidate_diagnostics_enabled": True, "baseline_diagnostics_enabled": False, "comparison": comparison}
    (output / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(comparison), "candidate_max_ms": max(r["max_ms"] for r in comparison if r["version"] == "0.4.1")}))


if __name__ == "__main__":
    main()
