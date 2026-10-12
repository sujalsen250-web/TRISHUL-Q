"""Central configuration for TRISHUL-Q.

TRISHUL-Q
  Full form: Threat Recognition, Identification & Signature Handling under
  Unified Logic -- Quantum

  "Teen shool" = three detection layers (three-prong motif):
      Layer 1 -- Teleportation / Bell-state integrity
      Layer 2 -- Pauli-eigenstate (X/Y/Z) basis verification + QBER
      Layer 3 -- Statistical (Hoeffding / deviation) + forgery-probability

Everything configurable lives here. A tiny .env loader reads the project-root
.env file (no external dependency); real secrets never go into source control
-- see .env.example.

Roles (three security roles):
    superadmin  -- LOCALHOST ONLY, separate simple panel
    admin       -- online (public domain / LAN)
    user        -- Sender / Receiver, capability-based ('send' / 'receive')
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------ .env loader ----
def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:      # real env vars win
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv()


def _env(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    return default if value is None else value.strip()


def _flag(key: str, default: bool = False) -> bool:
    return _env(key, "1" if default else "0").lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------- branding ------
APP_NAME = "TRISHUL-Q"
APP_FULL_NAME = ("Threat Recognition, Identification & Signature Handling "
                 "under Unified Logic — Quantum")
APP_TAGLINE = "Teen Shool — three detection layers, one unified QDS logic."
VERSION = "2.0.0"

# ----------------------------------------------------------------- env -------
# development | production.  In production there is NO silent SQLite fallback.
APP_ENV = _env("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV in ("production", "prod")


# ----------------------------------------------------------------- paths -----
DATA_DIR = Path(_env("TRISHUL_DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = Path(_env("TRISHUL_UPLOAD_DIR", str(BASE_DIR / "uploads")))
FRONTEND_DIST = Path(_env("TRISHUL_FRONTEND_DIST", str(BASE_DIR / "frontend" / "dist")))
FRONTEND_SRC = BASE_DIR / "frontend"
SUPERADMIN_DIR = Path(_env("TRISHUL_SUPERADMIN_DIR", str(BASE_DIR / "superadmin")))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SECRET_PATH = DATA_DIR / "secret.key"
SQLITE_PATH = DATA_DIR / "trishulq.db"

# --------------------------------------------------------------- database ----
# PostgreSQL is the ONLY supported datastore. There is no silent SQLite
# fallback: if PostgreSQL is unreachable, startup fails loudly. (The test
# suite points DATABASE_URL straight at a throw-away SQLite file, which is
# allowed because that is an explicit sqlite:// URL, not a fallback.)
DATABASE_URL = _env(
    "DATABASE_URL",
    "postgresql+psycopg2://trishul:trishul@localhost:15432/trishulq",
)
# Kept for backward compatibility, but SQLite fallback is DISABLED by default.
ALLOW_SQLITE_FALLBACK = _flag("TRISHUL_DB_FALLBACK", default=False)
DB_POOL_SIZE = int(_env("TRISHUL_DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(_env("TRISHUL_DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(_env("TRISHUL_DB_POOL_TIMEOUT", "30"))

# ---------------------------------------------------------------- server -----
APP_MODE = _env("APP_MODE", "lan").lower()          # local | lan | live
HOST = _env("TRISHUL_HOST", "0.0.0.0")
PORT = int(_env("TRISHUL_PORT", "8000"))

# --------------------------------------------------------------- security ----
SESSION_COOKIE = "trishul_session"
SESSION_TTL_SECONDS = 12 * 3600
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "[::1]"}
SUPERADMIN_PATH_PREFIXES = ("/superadmin", "/api/superadmin")

# SECRET_KEY / SESSION_SECRET -- if unset, a random one is generated per boot
# (sessions still survive restarts because they are DB-backed; the secret is
# used for signing auxiliary material).
SECRET_KEY = _env("SECRET_KEY") or _env("TRISHUL_SECRET_KEY")
SESSION_SECRET = _env("SESSION_SECRET") or SECRET_KEY

MAX_FILE_SIZE = int(_env("TRISHUL_MAX_FILE_SIZE", 25 * 1024 * 1024))  # 25 MB
ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".rtf", ".odt",
    ".doc", ".docx", ".ppt", ".pptx", ".pps", ".ppsx",
    ".xls", ".xlsx", ".csv", ".tsv", ".ods", ".odp",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".tif", ".tiff", ".heic", ".avif",
    ".mp3", ".wav", ".mp4", ".mkv", ".mov", ".webm",
    ".json", ".xml", ".yaml", ".yml", ".html", ".htm", ".log",
    ".py", ".js", ".css", ".java", ".c", ".cpp", ".ipynb",
    ".zip", ".tar", ".gz", ".7z", ".rar",
}

# ------------------------------------------------------------ accounts -------
SUPERADMIN_USERNAME = _env("TRISHUL_SUPERADMIN_USERNAME", "superadmin")
DEFAULT_SUPERADMIN_PASSWORD = _env("TRISHUL_SUPERADMIN_PASSWORD", "TrishulQ@2026")
SEED_DEFAULT_ADMIN = _flag("TRISHUL_SEED_DEFAULT_ADMIN", default=False)
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = _env("TRISHUL_DEFAULT_ADMIN_PASSWORD", "TrishulAdmin@2026")

# The Super Admin's own email -- welcome credentials are sent here for review.
SUPER_ADMIN_EMAIL = _env("SUPER_ADMIN_EMAIL")

ROLES = ("superadmin", "admin", "user")
CAPABILITIES = ("send", "receive")

# --------------------------------------------------------------- password ----
PASSWORD_MIN_LENGTH = int(_env("TRISHUL_PASSWORD_MIN_LENGTH", "8"))
# Reset tokens: single-use, hashed at rest, expire after this many seconds.
PASSWORD_RESET_TTL_SECONDS = int(_env("TRISHUL_RESET_TTL_SECONDS", "3600"))
EMAIL_VERIFICATION_REQUIRED = _flag("TRISHUL_EMAIL_VERIFICATION_REQUIRED", default=False)

# ------------------------------------------------------------- rate limits ---
LOGIN_MAX_ATTEMPTS = int(_env("TRISHUL_LOGIN_MAX_ATTEMPTS", "6"))
LOGIN_WINDOW_SECONDS = int(_env("TRISHUL_LOGIN_WINDOW_SECONDS", "300"))
RESET_MAX_REQUESTS = int(_env("TRISHUL_RESET_MAX_REQUESTS", "4"))
RESET_WINDOW_SECONDS = int(_env("TRISHUL_RESET_WINDOW_SECONDS", "900"))

# ---------------------------------------------------------------- google -----
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _env("GOOGLE_CLIENT_SECRET")
# Optional explicit override; when empty the callback URL is derived from the
# request (so localhost AND ngrok/public URLs both work).
GOOGLE_REDIRECT_URI = _env("GOOGLE_REDIRECT_URI")


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


# ------------------------------------------------------------------ mail -----
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_USERNAME = _env("SMTP_USERNAME") or _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
SMTP_FROM_EMAIL = _env("SMTP_FROM_EMAIL") or _env("SMTP_FROM") or SMTP_USERNAME
SMTP_FROM_NAME = _env("SMTP_FROM_NAME", APP_NAME)
SMTP_USE_TLS = _flag("SMTP_USE_TLS", default=True)
SMTP_USE_SSL = _flag("SMTP_USE_SSL", default=False)


def smtp_configured() -> bool:
    return bool(SMTP_HOST)


# ------------------------------------------------------------------ URLs -----
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", f"http://localhost:{PORT}")


def _lan_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


LOCAL_SUPERADMIN_URL = f"http://127.0.0.1:{PORT}/superadmin"
LOCAL_USER_URL = f"http://localhost:{PORT}"
LAN_USER_URL = f"http://{_lan_ip()}:{PORT}"

# ---------------------------------------------------------------- quantum ----
DEFAULT_N_QUBITS = 48
DEFAULT_N_MEASUREMENTS = 1000
DEFAULT_BELL_STATE = "PHI_PLUS"
SIGNATURE_TTL_SECONDS = 60

# -------------------------------------------------------------- detection ----
DEFAULT_THRESHOLD_SUSPICIOUS = 0.10
DEFAULT_THRESHOLD_THREAT = 0.20
REPLAY_WINDOW_SECONDS = 300
ONLINE_WINDOW_SECONDS = 90


def get_or_create_secret() -> bytes:
    """Server-side HMAC secret, created once and persisted in data/."""
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    key = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(key)
    return key


def url_summary() -> dict:
    return {
        "mode": APP_MODE,
        "env": APP_ENV,
        "superadmin_url": LOCAL_SUPERADMIN_URL,
        "local_user_url": LOCAL_USER_URL,
        "lan_user_url": LAN_USER_URL,
        "public_base_url": PUBLIC_BASE_URL,
        "note_superadmin_local_only": "Super Admin panel is enforced localhost-only "
                                      "on the server side in every mode.",
    }
