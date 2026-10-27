"""Versioned portable AEAD envelopes. No plaintext database is written to disk."""

import base64
import json
import os
import secrets
from pathlib import Path

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import AppError, require


def b64(value):
    return base64.b64encode(value).decode("ascii")


def unb64(value):
    return base64.b64decode(value, validate=True)


def derive(password, salt):
    return hash_secret_raw(password.encode("utf-8"), salt, 3, 65536, 1, 32, Type.ID)


def seal(key, data, aad):
    nonce = secrets.token_bytes(12)
    return {"nonce": b64(nonce), "data": b64(AESGCM(key).encrypt(nonce, data, aad))}


def open_seal(key, record, aad):
    return AESGCM(key).decrypt(unb64(record["nonce"]), unb64(record["data"]), aad)


def wrap(key, secret, aad):
    salt = secrets.token_bytes(16)
    return {"salt": b64(salt), **seal(derive(secret, salt), key, aad)}


def unwrap(record, secret, aad):
    return open_seal(derive(secret, unb64(record["salt"])), record, aad)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def atomic_write(path, data):
    """Same-directory replace: an interrupted write never truncates the last vault."""
    path = Path(path)
    temp = path.with_name(path.name + ".pending")
    try:
        with open(temp, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_envelope(path):
    require(Path(path).stat().st_size <= 256 * 1024 * 1024, "Хранилище слишком велико.")
    try:
        value = json.loads(Path(path).read_bytes())
        require(value["format"] == 1, "Версия хранилища не поддерживается.")
        require(isinstance(value["wraps"], dict), "Повреждён заголовок хранилища.")
        return value
    except (KeyError, ValueError, TypeError) as exc:
        raise AppError("Формат хранилища повреждён.", "integrity") from exc
