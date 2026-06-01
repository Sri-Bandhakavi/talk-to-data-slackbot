from __future__ import annotations


class InMemoryEventDeduper:
    """Process-local deduper for Slack ``event_id`` values.

    Resets when the process restarts. Suitable for MVP idempotency only.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(self, event_id: str) -> bool:
        """Return True if this ``event_id`` was previously marked seen."""
        return event_id in self._seen

    def mark(self, event_id: str) -> None:
        """Record an ``event_id`` as seen."""
        self._seen.add(event_id)
