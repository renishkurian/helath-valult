"""
Encryption at rest for medical data.

- Text fields (patient IDs, notes, etc.) are encrypted with Fernet before
  being written to the database, and decrypted on the way out.
- Uploaded files are encrypted on disk; nothing is ever stored as plaintext
  bytes in `storage/`.

Fernet = AES-128-CBC + HMAC-SHA256, authenticated encryption. Good enough for
personal-scale medical documents; if you outgrow this, swap for envelope
encryption with per-document data keys wrapped by MASTER_KEY.
"""
from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.MASTER_KEY.encode())


def encrypt_text(plain: str | None) -> str | None:
    if plain is None:
        return None
    return _fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str | None) -> str | None:
    if token is None:
        return None
    return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet.encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet.decrypt(token)


# Password-protected backup envelope: HV1 | 16-byte salt | Fernet(zip bytes)
_BACKUP_MAGIC = b"HV1\0"


def encrypt_backup(zip_bytes: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import os, base64
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return _BACKUP_MAGIC + salt + Fernet(key).encrypt(zip_bytes)


def decrypt_backup(blob: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64
    if not blob.startswith(_BACKUP_MAGIC):
        # Unencrypted zip handed to restore
        return blob
    salt = blob[len(_BACKUP_MAGIC):len(_BACKUP_MAGIC) + 16]
    token = blob[len(_BACKUP_MAGIC) + 16:]
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return Fernet(key).decrypt(token)
