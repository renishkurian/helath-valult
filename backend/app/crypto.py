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
