"""
Telegram Bot integration for Ganesh AgentOps.

Uses the Telegram Bot API directly via httpx — no extra dependencies beyond
what is already installed.  The polling loop runs as a background asyncio
task started during FastAPI lifespan.

Behaviour
─────────
• /start | /help  → welcome message with usage instructions
• /demo           → trigger Payment Failure Investigation with PAY-10291
• PAY-XXXXX text  → trigger investigation for that payment ID
• any other text  → treated as a free-form payment investigation request

Every inbound Telegram message AND outbound reply are persisted to the
database with channel="telegram" so they appear in the run monitor UI with
the correct run_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_PAY_ID_RE = re.compile(r"\bPAY-[\w-]+", re.IGNORECASE)
_TKT_RE    = re.compile(r"TKT-\d+")

_WELCOME = (
    "👋 <b>Welcome to Ganesh AgentOps!</b>\n\n"
    "I can investigate failed payment transactions using a 4-agent AI pipeline.\n\n"
    "<b>Commands:</b>\n"
    "• /demo — run the Payment Failure demo (PAY-10291)\n"
    "• /start — show this message\n\n"
    "<b>Examples:</b>\n"
    "  <code>PAY-10291 failed — card declined</code>\n"
    "  <code>Payment failure for transaction PAY-99999</code>"
)

_DEMO_INPUT = (
    "Customer reports payment failure for order PAY-10291. "
    "Card declined with error CARD_DECLINED. Please investigate and recommend next action."
)


# ── Bot class ─────────────────────────────────────────────────────────────────

class TelegramBot:
    """
    Lightweight Telegram polling bot backed by httpx.

    Starts/stops as an asyncio background task.  All mutable state is either
    accessed only from the event loop or protected by the GIL (simple
    assignments), so no explicit locks are needed for read-heavy fields like
    counters and timestamps.

    ssl_verify=False is provided for dev machines behind corporate proxies that
    intercept TLS (e.g. some Windows/macOS enterprise setups).  Never set this
    to False in production.
    """

    def __init__(self, token: str, session_factory: Callable, chat_id: str = "",
                 ssl_verify: bool = True):
        self._token          = token
        self._session_factory = session_factory
        self._ssl_verify     = ssl_verify
        self._notify_chat_id = int(chat_id) if chat_id.strip().lstrip("-").isdigit() else None
        self._base           = f"https://api.telegram.org/bot{token}"
        self._task: asyncio.Task | None = None
        self._running        = False

        # Exposed to the status endpoint
        self.connected       = False
        self.bot_username: str | None = None
        self.last_activity: str | None = None
        self.total_messages  = 0
        self.total_runs      = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Verify token and start background polling."""
        if self._task and not self._task.done():
            return

        try:
            info = await self._api("getMe")
            me = info.get("result", {})
            self.bot_username = me.get("username")
            self.connected    = True
            logger.info("[Telegram] Bot @%s connected", self.bot_username)
        except Exception as exc:
            logger.warning("[Telegram] Could not authenticate: %s — bot disabled", exc)
            self.connected = False
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="telegram-poll")

        # Optional startup ping to a configured chat
        if self._notify_chat_id:
            try:
                await self._send(
                    self._notify_chat_id,
                    "🤖 <b>Ganesh AgentOps Bot started.</b>\n"
                    "Send /demo to run the Payment Failure investigation.",
                )
            except Exception:
                pass  # Non-fatal

    async def stop(self) -> None:
        """Cancel the polling task and mark as disconnected."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.connected = False
        logger.info("[Telegram] Bot stopped")

    def status(self) -> dict[str, Any]:
        return {
            "enabled":        True,
            "connected":      self.connected,
            "username":       self.bot_username,
            "last_activity":  self.last_activity,
            "total_messages": self.total_messages,
            "total_runs":     self.total_runs,
        }

    async def send_message(self, chat_id: int, text: str) -> None:
        """Public API for ad-hoc sends from other parts of the app."""
        await self._send(chat_id, text)

    # ── Polling loop ──────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        offset = 0
        logger.info("[Telegram] Long-poll loop started")

        while self._running:
            try:
                data = await self._api(
                    "getUpdates",
                    params={
                        "offset":          offset,
                        "timeout":         20,           # long-poll up to 20 s
                        "allowed_updates": ["message"],
                    },
                    timeout=30.0,
                )
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        await self._handle_update(upd)
                    except Exception:
                        logger.exception("[Telegram] Unhandled error in update dispatch")

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                # Normal: long-poll returned nothing after 20 s
                continue
            except Exception as exc:
                logger.warning("[Telegram] Poll error: %s — retry in 5 s", exc)
                await asyncio.sleep(5)

        logger.info("[Telegram] Poll loop exited")

    # ── Update dispatch ───────────────────────────────────────────────────────

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message")
        if not msg:
            return

        text      = (msg.get("text") or "").strip()
        chat_id   = msg["chat"]["id"]
        from_user = msg.get("from", {}).get("username") or str(chat_id)

        if not text:
            return

        self.total_messages += 1
        self.last_activity   = datetime.now(timezone.utc).isoformat()
        logger.info("[Telegram] @%s → %r", from_user, text[:120])

        lower = text.lower()

        if lower in ("/start", "/help"):
            await self._send(chat_id, _WELCOME)
            return

        if lower == "/demo":
            await self._send(
                chat_id,
                "⏳ <b>Running Payment Failure demo</b>\n"
                "Investigating <code>PAY-10291</code> — this takes ~2 seconds…",
            )
            await self._run_investigation(chat_id, _DEMO_INPUT, from_user)
            return

        # Any free-form message: treat as investigation request
        preview = text[:100] + ("…" if len(text) > 100 else "")
        pay_ids = _PAY_ID_RE.findall(text)
        if pay_ids:
            await self._send(
                chat_id,
                f"🔍 Investigating <code>{pay_ids[0]}</code>…",
            )
        else:
            await self._send(
                chat_id,
                f"🔍 Starting investigation…\n<i>{preview}</i>",
            )

        await self._run_investigation(chat_id, text, from_user)

    # ── Workflow execution ────────────────────────────────────────────────────

    async def _run_investigation(
        self, chat_id: int, user_message: str, from_user: str
    ) -> None:
        """
        Execute the Payment Failure Investigation workflow:
        1. Persist inbound Telegram message
        2. Create WorkflowRun and execute pipeline
        3. Format and send reply
        4. Persist outbound reply
        """
        loop = asyncio.get_event_loop()

        result: dict = await loop.run_in_executor(
            None,
            self._execute_workflow_sync,
            user_message,
            from_user,
            chat_id,
        )

        if result["ok"]:
            reply = _build_reply(result["output"], result["run_id"])
        else:
            reply = (
                "❌ <b>Investigation failed</b>\n\n"
                f"{result.get('error', 'Unknown error')}\n\n"
                "Please try again or check the AgentOps UI."
            )

        await self._send(chat_id, reply)

        # Persist outbound reply with the run's ID
        run_id = result.get("run_id")
        if run_id:
            await loop.run_in_executor(
                None, self._persist_outbound, run_id, reply
            )

    def _execute_workflow_sync(
        self,
        user_message: str,
        from_user: str,
        chat_id: int,
    ) -> dict:
        """
        Blocking workflow execution — runs in a ThreadPoolExecutor so it
        doesn't block the asyncio event loop.

        Creates its own DB session to stay thread-safe.
        """
        # Local imports to avoid circular imports at module level
        from app.models.workflow import Workflow
        from app.models.workflow_run import WorkflowRun
        from app.runtime.agent_runtime import AgentRuntime
        from app.runtime.memory import persist_message

        db = self._session_factory()
        try:
            # ── 1. Locate the workflow ────────────────────────────────────────
            wf = (
                db.query(Workflow)
                .filter(Workflow.template_type == "payment_failure_investigation")
                .order_by(Workflow.id)
                .first()
            )
            if wf is None:
                return {"ok": False, "error": "No payment_failure_investigation workflow in DB. Run the demo from the UI first."}

            # ── 2. Create the run record (before persisting inbound message) ──
            run = WorkflowRun(
                workflow_id=wf.id,
                status="pending",
                input_payload={
                    "message":   user_message,
                    "channel":   "telegram",
                    "from_user": from_user,
                    "chat_id":   chat_id,
                },
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            # ── 3. Persist inbound Telegram message ───────────────────────────
            persist_message(
                db,
                run_id=run.id,
                sender_agent=None,                    # human sender
                receiver_agent="Support Intake Agent",
                content=f"[Telegram @{from_user}] {user_message}",
                message_type="text",
                channel="telegram",
            )

            # ── 4. Execute the workflow ───────────────────────────────────────
            logger.info(
                "[Telegram] Executing workflow '%s' (run_id=%d) for @%s",
                wf.name,
                run.id,
                from_user,
            )
            output = AgentRuntime(db).execute(run, {"message": user_message})
            self.total_runs += 1

            # Extract ticket ID from tool_result logs (not persisted in output_payload)
            from app.models.runtime_log import RuntimeLog
            ticket_id: str | None = None
            tool_logs = (
                db.query(RuntimeLog)
                .filter(
                    RuntimeLog.run_id == run.id,
                    RuntimeLog.event_type == "tool_result",
                )
                .all()
            )
            for tl in tool_logs:
                meta = tl.log_metadata or {}
                result_data = meta.get("result", {})
                if isinstance(result_data, dict) and "ticket_id" in result_data:
                    ticket_id = result_data["ticket_id"]
                    break
                # Fallback: regex over raw JSON
                raw = json.dumps(meta)
                m = _TKT_RE.search(raw)
                if m:
                    ticket_id = m.group()
                    break

            if ticket_id:
                output.setdefault("extracted_data", {})["ticket_id"] = ticket_id

            return {"ok": True, "output": output, "run_id": run.id}

        except Exception as exc:
            import traceback as tb
            logger.exception("[Telegram] Workflow sync execution failed: %s", exc)
            return {
                "ok":         False,
                "error":      str(exc),
                "traceback":  tb.format_exc()[:1000],
            }
        finally:
            db.close()

    def _persist_outbound(self, run_id: int, reply: str) -> None:
        """Persist the outbound Telegram reply; runs in thread pool."""
        from app.runtime.memory import persist_message

        db = self._session_factory()
        try:
            persist_message(
                db,
                run_id=run_id,
                sender_agent="Resolution Agent",
                receiver_agent=None,
                content=reply,
                message_type="text",
                channel="telegram",
            )
        finally:
            db.close()

    # ── Telegram API helpers ──────────────────────────────────────────────────

    async def _api(
        self,
        method: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        timeout: float = 10.0,
    ) -> dict:
        url = f"{self._base}/{method}"
        async with httpx.AsyncClient(timeout=timeout, verify=self._ssl_verify) as client:
            if json is not None:
                resp = await client.post(url, json=json)
            else:
                resp = await client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()

    async def _send(self, chat_id: int, text: str) -> None:
        """Send an HTML-formatted message to a Telegram chat."""
        try:
            await self._api(
                "sendMessage",
                json={
                    "chat_id":    chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                },
            )
        except Exception as exc:
            logger.warning("[Telegram] sendMessage to %s failed: %s", chat_id, exc)


# ── Response formatter ────────────────────────────────────────────────────────

def _build_reply(output: dict, run_id: int) -> str:
    """
    Turn workflow output into a structured, human-readable Telegram message.

    Extracts: payment_id, root_cause, failure_owner, fraud_detected,
    confidence_score, and ticket_id (from agent output text).
    """
    extracted     = output.get("extracted_data", {})
    agent_outputs = output.get("agent_outputs", {})
    cost          = output.get("cost_summary",  {})

    payment_id  = extracted.get("payment_id",       "unknown")
    root_cause  = extracted.get("root_cause",        "unknown")
    fraud       = bool(extracted.get("fraud_detected", False))
    confidence  = extracted.get("confidence_score")
    issue_type  = extracted.get("issue_type",        "payment_failure")
    failure_owner = extracted.get("failure_owner",   "")

    # ── Risk level ────────────────────────────────────────────────────────────
    if fraud:
        risk_emoji = "🔴"
        risk_label = "HIGH — Fraud signals detected"
    elif root_cause in ("CARD_DECLINED", "insufficient_funds", "expired_card"):
        risk_emoji = "🟡"
        risk_label = "LOW — Issuing bank issue (no fraud)"
    else:
        risk_emoji = "🟠"
        risk_label = "MEDIUM — Requires review"

    # ── Recommended action ────────────────────────────────────────────────────
    if fraud:
        action = "Transaction frozen. Escalated to Risk & Compliance."
    elif root_cause == "CARD_DECLINED":
        action = "Advise customer to retry with a different card or contact their issuing bank."
    elif root_cause == "insufficient_funds":
        action = "Advise customer to top up their account and retry."
    elif root_cause == "expired_card":
        action = "Advise customer to update their card details and retry."
    elif root_cause == "network_timeout":
        action = "Automatic retry scheduled. Monitor for resolution."
    else:
        action = "Manual review recommended. Contact the acquiring bank."

    # ── Ticket ID ─────────────────────────────────────────────────────────────
    # Injected by _execute_workflow_sync from tool_result logs, or found in
    # agent message text.
    ticket_id: str | None = extracted.get("ticket_id")  # type: ignore[assignment]
    if not ticket_id:
        all_agent_text = " ".join(str(v) for v in agent_outputs.values())
        tkt_m = _TKT_RE.search(all_agent_text) or _TKT_RE.search(str(output))
        ticket_id = tkt_m.group() if tkt_m else None

    # ── Token stats ───────────────────────────────────────────────────────────
    total_tok = cost.get("total_tokens", 0)

    # ── Assemble message ──────────────────────────────────────────────────────
    lines = [
        "✅ <b>Payment Investigation Complete</b>",
        "",
        f"💳 <b>Payment ID:</b>  <code>{payment_id}</code>",
        f"🚫 <b>Failure:</b>  {root_cause.replace('_', ' ').title()}",
    ]

    if failure_owner:
        lines.append(f"🏦 <b>Failure Owner:</b>  {failure_owner.replace('_', ' ').title()}")

    lines += [
        f"{risk_emoji} <b>Risk Level:</b>  {risk_label}",
        f"🎯 <b>Recommended Action:</b>  {action}",
    ]

    if ticket_id:
        lines.append(f"🎫 <b>Support Ticket:</b>  <code>{ticket_id}</code>")

    if confidence is not None:
        lines.append(f"📊 <b>Confidence:</b>  {int(float(confidence) * 100)}%")

    lines += [
        "",
        f"🔗 <b>Run ID:</b>  <code>#{run_id}</code> — view full details in the AgentOps UI",
    ]

    if total_tok:
        lines.append(f"⚡ <i>{total_tok:,} tokens consumed</i>")

    return "\n".join(lines)
