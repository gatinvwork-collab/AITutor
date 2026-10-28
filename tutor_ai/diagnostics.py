"""Explicit opt-in timings. No identities, paths, exception text or user content."""
import json
import math
import secrets
import threading
from datetime import datetime, timezone


ROUTES = frozenset({"home", "students", "notifications", "subjects", "lesson", "homework",
                    "knowledge", "history", "controls", "program", "providers", "backup",
                    "security", "settings", "profile"})


class Diagnostics:
    def __init__(self, root, enabled=False, commands=()):
        self.enabled = enabled
        self.commands = frozenset(commands) | {"tick", "pick_file", "choose_transfer", "run_transfer",
                                             "recover_transfer", "launch_transferred"}
        self.lock = threading.Lock()
        self.path = None
        if enabled:
            folder = root / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            self.path = folder / ("performance-" + stamp + "-" + secrets.token_hex(4) + ".jsonl")
            self.write({"event": "session", "version": "0.5.0a4", "timing": "not_physical_display_latency"})

    def write(self, record):
        if not self.enabled:
            return
        # Diagnostics must never prevent an educational operation or fill a disk.
        try:
            with self.lock:
                if self.path.exists() and self.path.stat().st_size >= 2 * 1024 * 1024:
                    return
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    @staticmethod
    def number(value, maximum=3_600_000):
        return round(value, 3) if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum else None

    def command(self, command, wait_ms, duration_ms):
        if command not in self.commands:
            command = "unknown"
        self.write({"event": "command", "command": command,
                    "wait_ms": self.number(wait_ms), "duration_ms": self.number(duration_ms)})

    def navigation(self, payload):
        if not isinstance(payload, dict) or payload.get("route") not in ROUTES:
            return
        self.write({"event": "navigation", "route": payload["route"],
                    **{key: self.number(payload.get(key)) for key in ("render_ms", "raf_ms", "width", "height", "dpr")}})
