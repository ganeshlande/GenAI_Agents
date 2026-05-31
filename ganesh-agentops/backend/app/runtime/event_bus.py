"""
In-process, thread-safe event bus with per-run event store.

The sync agent runtime writes events from a thread-pool thread;
the async SSE handler reads from the asyncio event loop.
A threading.Lock keeps both sides safe without any external dependencies.

In a production setup this would be replaced with Redis Pub/Sub or a
message broker so multiple server processes can share the event stream.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Event types that signal the workflow has finished
_TERMINAL_TYPES: frozenset[str] = frozenset({"workflow_end", "workflow_error"})


@dataclass
class RunEvent:
    run_id: int
    event_id: int          # sequential within the run
    timestamp: str         # ISO-8601 UTC
    event_type: str        # workflow_start|workflow_end|workflow_error|
                           # agent_start|agent_end|agent_message|
                           # tool_call|tool_result|guardrail_blocked
    sender_agent: str | None
    receiver_agent: str | None
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Encode as a single SSE data frame (terminated with \\n\\n)."""
        return f"data: {json.dumps(asdict(self), ensure_ascii=False)}\n\n"

    def to_dict(self) -> dict:
        return asdict(self)


class EventBus:
    """
    Per-run event store with O(1) publish and O(k) cursor-based reads.

    All public methods are safe to call from any thread.
    """

    def __init__(self) -> None:
        self._store: dict[int, list[RunEvent]] = {}
        self._lock = threading.Lock()

    # ── Write ─────────────────────────────────────────────────────────────────

    def publish(
        self,
        run_id: int,
        event_type: str,
        content: str,
        sender_agent: str | None = None,
        receiver_agent: str | None = None,
        metadata: dict | None = None,
    ) -> RunEvent:
        """Append an event and return it."""
        with self._lock:
            bucket = self._store.setdefault(run_id, [])
            evt = RunEvent(
                run_id=run_id,
                event_id=len(bucket),
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=event_type,
                sender_agent=sender_agent,
                receiver_agent=receiver_agent,
                content=content,
                metadata=metadata or {},
            )
            bucket.append(evt)
            return evt

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_events(self, run_id: int, after: int = 0) -> list[RunEvent]:
        """Return all events for run_id with event_id >= after."""
        with self._lock:
            return list(self._store.get(run_id, [])[after:])

    def event_count(self, run_id: int) -> int:
        with self._lock:
            return len(self._store.get(run_id, []))

    def is_terminal(self, run_id: int) -> bool:
        """True if a terminal event (workflow_end / workflow_error) has been published."""
        with self._lock:
            return any(
                e.event_type in _TERMINAL_TYPES
                for e in self._store.get(run_id, [])
            )

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def clear(self, run_id: int) -> None:
        with self._lock:
            self._store.pop(run_id, None)

    def run_ids(self) -> list[int]:
        with self._lock:
            return list(self._store.keys())


# ── Singleton used across the whole process ───────────────────────────────────
bus = EventBus()
