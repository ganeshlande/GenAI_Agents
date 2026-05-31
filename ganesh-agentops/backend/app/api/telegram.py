"""
Telegram integration status endpoint.

  GET  /api/telegram/status   – bot enabled/connected state, activity counters
  POST /api/telegram/send     – send an ad-hoc message to the configured chat_id
                                (only works when TELEGRAM_CHAT_ID is set)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status", summary="Telegram bot status")
async def telegram_status(request: Request) -> dict[str, Any]:
    """
    Returns the current state of the Telegram bot integration.

    - ``enabled``: True if TELEGRAM_BOT_TOKEN is configured.
    - ``connected``: True if the bot authenticated successfully and is polling.
    - ``username``: The bot's @handle on Telegram.
    - ``last_activity``: ISO timestamp of the last processed message.
    - ``total_messages``: How many Telegram messages have been handled.
    - ``total_runs``: How many workflow runs were triggered via Telegram.
    """
    bot = getattr(request.app.state, "telegram_bot", None)

    if bot is None:
        return {
            "enabled":        False,
            "connected":      False,
            "username":       None,
            "last_activity":  None,
            "total_messages": 0,
            "total_runs":     0,
            "hint": (
                "Set TELEGRAM_BOT_TOKEN in .env and restart the backend to enable "
                "Telegram integration.  See /docs for setup instructions."
            ),
        }

    return bot.status()


# ── Ad-hoc send ───────────────────────────────────────────────────────────────

class SendPayload(BaseModel):
    text: str
    chat_id: int | None = None   # overrides TELEGRAM_CHAT_ID if provided


@router.post("/send", summary="Send a message via the Telegram bot")
async def telegram_send(payload: SendPayload, request: Request) -> dict[str, Any]:
    """
    Send an ad-hoc HTML message through the bot.

    Requires the bot to be connected.  If ``chat_id`` is omitted, the
    configured ``TELEGRAM_CHAT_ID`` is used.
    """
    bot = getattr(request.app.state, "telegram_bot", None)

    if bot is None or not bot.connected:
        raise HTTPException(
            status_code=503,
            detail="Telegram bot is not connected.  Check TELEGRAM_BOT_TOKEN in .env.",
        )

    from app.config import settings

    target = payload.chat_id or (
        int(settings.TELEGRAM_CHAT_ID)
        if settings.TELEGRAM_CHAT_ID.strip().lstrip("-").isdigit()
        else None
    )

    if target is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No chat_id provided and TELEGRAM_CHAT_ID is not configured in .env."
            ),
        )

    await bot.send_message(target, payload.text)
    return {"ok": True, "chat_id": target}
