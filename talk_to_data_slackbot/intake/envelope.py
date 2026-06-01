from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestEnvelope:
    """Normalized analytics request produced by Intake for Router."""

    event_id: str
    channel_id: str
    user_id: str
    text: str
    thread_ts: str | None = None
