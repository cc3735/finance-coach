"""
plaid_service.py — Plaid API client for Finance Coach.

WHY PLAID:
Plaid gives us real bank data without asking users to manually track expenses.
The user connects their bank once → we get real-time transaction webhooks,
account balances, and 24 months of transaction history for budget analysis.

SANDBOX TESTING:
  Set PLAID_ENV=sandbox and use Plaid's test credentials.
  Test institutions: use "user_good" / "pass_good" in Plaid Link.
  Trigger webhooks: POST to Plaid sandbox fire_webhook endpoint.

PRODUCTION:
  PLAID_ENV=production. Requires Plaid approval for production access.
  Access tokens are encrypted at rest (TODO: use AWS KMS or similar).
"""

import asyncio
from typing import Optional
from app.services.logger import get_logger

logger = get_logger(__name__)


class PlaidService:
    """Plaid API client: Link, transactions, balances."""

    def __init__(self):
        self._client = None

    async def exchange_public_token(self, public_token: str) -> dict:
        """
        Exchange Plaid public token (from Plaid Link) for an access token.
        Called once per connected institution.
        """
        client = self._get_client()
        if client is None:
            # Dev mode: return fake token
            return {"access_token": "access-sandbox-fake", "item_id": "item-fake", "accounts": []}

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.item_public_token_exchange({"public_token": public_token})
            )
            return {
                "access_token": response["access_token"],
                "item_id": response["item_id"],
                "accounts": [],
            }
        except Exception as e:
            logger.error("plaid_token_exchange_failed", error=str(e))
            raise

    async def sync_transactions(self, item_id: str) -> list[dict]:
        """
        Sync new transactions for an item.
        Uses Plaid's /transactions/sync endpoint (cursor-based, most efficient).
        TODO: implement cursor storage per item_id.
        """
        client = self._get_client()
        if client is None:
            # Return test transactions for dev
            return [
                {
                    "transaction_id": "txn-test-001",
                    "merchant_name": "Starbucks",
                    "amount": 6.85,
                    "category": ["Food and Drink", "Coffee Shop"],
                    "date": "2026-03-08",
                    "pending": False,
                    "account_id": "acc-test",
                }
            ]

        try:
            # TODO: implement /transactions/sync with cursor
            return []
        except Exception as e:
            logger.error("plaid_sync_failed", item_id=item_id, error=str(e))
            return []

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import plaid
            import os
            configuration = plaid.Configuration(
                host=plaid.Environment.Sandbox if os.getenv("PLAID_ENV", "sandbox") == "sandbox"
                    else plaid.Environment.Production,
                api_key={
                    "clientId": os.getenv("PLAID_CLIENT_ID", ""),
                    "secret": os.getenv("PLAID_SECRET", ""),
                }
            )
            api_client = plaid.ApiClient(configuration)
            from plaid.api import plaid_api
            self._client = plaid_api.PlaidApi(api_client)
        except ImportError:
            logger.warning("plaid_sdk_not_installed", fallback="dev_mode")
        return self._client
