from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
load_dotenv()
class Settings:
    # --- Database ---
    # MySQL (matches your existing Pi stack), falls back to SQLite for local testing.
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./healthvault.db"
        # Example for MySQL on the Pi:
        # "mysql+pymysql://healthvault:CHANGE_ME@127.0.0.1:3306/healthvault"
    )

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "CHANGE_ME_dev_only_secret")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    # Fallbacks when Super Admin → Server settings has not saved these yet.
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    ONLINE_WINDOW_MINUTES: int = int(os.getenv("ONLINE_WINDOW_MINUTES", "5"))
    # Empty keys disable the widget and the server check (tests, local Pi).
    RECAPTCHA_SITE_KEY: str = os.getenv("RECAPTCHA_SITE_KEY", "").strip()
    RECAPTCHA_SECRET: str = os.getenv("RECAPTCHA_SECRET", "").strip()
    # Optional bootstrap: create or promote this account to superadmin on startup.
    SUPERADMIN_EMAIL: str = os.getenv("SUPERADMIN_EMAIL", "").strip().lower()
    SUPERADMIN_PASSWORD: str = os.getenv("SUPERADMIN_PASSWORD", "")
    SUPERADMIN_NAME: str = os.getenv("SUPERADMIN_NAME", "Super Admin").strip() or "Super Admin"

    # --- Encryption ---
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    MASTER_KEY: str = os.getenv("MASTER_KEY", "")

    # --- Storage ---
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", "./storage")).resolve()
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25"))

    # --- CORS ---
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",")

    # Optional Firebase service-account JSON (HTTP v1). Prefer Super Admin.
    # Leave empty to rely on on-device AlarmManager / in-app poll only.
    FCM_SERVICE_ACCOUNT_JSON: str = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "")

    # One OAuth Web client for the whole server. Users only click Connect.
    # Create in Google Cloud → APIs & Services → Credentials (Drive API on).
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    # Folder Syncthing / a USB disk can watch. Empty = no on-disk snapshot.
    BACKUP_DIR: Path | None = Path(p).resolve() if (p := os.getenv("BACKUP_DIR", "").strip()) else None

    # Optional system mailer (Super Admin default). Custom SMTP overrides in Server settings.
    SYSTEM_SMTP_HOST: str = os.getenv("SYSTEM_SMTP_HOST", "127.0.0.1").strip()
    SYSTEM_SMTP_PORT: int = int(os.getenv("SYSTEM_SMTP_PORT", "25"))
    SYSTEM_SMTP_USER: str = os.getenv("SYSTEM_SMTP_USER", "").strip()
    SYSTEM_SMTP_PASSWORD: str = os.getenv("SYSTEM_SMTP_PASSWORD", "")
    SYSTEM_MAIL_FROM: str = os.getenv("SYSTEM_MAIL_FROM", "vault@localhost").strip() or "vault@localhost"
    SYSTEM_SMTP_TLS: bool = os.getenv("SYSTEM_SMTP_TLS", "").strip().lower() in ("1", "true", "yes")
    SHARE_IDLE_DAYS: int = int(os.getenv("SHARE_IDLE_DAYS", "14"))
    OCR_LANGS: str = os.getenv("OCR_LANGS", "eng+mal+tam+hin")

settings = Settings()
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

if not settings.MASTER_KEY:
    # Fail loudly rather than silently storing medical data unencrypted.
    raise RuntimeError(
        "MASTER_KEY is not set. Generate one with:\n"
        "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
        "and put it in your .env as MASTER_KEY=..."
    )
