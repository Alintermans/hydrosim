"""Gunicorn configuration.

ONE worker, many threads — deliberate and load-bearing: the SSE broadcaster
(live.py) is in-process, so a second worker would only reach half the screens.
Threads carry the open SSE connections; 32 covers a healthy event audience,
and the JS polling fallback covers any overflow.
"""

import os

bind = os.environ.get("BIND", "0.0.0.0:8000")
workers = 1
threads = int(os.environ.get("THREADS", "32"))
worker_class = "gthread"
timeout = int(os.environ.get("TIMEOUT", "120"))
graceful_timeout = 15
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")
