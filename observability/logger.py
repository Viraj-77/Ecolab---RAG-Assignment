"""Append-only JSON-line logger shared by orchestrator and (optionally) agents.

Design:
- Every line is one JSON object.
- Every line carries: ``ts`` (ISO-8601), ``correlation_id``, ``causation_id``,
  ``sender``, ``recipient``, ``capability``, ``event``, plus any extras the
  caller passes.
- The sink is a single ndjson file. We rely on POSIX append-mode atomicity
  for short writes — fine for laptop-scale; not fine for a real production
  fleet (see docs/observability-walkthrough.md for the reasoning).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path(os.environ.get("A2A_LOG_PATH", REPO_ROOT / "observability" / "logs.ndjson"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_logger = logging.getLogger("a2a.events")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_root(level: int = logging.INFO) -> None:
    """Wire stdlib logging to stderr at the given level. Call once at process startup.

    Keeps stdlib logs separate from the structured event sink — stdlib goes to
    stderr (uvicorn / our own diagnostics), event log goes to the ndjson file.
    """
    if logging.getLogger().handlers:
        return
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(h)


def log_event(
    *,
    event: str,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    sender: Optional[str] = None,
    recipient: Optional[str] = None,
    capability: Optional[str] = None,
    **extras: Any,
) -> dict[str, Any]:
    """Write one structured event line. Returns the dict that was written
    so callers can stash it (e.g. for assertions in tests)."""
    record: dict[str, Any] = {
        "ts": _iso_now(),
        "event": event,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "sender": sender,
        "recipient": recipient,
        "capability": capability,
    }
    # Merge extras last so caller-supplied keys can override (rare but useful
    # for back-filling a synthetic ts in tests).
    record.update(extras)
    line = json.dumps(record, default=str, ensure_ascii=False) + "\n"
    with _lock:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    _logger.debug("event %s corr=%s", event, correlation_id)
    return record


__all__ = ["log_event", "configure_root", "LOG_PATH"]
