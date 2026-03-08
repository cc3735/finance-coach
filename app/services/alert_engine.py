"""
alert_engine.py — Budget threshold and transaction alert generation.

WHY THIS EXISTS:
Budget limits are only useful if the user knows when they're approaching them.
This engine sits between Plaid transaction events and the glasses TTS pipeline.
When a transaction is recorded and causes a category to cross an alert threshold
(default: 80%), the engine generates a glasses-ready alert dict with TTS script.

ALERT TYPES:
  transaction_alert:  A specific charge just posted (Starbucks $6.85)
  budget_alert:       Category crossed alert_at_percent threshold
  over_budget:        Category has exceeded its monthly limit

DEDUPLICATION:
  Transaction alerts are deduped by transaction_id.
  Budget alerts have a cooldown: same category won't alert again for 1 hour.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone
from services.logger import get_logger

logger = get_logger(__name__)


class AlertEngine:
    """Generates glasses-ready alert dicts from Plaid transaction events."""

    DEFAULT_ALERT_THRESHOLD = 0.80   # Alert at 80% of monthly limit

    def __init__(self):
        self._budget_alert_cooldown: dict[str, datetime] = {}  # category → last_alerted
        self._alerted_transactions: set[str] = set()

    async def check_transaction_threshold(
        self, txn: dict, category_name: Optional[str]
    ) -> Optional[dict]:
        """
        Check if a transaction warrants a glasses alert.

        Returns alert dict or None if no alert needed.
        """
        txn_id = txn.get("transaction_id", "")
        if txn_id in self._alerted_transactions:
            return None
        self._alerted_transactions.add(txn_id)

        merchant = txn.get("merchant_name") or txn.get("name", "Unknown")
        amount = abs(float(txn.get("amount", 0)))

        if not category_name:
            return None

        # Generate transaction alert
        # TODO: pull real category totals from DB
        weekly_count = 4  # Placeholder
        weekly_total = 24.80
        monthly_spent = 280.00
        monthly_limit = 300.00
        monthly_remaining = monthly_limit - monthly_spent

        tts_script = (
            f"{merchant} charge of ${amount:.2f}. "
            f"That's your {_ordinal(weekly_count)} {category_name.lower()} this week, "
            f"${weekly_total:.2f} total."
        )

        alert = {
            "type": "transaction_alert",
            "merchant": merchant,
            "amount": amount,
            "category": category_name,
            "weekly_count": weekly_count,
            "weekly_total": weekly_total,
            "budget_status": {
                "spent": monthly_spent,
                "limit": monthly_limit,
                "remaining": monthly_remaining,
            },
            "tts_script": tts_script,
        }

        # Check if budget threshold crossed
        if monthly_limit > 0:
            percent = monthly_spent / monthly_limit
            if percent >= 1.0:
                alert["budget_alert"] = {
                    "type": "over_budget",
                    "tts_script": f"{category_name} is over your ${monthly_limit:.0f} budget.",
                }
            elif percent >= self.DEFAULT_ALERT_THRESHOLD:
                if not self._is_budget_on_cooldown(category_name):
                    alert["budget_alert"] = {
                        "type": "approaching_limit",
                        "tts_script": (
                            f"{category_name} at {percent*100:.0f}% of budget. "
                            f"${monthly_remaining:.0f} left."
                        ),
                    }
                    self._mark_budget_alerted(category_name)

        return alert

    def _is_budget_on_cooldown(self, category: str) -> bool:
        last = self._budget_alert_cooldown.get(category)
        if last is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return elapsed < 1.0  # 1-hour cooldown

    def _mark_budget_alerted(self, category: str) -> None:
        self._budget_alert_cooldown[category] = datetime.now(timezone.utc)


def _ordinal(n: int) -> str:
    """Convert integer to ordinal string: 1 → '1st', 4 → '4th'."""
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th")
    return f"{n}{suffix}"
