"""Opt-in content diagnostics, encrypted independently of performance logs."""

import hashlib
import json
import re
import secrets
import threading
import time
import queue
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .crypto import atomic_write, encode, seal, open_seal


def sanitize(value, known=()):
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if re.search(r"password|secret|recovery|authorization|api.?key|credential|access_token|refresh_token", str(k), re.I)
                else sanitize(v, known) for k, v in value.items() if str(k).lower() not in ("headers", "bytes", "image", "images")}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, known) for v in value]
    if isinstance(value, str):
        for secret in known:
            if isinstance(secret, str) and len(secret) >= 3:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_.=:-]+", "[REDACTED]", value)
        def clean(match):
            p = urlsplit(match[0])
            return urlunsplit((p.scheme, p.hostname or "", p.path, "", ""))
        return re.sub(r"https?://[^\s\"<>]+", clean, value)
    return value if isinstance(value, (int, float, bool)) or value is None else "[unsupported]"


class ContentTrace:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.unlocked = False
        self.enabled = False
        self.incomplete = False
        self.session = secrets.token_hex(12)
        self.size = 0
        self.pending_bytes = 0
        self.events = queue.Queue(maxsize=256)
        self.writer = None

    def close(self):
        with self.lock:
            self.enabled = self.unlocked = False
            self.session = secrets.token_hex(12)
            self.size = 0

    def _write(self):
        while True:
            try:
                path, raw = self.events.get(timeout=.5)
            except queue.Empty:
                with self.lock:
                    if not self.enabled and self.events.empty():
                        self.writer = None
                        return
                continue
            try:
                atomic_write(path, raw)
            except Exception:
                with self.lock:
                    self.incomplete, self.enabled = True, False
            finally:
                with self.lock:
                    self.pending_bytes -= len(raw)
                self.events.task_done()

    def flush(self):
        deadline = time.monotonic()+5
        while self.events.unfinished_tasks and time.monotonic() < deadline:
            threading.Event().wait(.01)
        if self.events.unfinished_tasks:
            self.incomplete = True
        return not self.events.unfinished_tasks

    def directory(self):
        vault = self.store.envelope["vault"]
        directory = self.store.root / "logs" / "learning-trace" / hashlib.sha256(vault.encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.resolve().is_relative_to(self.store.root.resolve()) or directory.is_symlink():
            raise OSError("trace_directory")
        # Diagnostic segments add two path components to a Portable installation.
        # Use Windows' supported long-path spelling without weakening containment.
        if os.name == "nt":
            absolute = str(directory.resolve())
            if not absolute.startswith("\\\\?\\"):
                directory = Path("\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute)
        return directory

    def key(self):
        return hashlib.sha256(b"tutor-ai-content-trace-v1\0" + self.store.key).digest()

    def record(self, student, stage, body, known=(), guard=None):
        with self.lock:
            if not self.enabled or not self.store.key or (guard is not None and not guard()):
                return
            try:
                event = {"student": student, "stage": stage, "at": time.time(), "body": sanitize(body, known)}
                raw = encode(event)
                if len(raw) > 4*1024*1024 or self.size + len(raw) > 20*1024*1024:
                    self.incomplete, self.enabled = True, False
                    return
                folder = self.directory()
                files = list(folder.glob("*.trace"))
                for path in files:
                    if not path.is_symlink() and time.time()-path.stat().st_mtime > 7*86400:
                        path.unlink()
                files = [p for p in folder.glob("*.trace") if not p.is_symlink()]
                identity = self.session + "-" + secrets.token_hex(12)
                aad = (self.store.envelope["vault"] + ":" + identity + ":1").encode()
                encrypted = encode(seal(self.key(), raw, aad))
                if len(encrypted) > 4*1024*1024 or self.size+len(encrypted) > 20*1024*1024 or sum(p.stat().st_size for p in files)+self.pending_bytes+len(encrypted) > 100*1024*1024:
                    self.incomplete, self.enabled = True, False
                    return
                self.events.put_nowait((folder / (identity+".trace"), encrypted))
                self.pending_bytes += len(encrypted)
                self.size += len(encrypted)
                if not self.writer:
                    self.writer = threading.Thread(target=self._write, name="encrypted-trace", daemon=True)
                    self.writer.start()
            except Exception:
                self.incomplete, self.enabled = True, False

    def read(self, allowed, student_role=False, since=0, job=None, stage=None):
        result = []
        self.flush()
        with self.lock:
            if not self.store.key:
                return result
            for path in sorted(self.directory().glob("*.trace"), key=lambda p: p.stat().st_mtime):
                if path.is_symlink():
                    continue
                try:
                    aad = (self.store.envelope["vault"] + ":" + path.stem + ":1").encode()
                    item = json.loads(open_seal(self.key(), json.loads(path.read_bytes()), aad))
                    if item["student"] not in allowed or item["at"] < since or (stage and item["stage"] != stage):
                        continue
                    if job and item["body"].get("job") != job:
                        continue
                    if student_role and item["body"].get("purpose") not in ("work_check", "recognize", "study_topic", "ui_operation"):
                        continue
                    result.append(item)
                except Exception:
                    self.incomplete = True
            return result

    def clear(self, allowed):
        self.enabled = False
        self.flush()
        with self.lock:
            self.incomplete = False
            for path in self.directory().glob("*.trace"):
                if not path.is_symlink() and path.resolve().parent == self.directory().resolve():
                    try:
                        aad = (self.store.envelope["vault"] + ":" + path.stem + ":1").encode()
                        event = json.loads(open_seal(self.key(), json.loads(path.read_bytes()), aad))
                        if event["student"] in allowed:
                            path.unlink()
                    except Exception:
                        self.incomplete = True
            self.size = 0
