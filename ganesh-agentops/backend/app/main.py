import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.seed.seed_data import seed_agents, seed_workflows, seed_sample_runs
from app.api.agents import router as agents_router
from app.api.workflows import router as workflows_router
from app.api.templates import router as templates_router
from app.api.runs import router as runs_router
from app.api.messages import router as messages_router
from app.api.telegram import router as telegram_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    init_db()
    seed_agents()
    seed_workflows()
    seed_sample_runs()   # 3 historical demo runs; no-op after first startup

    # ── Telegram integration (optional) ───────────────────────────────────────
    telegram_bot = None
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            from app.integrations.telegram_bot import TelegramBot
            from app.database import SessionLocal

            telegram_bot = TelegramBot(
                token=settings.TELEGRAM_BOT_TOKEN,
                session_factory=SessionLocal,
                chat_id=settings.TELEGRAM_CHAT_ID,
                ssl_verify=not settings.TELEGRAM_SKIP_SSL_VERIFY,
            )
            app.state.telegram_bot = telegram_bot
            await telegram_bot.start()

            if telegram_bot.connected:
                logger.info(
                    "[Telegram] Bot @%s is live and polling",
                    telegram_bot.bot_username,
                )
            else:
                logger.warning(
                    "[Telegram] Token present but bot failed to connect — "
                    "check TELEGRAM_BOT_TOKEN in .env"
                )
        except Exception as exc:
            logger.warning("[Telegram] Startup failed (non-fatal): %s", exc)
            app.state.telegram_bot = None
    else:
        app.state.telegram_bot = None
        logger.info(
            "[Telegram] Integration disabled — set TELEGRAM_BOT_TOKEN in .env to enable"
        )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if telegram_bot is not None:
        await telegram_bot.stop()


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI Agent Orchestration Platform — Ganesh AgentOps\n\n"
        "**Telegram integration:** set `TELEGRAM_BOT_TOKEN` in `.env` to enable the bot."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(templates_router)
app.include_router(runs_router)
app.include_router(messages_router)
app.include_router(telegram_router)


# ── System endpoints ──────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    """Service health + Telegram status summary."""
    bot = getattr(app.state, "telegram_bot", None)
    telegram_info: dict = (
        {"enabled": True, "connected": bot.connected, "username": bot.bot_username}
        if bot is not None
        else {"enabled": False, "connected": False, "username": None}
    )
    return {
        "status":   "ok",
        "service":  "ganesh-agentops-backend",
        "version":  "0.1.0",
        "telegram": telegram_info,
    }
