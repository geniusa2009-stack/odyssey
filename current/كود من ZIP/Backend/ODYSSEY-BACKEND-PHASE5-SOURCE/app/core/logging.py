"""Structured JSON logging with request/mission context and secret redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id", default=None
)
timeline_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "timeline_id", default=None
)
simulation_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "simulation_run_id", default=None
)
state_version_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "state_version", default=None
)
decision_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "decision_id", default=None
)
scenario_version_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "scenario_version", default=None
)

_CONTEXT_VARS: dict[str, contextvars.ContextVar[Any]] = {
    "request_id": request_id_var,
    "mission_session_id": session_id_var,
    "timeline_id": timeline_id_var,
    "simulation_run_id": simulation_run_id_var,
    "state_version": state_version_var,
    "decision_id": decision_id_var,
    "scenario_version": scenario_version_var,
}
# All per-request context variables (reset by RequestContextMiddleware).
REQUEST_CONTEXT_VARS: tuple[contextvars.ContextVar[Any], ...] = tuple(_CONTEXT_VARS.values())
_EXTRA_FIELDS = (
    "event_type",
    "error_code",
    "duration_ms",
    "status_code",
    "method",
    "path",
    "detail",
    "ticks",
    "tick",
    "event_id",
    "events_published",
    "idempotent_replay",
    # game backend (odyssey.game.v1)
    "game_session_id",
    "game_timeline_id",
    "game_state_version",
    "action_id",
    "action_type",
    "mission",
    "result",
    "reason",
)
SENSITIVE_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if any(m in k.lower() for m in SENSITIVE_MARKERS) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name, var in _CONTEXT_VARS.items():
            value = var.get()
            if value is not None:
                payload[name] = value
        for name in _EXTRA_FIELDS:
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(redact(payload), default=str)


_QUERY_SECRET = re.compile(r"([?&](?:token|access_token|api_key)=)[^&\s\"']+", re.IGNORECASE)


class QuerySecretFilter(logging.Filter):
    """Redacts secrets passed in URL query strings (``?token=`` on the game WebSocket) from
    log lines, including the server's own ("WebSocket /path?token=… [accepted]")."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record: leave it alone
            return True
        redacted = _QUERY_SECRET.sub(r"\1[REDACTED]", message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    secret_filter = QuerySecretFilter()
    handler.addFilter(secret_filter)
    for server_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(server_logger)
        if not any(isinstance(f, QuerySecretFilter) for f in target.filters):
            target.addFilter(secret_filter)
