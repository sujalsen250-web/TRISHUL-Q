"""Persistence-layer tests (dialect-neutral; the same helpers run on PostgreSQL)."""
from __future__ import annotations

import pytest

from backend import db


@pytest.fixture(autouse=True)
def _schema():
    db.init_db()


def test_database_info_reports_dialect():
    info = db.database_info()
    assert info["dialect"] in ("postgresql", "sqlite")


def test_utcnow_is_iso():
    ts = db.utcnow()
    assert "T" in ts and len(ts) >= 19


def test_setting_upsert_roundtrip():
    db.set_setting("threshold_suspicious", "0.11")
    assert db.get_setting("threshold_suspicious") == "0.11"
    db.set_setting("threshold_suspicious", "0.12")   # ON CONFLICT update
    assert db.get_setting("threshold_suspicious") == "0.12"
    db.set_setting("threshold_suspicious", "0.10")


def test_execute_and_query():
    db.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               ("test_key", "test_value"))
    row = db.query_one("SELECT value FROM settings WHERE key=?", ("test_key",))
    assert row["value"] == "test_value"
    rows = db.query("SELECT key FROM settings WHERE key=?", ("test_key",))
    assert len(rows) == 1


def test_indexes_created():
    rows = db.query("SELECT name FROM sqlite_master WHERE type='index'") \
        if db.dialect() == "sqlite" else \
        db.query("SELECT indexname AS name FROM pg_indexes WHERE schemaname='public'")
    names = {r["name"] for r in rows}
    # at least the users / admin_requests indexes exist
    assert any("users" in n for n in names)
    assert any("adminreq" in n or "admin_requests" in n for n in names)
