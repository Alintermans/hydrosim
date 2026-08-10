"""In-process live updates (SSE).

Deliberately dumb: subscribers get a "something changed" ping and refetch
/api/state themselves — the stream never carries state, so a dropped message
can never leave a screen stale (the kiosk also polls every few seconds as a
belt-and-braces fallback).

In-process means: run ONE gunicorn worker (threads scale fine). See
gunicorn.conf.py; a second worker would only see half the pings.
"""

import json
import queue
import threading

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()

KEEPALIVE_S = 15


def publish(kind: str, event_slug: str = "") -> None:
    """Wake every listener. kind is informational ('lap', 'name', 'driver', 'event')."""
    payload = json.dumps({"kind": kind, "event": event_slug})
    with _lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(payload)
            except queue.Full:  # slow client: it will catch up via polling
                pass


def stream():
    """Generator for one SSE client."""
    q: queue.Queue = queue.Queue(maxsize=32)
    with _lock:
        _subscribers.append(q)
    try:
        yield "retry: 3000\n\n"
        while True:
            try:
                payload = q.get(timeout=KEEPALIVE_S)
                yield f"data: {payload}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"  # comment frame keeps proxies from closing us
    finally:
        with _lock:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass
