"""SQLite in RAM with a completely encrypted, atomic on-disk snapshot.

Bootstrap wrappers and ciphertext share one atomically replaced document. This
avoids the two-file password-reset consistency problem. Intended for the pilot,
not an unlimited-size database. Memory/OS paging is outside at-rest guarantees.
"""

import copy
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

from .crypto import atomic_write, encode, open_seal, read_envelope, seal, unwrap, wrap
from .errors import AppError, require
from .education import catalog_subject

SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA temp_store=MEMORY;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_migrations VALUES(1);
INSERT OR IGNORE INTO schema_migrations VALUES(2);
INSERT OR IGNORE INTO schema_migrations VALUES(3);
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('PARENT','STUDENT')),
 name TEXT NOT NULL, profile TEXT NOT NULL, theme TEXT NOT NULL DEFAULT 'system',
 design TEXT NOT NULL DEFAULT 'strict' CHECK(design IN ('strict','modern')),
 profile_revision INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS links(
 parent_id TEXT REFERENCES users(id), student_id TEXT REFERENCES users(id),
 PRIMARY KEY(parent_id,student_id));
CREATE TABLE IF NOT EXISTS records(
 kind TEXT NOT NULL, id TEXT NOT NULL, owner TEXT, body TEXT NOT NULL,
 PRIMARY KEY(kind,id));
"""


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        for folder in ("config", "data", "secure", "attachments", "cache", "logs", "backups"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.path = self.root / "data" / "vault.aead"
        self.db = None
        self.key = None
        self.envelope = None
        self.directory_warning = False

    @property
    def exists(self):
        return self.path.exists()

    def accounts(self):
        if not self.exists:
            return []
        envelope = read_envelope(self.path)
        directory = envelope.get("directory", {})
        profiles = directory.get("profiles", []) if isinstance(directory, dict) else []
        profiles = profiles if isinstance(profiles, list) else []
        labels = {p.get("id"): p for p in profiles if isinstance(p, dict) and isinstance(p.get("id"), str)}
        result = []
        for uid in envelope["wraps"]:
            record = labels.get(uid, {})
            name = record.get("name")
            role = record.get("role")
            result.append({"id": uid, "name": name[:60] if isinstance(name, str) else None,
                           "role": role if role in ("PARENT", "STUDENT") else None})
        return result

    def create(self):
        require(not self.exists, "Хранилище уже существует.")
        self.key = secrets.token_bytes(32)
        self.envelope = {"format": 1, "vault": str(uuid.uuid4()), "wraps": {}}
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def aad(self, account, purpose):
        return f'{self.envelope["vault"]}:{account}:{purpose}:1'.encode()

    def unlock(self, account, secret, recovery=False):
        self.close()
        self.envelope = read_envelope(self.path)
        try:
            purpose = "recovery" if recovery else "password"
            record = self.envelope["wraps"][account][purpose]
            self.key = unwrap(record, secret, self.aad(account, purpose))
            raw = open_seal(self.key, self.envelope["payload"], self.envelope["vault"].encode())
            self.db = sqlite3.connect(":memory:", check_same_thread=False)
            self.db.deserialize(raw)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA temp_store=MEMORY")
            require(self.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "База повреждена.")
            version = self.db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
            require(version in (1, 2, 3),
                    "Версия базы не поддерживается.")
            require(self.user(account) is not None, "Учётная запись отсутствует.")
            directory = self.envelope.get("directory")
            if directory is not None:
                expected = hmac.new(self.key, b"directory-v1:" + encode(directory), hashlib.sha256).hexdigest()
                self.directory_warning = not hmac.compare_digest(expected.encode(),
                    str(self.envelope.get("directory_mac", "")).encode("utf-8"))
        except Exception as exc:
            self.close()
            raise AppError("Неверные данные входа или повреждённое хранилище.", "authentication") from exc
        if version < 3:
            try:
                self.migrate_v3(version)
            except Exception as exc:
                self.close()
                raise AppError("Не удалось обновить хранилище. Исходные данные сохранены; "
                               "проверьте свободное место и права записи.", "migration") from exc

    def credentials(self, account, password, parent=False, rotate_recovery=False):
        require(len(password) >= 10, "Используйте пароль не короче 10 символов. Короткий PIN пока недоступен.")
        record = self.envelope["wraps"].setdefault(account, {})
        record["password"] = wrap(self.key, password, self.aad(account, "password"))
        recovery = None
        if parent and (rotate_recovery or "recovery" not in record):
            recovery = secrets.token_urlsafe(32)
            record["recovery"] = wrap(self.key, recovery, self.aad(account, "recovery"))
        return recovery

    def save(self):
        require(self.db is not None, "Сначала войдите.", "authentication")
        # Deliberately public metadata, approved by the user. Canonical names and
        # authorization still come from the encrypted DB, never this directory.
        self.envelope["directory"] = {"version": 1, "profiles": [dict(row) for row in self.db.execute(
            "SELECT id,name,role FROM users ORDER BY id")]}
        self.envelope["directory_mac"] = hmac.new(self.key, b"directory-v1:" + encode(self.envelope["directory"]),
                                                  hashlib.sha256).hexdigest()
        self.envelope["payload"] = seal(self.key, self.db.serialize(), self.envelope["vault"].encode())
        encoded = encode(self.envelope)
        require(len(encoded) <= 256 * 1024 * 1024,
                "Хранилище достигло лимита прототипа 256 МБ. Новые данные не сохранены.", "capacity")
        atomic_write(self.path, encoded)

    def migrate_v2(self, persist=True):
        """One encrypted pre-migration snapshot; preserve all historical facts."""
        raw = self.path.read_bytes()
        backup = self.root / "backups" / ("before-migration-v1-" + hashlib.sha256(raw).hexdigest()[:16] + ".aead")
        if not backup.exists():
            atomic_write(backup, raw)
        with self.transaction() if persist else nullcontext():
            for user in self.db.execute("SELECT id,profile FROM users WHERE role='STUDENT'").fetchall():
                profile = json.loads(user["profile"])
                if "address" not in profile:
                    profile["address"] = {"mode": "manual", "verification": "manual_unverified"}
                    self.db.execute("UPDATE users SET profile=? WHERE id=?", (json.dumps(profile), user["id"]))
            for kind in ("session", "homework"):
                for row in self.db.execute("SELECT id,owner,body FROM records WHERE kind=?", (kind,)).fetchall():
                    record = json.loads(row["body"])
                    record["catalog_subject"] = catalog_subject(record)
                    if kind == "homework" and not record.get("subject"):
                        record["needs_subject_confirmation"] = True
                    self.put(kind, row["id"], record, row["owner"])
            for row in self.db.execute("SELECT id,owner,body FROM records WHERE kind='program'").fetchall():
                record = json.loads(row["body"])
                record["needs_subject_confirmation"] = True
                self.put("program", row["id"], record, row["owner"])
            self.db.execute("INSERT INTO schema_migrations(version) VALUES(2)")

    def migrate_v3(self, version):
        raw = self.path.read_bytes()
        backup = self.root / "backups" / (
            f"before-migration-v{version}-" + hashlib.sha256(raw).hexdigest()[:16] + ".aead")
        if not backup.exists():
            atomic_write(backup, raw)
        require(backup.read_bytes() == raw, "Не удалось проверить снимок перед обновлением.", "migration")
        # Both upgrades are published together; a failed v1 -> v3 never replaces v1 with v2.
        with self.transaction():
            if version == 1:
                self.migrate_v2(persist=False)
            self.db.execute("ALTER TABLE users ADD COLUMN design TEXT NOT NULL DEFAULT 'strict' "
                            "CHECK(design IN ('strict','modern'))")
            self.db.execute("ALTER TABLE users ADD COLUMN profile_revision INTEGER NOT NULL DEFAULT 0")
            self.db.execute("UPDATE users SET design='modern' WHERE role='STUDENT'")
            self.db.execute("INSERT INTO schema_migrations(version) VALUES(3)")

    @contextmanager
    def transaction(self):
        previous = copy.deepcopy(self.envelope)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            # Serialize includes the current transaction. Persist before COMMIT;
            # COMMIT on a private in-memory DB has no disk I/O to fail.
            self.save()
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.envelope = previous
            raise

    def user(self, account):
        row = self.db.execute("SELECT * FROM users WHERE id=?", (account,)).fetchone()
        return dict(row) if row else None

    def put(self, kind, identity, body, owner=None):
        self.db.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET "
                        "owner=excluded.owner,body=excluded.body", (kind, identity, owner, json.dumps(body)))

    def get(self, kind, identity):
        row = self.db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, identity)).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, kind, owner=None):
        query = "SELECT body FROM records WHERE kind=?"
        params = [kind]
        if owner is not None:
            query += " AND owner=?"
            params.append(owner)
        return [json.loads(row[0]) for row in self.db.execute(query, params)]

    def attachment_key(self):
        return hashlib.sha256(self.key + b"aitutor-attachments-v1").digest()

    def close(self):
        if self.db is not None:
            self.db.close()
        self.db = None
        self.key = None
        self.envelope = None
        self.directory_warning = False
