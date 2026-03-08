"""
plaid.py — Plaid API integration routes.

WHY PLAID:
Plaid gives us real-time access to bank accounts, credit cards, and
transaction data without the user having to manually enter expenses.
When a Starbucks charge posts → glasses whisper the weekly coffee total.
When you walk into Whole Foods → glasses have your grocery budget ready.

WEBHOOK FLOW:
  Plaid detects transaction → POST /api/v1/plaid/webhook
    → update transactions table
    → recalculate budget snapshots
    → if budget threshold crossed → push alert to glasses session

SANDBOX TESTING:
  Use Plaid Sandbox credentials. Trigger test transactions via:
  POST https://sandbox.plaid.com/sandbox/item/fire_webhook
"""

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import hmac
import hashlib

from app.services.plaid_service import PlaidService
from app.services.budget_engine import BudgetEngine
from app.services.alert_engine import AlertEngine
from app.services.tts_service import FinanceTTSService
from app.api.v1.glasses import broadcast_transaction_alert
from app.config import settings
from services.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/plaid", tags=["Plaid"])

_plaid: Optional[PlaidService] = None
_budget: Optional[BudgetEngine] = None
_alerts: Optional[AlertEngine] = None
_tts: Optional[FinanceTTSService] = None


def get_plaid():
    global _plaid
    if _plaid is None:
        _plaid = PlaidService()
    return _plaid


def get_budget():
    global _budget
    if _budget is None:
        _budget = BudgetEngine()
    return _budget


def get_alerts():
    global _alerts
    if _alerts is None:
        _alerts = AlertEngine()
    return _alerts


def get_tts():
    global _tts
    if _tts is None:
        _tts = FinanceTTSService()
    return _tts


# =============================================================================
# SCHEMAS
# =============================================================================

class PlaidLinkRequest(BaseModel):
    public_token: str
    institution_name: Optional[str] = None


class PlaidLinkResponse(BaseModel):
    access_token: str
    item_id: str
    accounts: List[dict]
    institution_name: Optional[str]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/link", response_model=PlaidLinkResponse)
async def link_plaid_account(request: PlaidLinkRequest):
    """
    Exchange Plaid public token for access token.
    Called from companion app after user completes Plaid Link flow.
    Stores access token securely (encrypted in DB).
    """
    plaid = get_plaid()
    result = await plaid.exchange_public_token(request.public_token)

    return PlaidLinkResponse(
        access_token=result["access_token"],
        item_id=result["item_id"],
        accounts=result.get("accounts", []),
        institution_name=request.institution_name,
    )


@router.post("/webhook")
async def plaid_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Plaid webhook receiver. Handles real-time transaction notifications.

    Plaid sends a webhook when:
    - TRANSACTIONS_SYNC: new transactions available
    - PENDING_EXPIRATION: item access token expires soon
    - ERROR: item requires re-authentication

    We process transaction syncs in the background to avoid blocking the
    200 OK response Plaid expects within 5 seconds.
    """
    body = await request.body()

    # TODO: verify Plaid webhook signature in production
    # plaid_signature = request.headers.get("Plaid-Verification")
    # _verify_webhook_signature(body, plaid_signature, settings.plaid_webhook_secret)

    payload = await request.json()
    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")
    item_id = payload.get("item_id")

    logger.info("plaid_webhook_received", type=webhook_type, code=webhook_code, item_id=item_id)

    if webhook_type == "TRANSACTIONS" and webhook_code in ("TRANSACTIONS_SYNC", "DEFAULT_UPDATE"):
        background_tasks.add_task(_process_transaction_sync, item_id, payload)
    elif webhook_type == "ITEM" and webhook_code == "PENDING_EXPIRATION":
        logger.warning("plaid_item_expiring", item_id=item_id)
    elif webhook_type == "ITEM" and webhook_code == "ERROR":
        logger.error("plaid_item_error", item_id=item_id, error=payload.get("error"))

    return {"status": "received"}


async def _process_transaction_sync(item_id: str, payload: dict):
    """
    Background task: sync new Plaid transactions and push glasses alerts.

    Flow:
    1. Fetch new transactions from Plaid
    2. Categorize each transaction against budget categories
    3. Update budget_snapshots
    4. If any category crossed alert threshold → push glasses alert
    """
    plaid = get_plaid()
    budget = get_budget()
    alerts = get_alerts()
    tts = get_tts()

    try:
        # Sync transactions
        new_transactions = await plaid.sync_transactions(item_id)
        logger.info("transactions_synced", count=len(new_transactions), item_id=item_id)

        for txn in new_transactions:
            # Categorize
            category_id = await budget.categorize_transaction(txn)

            # Update snapshot
            await budget.record_transaction(txn, category_id)

            # Check if alert threshold crossed
            alert = await alerts.check_transaction_threshold(txn, category_id)
            if alert:
                audio = await tts.synthesize(alert["tts_script"], urgency="medium")
                alert_with_audio = {**alert, "tts_audio_base64": audio}

                # Push to all active glasses sessions for this user
                # TODO: look up active sessions for txn.user_id from DB
                # For now: broadcast to all sessions (MVP)
                for session_id in list(_get_active_sessions()):
                    await broadcast_transaction_alert(session_id, alert_with_audio)

    except Exception as e:
        logger.error("transaction_sync_failed", item_id=item_id, error=str(e))


def _get_active_sessions() -> list:
    """Get active session IDs (imported to avoid circular import)."""
    from app.api.v1.glasses import _sessions
    return list(_sessions.keys())
