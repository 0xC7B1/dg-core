"""Event dispatcher — the single entry point for all game events."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import GameEvent
from app.models.result import EngineResult

logger = logging.getLogger(__name__)

HandlerFn = Callable[[AsyncSession, GameEvent], Awaitable[EngineResult]]
_handlers: dict[str, HandlerFn] = {}
_registered = False


def register_handler(event_type: str, handler: HandlerFn) -> None:
    """Register a handler function for an event type."""
    _handlers[event_type] = handler


def _ensure_registered() -> None:
    """Lazy-import all handler modules to trigger registration."""
    global _registered
    if _registered:
        return
    import app.domain.mechanics.checks  # noqa: F401
    import app.domain.mechanics.combat  # noqa: F401
    import app.domain.mechanics.communication  # noqa: F401
    import app.domain.mechanics.lifecycle  # noqa: F401
    import app.domain.mechanics.management  # noqa: F401
    import app.domain.mechanics.state  # noqa: F401
    _registered = True


async def dispatch(db: AsyncSession, event: GameEvent) -> EngineResult:
    """Route a GameEvent to its handler and return an EngineResult."""
    _ensure_registered()
    et = event.payload.event_type
    handler = _handlers.get(et)
    if handler is None:
        return EngineResult(
            success=False, event_type=et, error=f"Unknown event type: {et}"
        )
    try:
        return await handler(db, event)
    except Exception as exc:
        logger.exception("Dispatch error for %s", et)
        return EngineResult(success=False, event_type=et, error=str(exc))
