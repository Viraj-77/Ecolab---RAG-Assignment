"""A2A message envelope — the single wire format every agent speaks."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class Envelope(BaseModel):
    """Wire format for every cross-agent message in the A2A system."""

    correlation_id: str = Field(default_factory=_new_id)
    """Same across every message in one user request — used to stitch a workflow's logs together."""

    causation_id: Optional[str] = None
    """The id of the message that caused this one — lets you reconstruct the call chain."""

    idempotency_key: str = Field(default_factory=_new_id)
    """Receiver dedupes on this — a retried envelope reuses the same key so the work runs once."""

    sender: str
    """Logical name of the agent emitting this envelope (matches its registry name)."""

    recipient: str
    """Logical name of the intended receiving agent (or capability when broadcasting)."""

    capability: str
    """The capability being invoked — e.g. ``answer-from-corpus``, ``propose-radar-change``."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """The actual request/response body — schema is per-capability, not enforced here."""

    timestamp: str = Field(default_factory=_now_iso)
    """ISO-8601 UTC instant the envelope was created — used for timeline ordering in traces."""

    message_id: str = Field(default_factory=_new_id)
    """Unique id for THIS envelope — distinct from idempotency_key (which a retry reuses)."""

    def reply(self, payload: dict[str, Any], sender: str) -> "Envelope":
        """Build a reply envelope: keeps correlation_id, sets causation_id to this message_id."""
        return Envelope(
            correlation_id=self.correlation_id,
            causation_id=self.message_id,
            sender=sender,
            recipient=self.sender,
            capability=self.capability,
            payload=payload,
        )

    def next_step(
        self, *, sender: str, recipient: str, capability: str, payload: dict[str, Any]
    ) -> "Envelope":
        """Build a downstream envelope in the same workflow (correlation preserved, new causation)."""
        return Envelope(
            correlation_id=self.correlation_id,
            causation_id=self.message_id,
            sender=sender,
            recipient=recipient,
            capability=capability,
            payload=payload,
        )


__all__ = ["Envelope"]
