"""Opt-in synthetic encrypted-snapshot capacity probe; build/ only."""

import ctypes
import hashlib
import json
import time
import uuid
from pathlib import Path

from tutor_ai.errors import AppError
from tutor_ai.service import Service


def main():
    root = Path(__file__).resolve().parent.parent / "build" / ("capacity050-" + uuid.uuid4().hex[:8])

    class Memory(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("load", ctypes.c_ulong),
            ("total", ctypes.c_ulonglong),
            ("available", ctypes.c_ulonglong),
            ("page_total", ctypes.c_ulonglong),
            ("page_available", ctypes.c_ulonglong),
            ("virtual_total", ctypes.c_ulonglong),
            ("virtual_available", ctypes.c_ulonglong),
            ("extended", ctypes.c_ulonglong),
        ]

    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
    root.mkdir()
    result = {
        "available_before_bytes": memory.available,
        "kind": "synthetic snapshot; not realistic model/photo corpus",
    }
    if memory.available < 4 * 1024**3:
        result.update(status="skipped_insufficient_free_ram")
    else:
        app = Service(root / "app-data")
        app.register("Synthetic capacity", "synthetic-capacity-password", "PARENT")
        start = time.perf_counter()
        with app.store.transaction():
            app.store.put("capacity_probe", "large", {"payload": "x" * (185 * 1024 * 1024)}, app.actor)
        result["checkpoint_seconds"] = time.perf_counter() - start
        result["vault_bytes"] = app.store.path.stat().st_size
        before = hashlib.sha256(app.store.path.read_bytes()).hexdigest()
        start = time.perf_counter()
        try:
            with app.store.transaction():
                app.store.put(
                    "capacity_probe", "additional", {"payload": "y" * (20 * 1024 * 1024)}, app.actor
                )
            raise AssertionError("capacity limit not enforced")
        except AppError as exc:
            assert exc.code == "capacity"
        result["refusal_seconds"] = time.perf_counter() - start
        result["file_unchanged"] = before == hashlib.sha256(app.store.path.read_bytes()).hexdigest()
        result["ram_rolled_back"] = app.store.get("capacity_probe", "additional") is None
        app.store.close()
        app.network_jobs.shutdown()
        result["status"] = "passed" if result["file_unchanged"] and result["ram_rolled_back"] else "failed"
    (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(root), **result}))
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
