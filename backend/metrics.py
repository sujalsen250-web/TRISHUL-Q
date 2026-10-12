"""Server monitoring: real system metrics collection.

A background thread samples CPU / memory / active sessions / request
counters every few seconds into the `system_metrics` table. Values are
REAL measurements (psutil when available); nothing is faked. The admin
dashboard polls /api/admin/metrics and draws the line graph from this data.
"""
import threading
import time
from datetime import datetime, timezone

from . import db as dbm

try:
    import psutil
except ImportError:                      # metrics degrade gracefully
    psutil = None

_SAMPLE_INTERVAL_SECONDS = 5
_KEEP_LAST = 720                         # ~1 hour of samples

_running = threading.Event()
_thread: threading.Thread | None = None

_start_time = time.time()

# ---- live request counters (updated by middleware in main.py) --------------
_request_lock = threading.Lock()
_requests_total = 0
_response_times_ms: list[float] = []      # rolling window for average


def note_request(duration_ms: float) -> None:
    global _requests_total
    with _request_lock:
        _requests_total += 1
        _response_times_ms.append(duration_ms)
        if len(_response_times_ms) > 200:
            del _response_times_ms[:100]


def snapshot() -> dict:
    """Current real values (used for the API + sampled into the DB)."""
    with _request_lock:
        avg_ms = (sum(_response_times_ms) / len(_response_times_ms)
                  if _response_times_ms else 0.0)
        requests = _requests_total
    sessions = dbm.query_one(
        "SELECT COUNT(*) c FROM sessions WHERE expires_at >= ?",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),))["c"]
    messages = dbm.query_one("SELECT COUNT(*) c FROM messages")["c"]
    verifications = dbm.query_one(
        "SELECT COUNT(*) c FROM performance_metrics WHERE operation='verification'")["c"]
    cpu = psutil.cpu_percent(interval=None) if psutil else None
    mem = psutil.virtual_memory().percent if psutil else None
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cpu_percent": cpu,
        "mem_percent": mem,
        "active_sessions": sessions,
        "requests_total": requests,
        "messages_total": messages,
        "verifications": verifications,
        "avg_response_ms": round(avg_ms, 2),
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


def _collect_forever() -> None:
    while _running.is_set():
        try:
            snap = snapshot()
            dbm.execute(
                "INSERT INTO system_metrics(ts, cpu_percent, mem_percent, "
                "active_sessions, requests_total, messages_total, "
                "verifications, avg_response_ms) VALUES(?,?,?,?,?,?,?,?)",
                (snap["ts"], snap["cpu_percent"], snap["mem_percent"],
                 snap["active_sessions"], snap["requests_total"],
                 snap["messages_total"], snap["verifications"],
                 snap["avg_response_ms"]))
            # trim old samples
            if int(time.time()) % 60 == 0:
                dbm.execute(
                    "DELETE FROM system_metrics WHERE id < (SELECT MAX(id) FROM "
                    "system_metrics) - ?", (_KEEP_LAST,))
        except Exception:
            pass                       # monitoring must never crash the server
        time.sleep(_SAMPLE_INTERVAL_SECONDS)


def start_collector() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _running.set()
    _thread = threading.Thread(target=_collect_forever, daemon=True,
                               name="qds-metrics")
    _thread.start()


def series(limit: int = 60) -> list[dict]:
    """Recent samples for the admin line graph (oldest first)."""
    rows = dbm.query(
        "SELECT * FROM (SELECT * FROM system_metrics ORDER BY id DESC LIMIT ?) AS t "
        "ORDER BY id ASC", (max(1, min(limit, 500)),))
    return rows


def psutil_available() -> bool:
    return psutil is not None
