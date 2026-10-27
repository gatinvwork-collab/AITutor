"""Portable installation transfer. Never edit the source or merge a destination.

Only the desktop's native directory chooser supplies paths. A journal gates all
ordinary writes until publication/rollback finishes, including after a crash.
"""

import hashlib
import json
import os
import shutil
import stat
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .crypto import atomic_write, encode, open_seal, read_envelope
from .errors import require
from .storage import Store

JOURNAL = "transfer-state.json"
STAGE = ".transfer-stage"
FOLDERS = {"config", "data", "secure", "attachments", "cache", "logs", "backups"}


def safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink() and not part.is_junction(),
                "Ссылки и junction в пути переноса не поддерживаются.", "transfer_path")
    return path.resolve()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return {"size": Path(path).stat().st_size, "sha256": value.hexdigest()}


def publish_file(source, destination):
    # Windows rename refuses an existing destination (also on FAT/exFAT).
    # POSIX rename would overwrite, so use its exclusive hardlink operation.
    if os.name == "nt":
        os.rename(source, destination)
    else:
        os.link(source, destination)


def inventory(root, internal=False):
    """Unknown regular files are preserved; only declared runtime state is omitted."""
    root = safe_path(root)
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            require(not path.is_symlink() and not path.is_junction(),
                    "В данных обнаружена ссылка. Перенос остановлен.", "transfer_path")
        relative = Path(folder).relative_to(root)
        if relative == Path("."):
            dirs[:] = [d for d in dirs if d != "cache"]
        for name in files:
            path = Path(folder) / name
            rel = path.relative_to(root).as_posix()
            if rel == ".transfer-owner":
                require(internal, "В источнике найден служебный маркер переноса.", "transfer_pending")
                continue
            if rel == "instance.lock" or name.endswith(".pending"):
                continue
            require(rel != JOURNAL and STAGE not in path.relative_to(root).parts,
                    "В источнике есть незавершённый перенос. Завершите его в исходной установке.", "transfer_pending")
            require(stat.S_ISREG(path.stat().st_mode), "Неподдерживаемый тип файла.", "transfer_path")
            result[rel] = digest(path)
    return result


@contextmanager
def installation_lock(data):
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(Path(data) / "instance.lock"))
    require(lock.tryLock(0), "Закройте приложение, использующее выбранную папку данных.", "transfer_locked")
    try:
        yield
    finally:
        lock.unlock()


def check_empty(data):
    """Permit only the host's empty scaffold, runtime cache and instance lock."""
    safe_path(data)
    if not data.exists():
        return
    for path in data.iterdir():
        safe_path(path)
        if path.name in ("cache", "instance.lock"):
            continue
        require(path.name in FOLDERS and path.is_dir() and not any(path.iterdir()),
                "В назначении уже есть данные. Выберите отдельную пустую папку; объединение не выполняется.",
                "transfer_conflict")


def validate_store(store):
    db = store.db
    require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            and not db.execute("PRAGMA foreign_key_check").fetchall(), "Нарушена целостность данных.", "integrity")
    users = {row[0] for row in db.execute("SELECT id FROM users")}
    for row in db.execute("SELECT kind,id,owner,body FROM records"):
        item = json.loads(row["body"])
        if row["kind"] in ("session", "homework", "knowledge"):
            require(row["owner"] in users, "В истории отсутствует владелец записи.", "integrity")
        if row["kind"] == "homework":
            require(not item.get("filename") or item.get("original"),
                    "В исходной истории отсутствует оригинал вложения. Полный перенос невозможен.", "attachment_missing")
            if item.get("original"):
                open_seal(store.attachment_key(), item["original"], row["id"].encode())


class Transfer:
    def __init__(self, root, frozen_executable=None):
        self.root = safe_path(root)
        self.executable = Path(frozen_executable) if frozen_executable else None
        self.plan = None
        self.cancelled = threading.Event()

    def prepare(self, source, destination=None):
        source = safe_path(source)
        destination = safe_path(destination or self.root)
        require(source != destination and not source.is_relative_to(destination)
                and not destination.is_relative_to(source),
                "Источник и назначение не должны совпадать или находиться друг внутри друга.", "transfer_path")
        data = source / "app-data"
        require(data.is_dir() and (data / "data" / "vault.aead").is_file(),
                "Выберите корень прежней установки с папкой app-data и хранилищем.", "transfer_source")
        safe_path(data)
        if destination != self.root:
            require(self.executable and self.executable.is_file(),
                    "Отдельную установку можно создать из Portable exe. Для исходников выберите текущую папку.")
            require(not destination.exists() or not any(destination.iterdir()),
                    "Выберите пустую папку для отдельной Portable-установки.", "transfer_conflict")
        check_empty(destination / "app-data")
        with installation_lock(data):
            files = inventory(data)
            envelope = read_envelope(data / "data" / "vault.aead")
            labels = {p["id"]: p for p in envelope.get("directory", {}).get("profiles", [])}
            accounts = [{"id": uid, "name": labels.get(uid, {}).get("name"),
                         "role": labels.get(uid, {}).get("role")} for uid in envelope["wraps"]]
        self.plan = {"id": uuid.uuid4().hex, "source": source, "destination": destination, "files": files}
        return {"id": self.plan["id"], "source": str(data), "destination": str(destination / "app-data"),
                "accounts": accounts, "files": len(files), "bytes": sum(f["size"] for f in files.values())}

    def cancel(self):
        self.cancelled.set()
        return {"ok": True}

    def checkpoint(self):
        require(not self.cancelled.is_set(), "Перенос отменён. Источник сохранён.", "cancelled")

    def execute(self, operation, account, password):
        require(self.plan and self.plan["id"] == operation, "Сначала выберите папки переноса.")
        self.cancelled.clear()
        plan = self.plan
        data = plan["destination"] / "app-data"
        data.mkdir(parents=True, exist_ok=True)
        if plan["destination"] == self.root:
            return self._execute_locked(data, plan, account, password)
        with installation_lock(data):
            return self._execute_locked(data, plan, account, password)

    def _execute_locked(self, data, plan, account, password):
        check_empty(data)
        stage = data / STAGE
        require(not stage.exists(), "Обнаружена незавершённая копия. Сначала отмените прежний перенос.", "transfer_pending")
        journal = {"format": 1, "operation": plan["id"], "phase": "copy", "files": {}}
        journal_path = data / JOURNAL
        # Create journal exclusively: never overwrite another transfer.
        with journal_path.open("xb") as stream:
            stream.write(encode(journal))
            stream.flush()
            os.fsync(stream.fileno())
        store = None
        try:
            with installation_lock(plan["source"] / "app-data"):
                source = plan["source"] / "app-data"
                require(inventory(source) == plan["files"], "Источник изменился. Выберите установку заново.", "transfer_changed")
                space = shutil.disk_usage(data).free
                size = sum(f["size"] for f in plan["files"].values())
                executable_size = self.executable.stat().st_size if self.executable else 0
                require(space >= size * 3 + executable_size + 16 * 1024 * 1024,
                        "Недостаточно места для копии, снимка и публикации.", "capacity")
                stage.mkdir()
                (stage / ".transfer-owner").write_text(plan["id"], encoding="ascii")
                for name, expected in plan["files"].items():
                    self.checkpoint()
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / name, target)
                    require(digest(target) == expected, "Копия не прошла проверку SHA256.", "integrity")
                require(inventory(source) == plan["files"], "Источник изменился во время копирования.", "transfer_changed")
                store = Store(stage)
                store.unlock(account, password)
                validate_store(store)
                # No Service.login: no auto-backup, billing or login audit in the copy.
                sessions = store.all("session")
                if any(s.get("status") == "active" for s in sessions):
                    with store.transaction():
                        for session in sessions:
                            if session.get("status") == "active":
                                session["status"] = "paused"
                                store.put("session", session["id"], session, session["student"])
                store.close()
                store = None
                self.checkpoint()
                if plan["destination"] != self.root:
                    executable = plan["destination"] / self.executable.name
                    require(not executable.exists(), "Конфликт исполняемого файла назначения.", "transfer_conflict")
                    # New executable only; old exe/resources are not copied from source.
                    bundled = stage / "cache" / "new-executable"
                    bundled.parent.mkdir(parents=True, exist_ok=True)
                    with self.executable.open("rb") as inp, bundled.open("xb") as out:
                        shutil.copyfileobj(inp, out)
                        out.flush()
                        os.fsync(out.fileno())
                    require(digest(bundled) == digest(self.executable), "Не удалось проверить новый exe.", "integrity")
                    journal["executable"] = {"name": executable.name, **digest(bundled)}
                journal.update(phase="publish", files=inventory(stage, internal=True))
                atomic_write(journal_path, encode(journal))
                if journal.get("executable"):
                    publish_file(stage / "cache" / "new-executable", data.parent / journal["executable"]["name"])
                names = sorted(journal["files"], key=lambda n: n == "data/vault.aead")
                for name in names:
                    self.checkpoint()
                    target = data / name
                    safe_path(target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    publish_file(stage / name, target)
                journal["phase"] = "published"
                atomic_write(journal_path, encode(journal))
                self.finish(data, journal)
        except Exception:
            if store:
                store.close()
            # A durable journal lets the UI safely retry cleanup after I/O failure/crash.
            raise
        self.plan = None
        return {"ok": True, "destination": str(plan["destination"]),
                "current": plan["destination"] == self.root, "files": len(journal["files"])}

    @staticmethod
    def read_journal(data):
        data = safe_path(data)
        path = data / JOURNAL
        safe_path(path)
        require(path.stat().st_size <= 16 * 1024 * 1024, "Журнал переноса повреждён.")
        journal = json.loads(path.read_bytes())
        require(journal.get("format") == 1 and len(journal.get("operation", "")) == 32
                and all(c in "0123456789abcdef" for c in journal["operation"])
                and journal.get("phase") in ("copy", "publish", "published")
                and isinstance(journal.get("files"), dict), "Журнал переноса повреждён.")
        for name, info in journal["files"].items():
            require(isinstance(name, str) and not Path(name).is_absolute() and ".." not in Path(name).parts
                    and ":" not in name and "\\" not in name and name not in (JOURNAL, "instance.lock")
                    and name.split("/")[0] not in (STAGE, "cache")
                    and isinstance(info.get("sha256"), str) and len(info["sha256"]) == 64,
                    "Небезопасный журнал переноса.")
            safe_path(data / name)
        executable = journal.get("executable")
        if executable:
            require(Path(executable["name"]).name == executable["name"]
                    and executable["name"].startswith("Tutor-AI-") and executable["name"].endswith(".exe")
                    and ":" not in executable["name"] and "\\" not in executable["name"], "Небезопасный путь exe.")
            safe_path(data.parent / executable["name"])
        return journal

    @staticmethod
    def remove_stage(data, journal):
        stage = safe_path(data / STAGE)
        require(stage.parent == data and stage.name == STAGE, "Небезопасный путь временной копии.")
        if not stage.exists():
            return
        owner = stage / ".transfer-owner"
        require((owner.is_file() and owner.read_text(encoding="ascii") == journal["operation"])
                or not any(stage.iterdir()), "Временная копия принадлежит другой операции.")
        files, dirs = [], []
        for folder, children, names in os.walk(stage, followlinks=False):
            for name in children + names:
                path = Path(folder) / name
                require(safe_path(path).is_relative_to(stage), "Небезопасный временный путь.")
                (dirs if path.is_dir() else files).append(path)
        # Retain ownership marker until all content has gone, also across a crash.
        for path in files:
            if path != owner:
                path.unlink()
        for path in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
            path.rmdir()
        owner.unlink(missing_ok=True)
        stage.rmdir()

    @staticmethod
    def finish(data, journal):
        require(all((data / name).is_file() and digest(data / name) == expected
                    for name, expected in journal["files"].items()), "Опубликованная копия повреждена.", "integrity")
        if journal.get("executable"):
            executable = journal["executable"]
            require(digest(data.parent / executable["name"]) == {k: executable[k] for k in ("size", "sha256")},
                    "Новый исполняемый файл повреждён.", "integrity")
        Transfer.remove_stage(data, journal)
        (data / JOURNAL).unlink()

    @staticmethod
    def recover(data):
        """Finalize a fully published copy, or remove only our unchanged hardlinks."""
        data = safe_path(data)
        journal = Transfer.read_journal(data)
        if journal["phase"] == "published":
            Transfer.finish(data, journal)
            return {"ok": True, "published": True}
        stage = safe_path(data / STAGE)
        if stage.exists() and any(stage.iterdir()):
            require((stage / ".transfer-owner").is_file()
                    and (stage / ".transfer-owner").read_text(encoding="ascii") == journal["operation"],
                    "Временная копия принадлежит другой операции.")
        staged = inventory(stage, internal=True) if stage.exists() else {}
        for name, expected in journal["files"].items():
            target = data / name
            if target.exists():
                require(digest(target) == expected and (name not in staged or
                        (staged[name] == expected and os.path.samefile(stage / name, target))),
                        "Целевой файл изменён. Автоматическая очистка остановлена; сохраните папку для проверки.", "transfer_conflict")
        executable = journal.get("executable")
        if executable and (data.parent / executable["name"]).exists():
            target = data.parent / executable["name"]
            bundled = stage / "cache" / "new-executable"
            require((not bundled.exists() or os.path.samefile(bundled, target))
                    and digest(target) == {k: executable[k] for k in ("size", "sha256")},
                    "Исполняемый файл назначения изменён. Очистка остановлена.", "transfer_conflict")
            target.unlink()
        for name in journal["files"]:
            (data / name).unlink(missing_ok=True)
        Transfer.remove_stage(data, journal)
        (data / JOURNAL).unlink()
        return {"ok": True, "published": False}
