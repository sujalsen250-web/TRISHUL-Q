"""TRISHUL-Q persistence layer -- PostgreSQL (primary) via SQLAlchemy.

Complete replacement of the previous SQLite-only build:

  * PostgreSQL is the default, production datastore, reached through a pooled
    SQLAlchemy engine (pool_pre_ping + pool_size + max_overflow).
  * A SQLite fallback is available ONLY in non-production environments
    (development / the test-suite) when a PostgreSQL server is not reachable.
    In production the fallback is disabled and startup FAILS LOUDLY.
  * Indexes are created on every hot table.

The rest of the backend talks to the database through the small, driver-neutral
helpers below (``execute`` / ``query`` / ``query_one``) so the same code runs
unchanged on PostgreSQL and SQLite.  ``?`` placeholders in the SQL strings are
translated to SQLAlchemy named binds at call time.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from . import config

_ENGINE = None
_DIALECT = "postgresql"


# --------------------------------------------------------------- DDL ---------
# {PK} is replaced per-dialect with the auto-increment primary-key clause.
_DDL = """
CREATE TABLE IF NOT EXISTS roles (
    role_name   TEXT PRIMARY KEY,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id                   {PK},
    username             TEXT UNIQUE NOT NULL,
    password_hash        TEXT NOT NULL,
    role                 TEXT NOT NULL,
    capabilities         TEXT,
    device_ip            TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    last_seen            TEXT,
    last_login           TEXT,
    email                TEXT,
    phone                TEXT,
    aadhaar              TEXT,
    department_id        TEXT,
    department           TEXT,
    gender               TEXT,
    full_name            TEXT,
    auth_provider        TEXT DEFAULT 'password',
    must_change_password INTEGER DEFAULT 0,
    email_verified       INTEGER DEFAULT 0,
    created_by           TEXT,
    owner_admin          TEXT,
    is_active            INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    role       TEXT NOT NULL,
    ip         TEXT,
    created_at TEXT,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         {PK},
    token_hash TEXT UNIQUE NOT NULL,
    username   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at    TEXT
);

CREATE TABLE IF NOT EXISTS oauth_accounts (
    id               {PK},
    provider         TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    username         TEXT NOT NULL,
    email            TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE (provider, provider_user_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id         {PK},
    actor      TEXT,
    action     TEXT NOT NULL,
    target     TEXT,
    result     TEXT,
    ip         TEXT,
    detail     TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_events (
    id                  {PK},
    message_id          TEXT,
    signature_id        TEXT,
    classification      TEXT,
    action              TEXT,
    deviation           REAL,
    pauli_checks        INTEGER,
    pauli_mismatch_rate REAL,
    source              TEXT,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_metrics (
    id              {PK},
    ts              TEXT NOT NULL,
    cpu_percent     REAL,
    mem_percent     REAL,
    active_sessions INTEGER,
    requests_total  INTEGER,
    messages_total  INTEGER,
    verifications   INTEGER,
    avg_response_ms REAL
);

CREATE TABLE IF NOT EXISTS recovery (
    username    TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    answer_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              {PK},
    message_id      TEXT UNIQUE NOT NULL,
    sender_id       TEXT NOT NULL,
    receiver_id     TEXT NOT NULL,
    sender_ip       TEXT,
    receiver_ip     TEXT,
    message         TEXT,
    file_name       TEXT,
    file_path       TEXT,
    file_hash       TEXT,
    message_hash    TEXT NOT NULL,
    signature_id    TEXT NOT NULL,
    nonce           TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    status          TEXT NOT NULL,
    verdict         TEXT,
    deviation       REAL,
    created_at      TEXT NOT NULL,
    verified_at     TEXT,
    delivery_status TEXT DEFAULT 'PENDING',
    ack_at          TEXT,
    ack_note        TEXT
);

CREATE TABLE IF NOT EXISTS signatures (
    id                    {PK},
    signature_id          TEXT UNIQUE NOT NULL,
    message_id            TEXT,
    message_hash          TEXT NOT NULL,
    bell_state            TEXT NOT NULL,
    quantum_state         TEXT,
    seed                  BIGINT NOT NULL,
    n_qubits              INTEGER NOT NULL,
    n_measurements        INTEGER NOT NULL,
    measurement_result    TEXT,
    pauli_operation       TEXT,
    expected_distribution TEXT,
    teleports             TEXT,
    mac                   TEXT NOT NULL,
    sender_username       TEXT NOT NULL,
    sender_ip             TEXT,
    nonce                 TEXT NOT NULL,
    verification_status   TEXT,
    created_at            TEXT NOT NULL,
    generation_time_ms    REAL
);

CREATE TABLE IF NOT EXISTS security_events (
    id          {PK},
    event_type  TEXT NOT NULL,
    severity    TEXT NOT NULL,
    description TEXT,
    source      TEXT,
    target      TEXT,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS used_nonces (
    nonce        TEXT PRIMARY KEY,
    signature_id TEXT,
    used_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS support_messages (
    id         {PK},
    from_user  TEXT NOT NULL,
    to_user    TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at    TEXT
);

CREATE TABLE IF NOT EXISTS admin_messages (
    id         {PK},
    from_user  TEXT NOT NULL,
    to_user    TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at    TEXT
);

CREATE TABLE IF NOT EXISTS admin_requests (
    id                 {PK},
    request_id         TEXT UNIQUE NOT NULL,
    full_name          TEXT NOT NULL,
    email              TEXT NOT NULL,
    phone              TEXT,
    aadhaar            TEXT,
    department_id      TEXT,
    department         TEXT,
    gender             TEXT,
    status             TEXT NOT NULL DEFAULT 'PENDING',
    note               TEXT,
    created_at         TEXT NOT NULL,
    decided_at         TEXT,
    decided_by         TEXT,
    generated_password TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS performance_metrics (
    id          {PK},
    operation   TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    ref_id      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_snapshots (
    id          {PK},
    n_qubits    INTEGER NOT NULL,
    checks      INTEGER NOT NULL,
    p_forge     REAL NOT NULL,
    p_honest    REAL,
    payload     TEXT,
    created_at  TEXT NOT NULL
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_owner ON users(owner_admin);
CREATE INDEX IF NOT EXISTS ix_sessions_username ON sessions(username);
CREATE INDEX IF NOT EXISTS ix_signatures_sender ON signatures(sender_username);
CREATE INDEX IF NOT EXISTS ix_signatures_nonce ON signatures(nonce);
CREATE INDEX IF NOT EXISTS ix_messages_sender ON messages(sender_id);
CREATE INDEX IF NOT EXISTS ix_messages_receiver ON messages(receiver_id);
CREATE INDEX IF NOT EXISTS ix_messages_signature ON messages(signature_id);
CREATE INDEX IF NOT EXISTS ix_events_type ON security_events(event_type);
CREATE INDEX IF NOT EXISTS ix_events_ts ON security_events(timestamp);
CREATE INDEX IF NOT EXISTS ix_adminreq_status ON admin_requests(status);
CREATE INDEX IF NOT EXISTS ix_perf_op ON performance_metrics(operation);
CREATE INDEX IF NOT EXISTS ix_support_to ON support_messages(to_user);
CREATE INDEX IF NOT EXISTS ix_adminmsg_to ON admin_messages(to_user);
CREATE INDEX IF NOT EXISTS ix_reset_hash ON password_reset_tokens(token_hash);
CREATE INDEX IF NOT EXISTS ix_oauth_provider ON oauth_accounts(provider, provider_user_id);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS ix_verif_message ON verification_events(message_id);
"""

# Additive column migrations for databases created before this upgrade.
_COLUMN_MIGRATIONS = (
    ("users", "updated_at", "TEXT"),
    ("users", "last_login", "TEXT"),
    ("users", "auth_provider", "TEXT DEFAULT 'password'"),
    ("users", "must_change_password", "INTEGER DEFAULT 0"),
    ("users", "email_verified", "INTEGER DEFAULT 0"),
    ("users", "created_by", "TEXT"),
    ("users", "owner_admin", "TEXT"),
    ("users", "phone", "TEXT"),
    ("users", "aadhaar", "TEXT"),
    ("users", "department_id", "TEXT"),
    ("users", "gender", "TEXT"),
    ("sessions", "created_at", "TEXT"),
)

_ROLE_SEED = (
    ("superadmin", "Localhost-only super administrator"),
    ("admin", "Online administrator (manages senders)"),
    ("user", "Sender / Receiver (capability-based)"),
)


def _ddl_for(dialect: str) -> str:
    pk = ("SERIAL PRIMARY KEY" if dialect == "postgresql"
          else "INTEGER PRIMARY KEY AUTOINCREMENT")
    return _DDL.replace("{PK}", pk) + _INDEXES


# --------------------------------------------------------------- engine ------
def _build_engine():
    global _ENGINE, _DIALECT
    if _ENGINE is not None:
        return _ENGINE
    url = config.DATABASE_URL
    if url.startswith("sqlite"):
        _ENGINE = create_engine(url, connect_args={"check_same_thread": False},
                                future=True)
        _DIALECT = "sqlite"
        return _ENGINE
    try:
        eng = create_engine(
            url, future=True, pool_pre_ping=True,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_MAX_OVERFLOW,
            pool_timeout=config.DB_POOL_TIMEOUT,
        )
        with eng.connect() as conn:            # fail fast if unreachable
            conn.execute(text("SELECT 1"))
        _ENGINE, _DIALECT = eng, "postgresql"
    except Exception as exc:
        if config.IS_PRODUCTION or not config.ALLOW_SQLITE_FALLBACK:
            raise RuntimeError(
                f"PostgreSQL is required but unreachable: {exc}. "
                f"Start PostgreSQL (docker compose up -d db) and check "
                f"DATABASE_URL. TRISHUL-Q runs on PostgreSQL ONLY -- there is "
                f"no SQLite fallback."
            ) from exc
        print(f"  [TRISHUL-Q] PostgreSQL unreachable ({exc.__class__.__name__}); "
              f"development fallback -> SQLite at {config.SQLITE_PATH}")
        _ENGINE = create_engine(f"sqlite:///{config.SQLITE_PATH}",
                                connect_args={"check_same_thread": False},
                                future=True)
        _DIALECT = "sqlite"
    return _ENGINE


def engine():
    return _build_engine() if _ENGINE is None else _ENGINE


def dialect() -> str:
    engine()
    return _DIALECT


def reset_engine() -> None:
    """Drop the cached engine (used by tests)."""
    global _ENGINE
    _ENGINE = None


# ------------------------------------------------------- bind translation ----
_BIND_RE = re.compile(r"\?")


def _prepare(sql: str, params: tuple) -> tuple[str, dict]:
    names = []

    def _sub(_m):
        name = f"p{len(names)}"
        names.append(name)
        return ":" + name

    prepared = _BIND_RE.sub(_sub, sql)
    binds = {name: (params[i] if i < len(params) else None)
             for i, name in enumerate(names)}
    return prepared, binds


@contextmanager
def db():
    conn = engine().connect()
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------- helpers -------
def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def execute(sql: str, params: tuple = ()):
    prepared, binds = _prepare(sql, params)
    with engine().begin() as conn:
        result = conn.execute(text(prepared), binds)
        return getattr(result, "lastrowid", None) or result.rowcount


def executemany(sql: str, seq_of_params: list[tuple]):
    if not seq_of_params:
        return
    prepared, _ = _prepare(sql, seq_of_params[0])
    binds = [_prepare(sql, p)[1] for p in seq_of_params]
    with engine().begin() as conn:
        conn.execute(text(prepared), binds)


def query(sql: str, params: tuple = ()) -> list[dict]:
    prepared, binds = _prepare(sql, params)
    with engine().connect() as conn:
        rows = conn.execute(text(prepared), binds).mappings().all()
        return [dict(r) for r in rows]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def _migrate() -> None:
    """Additive, idempotent column migrations (each in its own transaction)."""
    for table, column, ctype in _COLUMN_MIGRATIONS:
        try:
            execute(f"ALTER TABLE {table} ADD COLUMN {column} {ctype}")
        except Exception:
            pass  # column already exists


def init_db() -> None:
    ddl = _ddl_for(dialect())
    with engine().begin() as conn:
        for statement in ddl.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    _migrate()
    for role_name, desc in _ROLE_SEED:
        try:
            execute("INSERT INTO roles(role_name, description) VALUES(?,?) "
                    "ON CONFLICT(role_name) DO UPDATE SET description=excluded.description",
                    (role_name, desc))
        except Exception:
            pass


def database_info() -> dict:
    return {"dialect": dialect(), "pooled": dialect() == "postgresql",
            "fallback_sqlite": dialect() == "sqlite", "env": config.APP_ENV}


def database_status() -> dict:
    """Connectivity + schema check for the startup banner."""
    try:
        one = query_one("SELECT 1 AS ok")
        tables = _list_tables()
        required = {"users", "sessions", "roles", "password_reset_tokens",
                    "oauth_accounts", "audit_logs", "security_events", "messages",
                    "signatures", "verification_events"}
        missing = sorted(required - set(tables))
        return {
            "connected": bool(one and one.get("ok") == 1),
            "dialect": dialect(),
            "tables": len(tables),
            "missing_tables": missing,
            "ready": not missing,
        }
    except Exception as exc:
        return {"connected": False, "dialect": dialect(), "error": str(exc),
                "ready": False}


def _list_tables() -> list[str]:
    if dialect() == "sqlite":
        rows = query("SELECT name FROM sqlite_master WHERE type='table'")
        return [r["name"] for r in rows]
    rows = query("SELECT tablename AS name FROM pg_tables WHERE schemaname='public'")
    return [r["name"] for r in rows]


# ------------------------------------------------------------- settings ------
DEFAULT_SETTINGS = {
    "threshold_suspicious": str(config.DEFAULT_THRESHOLD_SUSPICIOUS),
    "threshold_threat": str(config.DEFAULT_THRESHOLD_THREAT),
    "n_measurements": str(config.DEFAULT_N_MEASUREMENTS),
    "n_qubits": str(config.DEFAULT_N_QUBITS),
    "default_bell_state": config.DEFAULT_BELL_STATE,
    "replay_window_seconds": str(config.REPLAY_WINDOW_SECONDS),
    "pauli_mismatch_threshold": "0.30",
}


def get_setting(key: str) -> str:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else DEFAULT_SETTINGS.get(key, "")


def get_settings() -> dict:
    stored = {r["key"]: r["value"] for r in query("SELECT key, value FROM settings")}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(stored)
    return merged


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
