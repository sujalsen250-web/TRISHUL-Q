"""In-process event bus used to push live security notifications over SSE."""
import asyncio
import json
from datetime import datetime, timezone


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, event: dict) -> None:
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


BUS = EventBus()


def emit(event_type: str, severity: str, description: str,
         source: str | None = None, target: str | None = None,
         extra: dict | None = None) -> dict:
    """Record a security event in the DB and push it to live subscribers."""
    event = {
        "event_type": event_type,
        "severity": severity,
        "description": description,
        "source": source,
        "target": target,
    }
    if extra:
        event.update(extra)
    from . import db as dbm  # local import avoids a cycle

    dbm.execute(
        "INSERT INTO security_events(event_type, severity, description, source, target, timestamp) "
        "VALUES(?,?,?,?,?,?)",
        (event_type, severity, description, source, target,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    BUS.publish(event)
    return event


def dumps(event: dict) -> str:
    return json.dumps(event, default=str)
