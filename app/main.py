"""
main.py — Finance Coach FastAPI application.

WHY THIS EXISTS:
Most finance apps require you to open them. You already know you should
check your budget — the problem is the 200 moments per month when you're
*about to spend* and your brain never connects "this purchase" to your
budget state.

The glasses change the interface to ambient. Walking into a restaurant →
whisper "you've spent $280 on dining this month, $70 under budget — enjoy."
Buying your 4th coffee this week → whisper "this is your 4th Starbucks this
week, $18.50 total." No app to open. No friction.

ARCHITECTURE:
  Plaid webhooks → budget engine → alert queue → glasses TTS
  GPS geofences → location triggers → glasses TTS
  Voice queries → GPT-4o coach → glasses TTS
  Morning glasses put-on → daily briefing

DEPLOYED: finance.thoughtvault.ai → Azure VM → port 8003
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.api.v1 import glasses, plaid, budgets, transactions, coaching
from app.services.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("finance_coach_startup", host=f"{settings.host}:{settings.port}")
    yield
    logger.info("finance_coach_shutdown")


app = FastAPI(
    title="Finance Coach API",
    description="Glasses-first AI personal finance coaching via ambient TTS alerts.",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(glasses.router)        # /api/v1/glasses/*
app.include_router(plaid.router)          # /api/v1/plaid/*
app.include_router(budgets.router)        # /api/v1/budgets/*
app.include_router(transactions.router)   # /api/v1/transactions/*
app.include_router(coaching.router)       # /api/v1/coaching/*


@app.get("/health")
def health():
    return {"status": "ok", "service": "finance-coach"}
