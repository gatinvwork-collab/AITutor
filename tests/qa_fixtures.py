"""Synthetic foreign-vault fixture with deliberate identity collisions."""
import json
import shutil
import uuid

from tutor_ai.service import Service


def foreign_backup(source, root, passwords, archive_password):
    foreign = Service(root)
    foreign.store.create()
    with foreign.store.transaction():
        for row in source.store.db.execute("SELECT * FROM users").fetchall():
            user = dict(row)
            user["name"] = "Foreign " + user["name"][:52]
            if user["role"] == "STUDENT":
                profile = json.loads(user["profile"])
                profile["school"] = "Foreign school"
                user["profile"] = json.dumps(profile)
            foreign.store.db.execute("INSERT INTO users(id,role,name,profile,theme,design,profile_revision) "
                "VALUES(?,?,?,?,?,?,?)", tuple(user[k] for k in (
                    "id", "role", "name", "profile", "theme", "design", "profile_revision")))
            foreign.store.credentials(user["id"], passwords[user["id"]], user["role"] == "PARENT")
        for link in source.store.db.execute("SELECT * FROM links"):
            foreign.store.db.execute("INSERT INTO links VALUES(?,?)", tuple(link))
    foreign.actor = source.actor
    name = foreign.backup(archive_password)["file"]
    target = "foreign-" + uuid.uuid4().hex + ".aitbackup"
    shutil.copy2(foreign.store.root / "backups" / name, source.store.root / "backups" / target)
    vault = foreign.store.envelope["vault"]
    foreign.logout()
    return target, vault


def seed_import_032(service, student):
    from tutor_ai.crypto import seal
    from tests.test_import_032 import pdf_bytes
    with service.store.transaction():
        for hid, filename, raw, extracted in (
            ("legacy-long032", "old-long.txt", b"x" * 30000 + b"\nFINAL QUESTION", "x" * 30000),
            ("legacy-short032", "old-short.pdf", pdf_bytes(6000), "x" * 5000),
        ):
            service.store.put("homework", hid, {"id": hid, "student": student, "created": "2026-10-25",
                "subject": "algebra", "topic": None, "filename": filename, "text": extracted,
                "confirmed": True, "warning": "", "result": "Старый результат",
                "original": seal(service.store.attachment_key(), raw, hid.encode())}, student)
