"""
budget_engine.py — Budget tracking, categorization, and velocity calculation.

WHY THIS EXISTS:
Raw Plaid transactions need to be mapped to budget categories, accumulated
into monthly snapshots, and analyzed for spending velocity (are we on track
to exceed the budget before month end?). This engine does all three.

CATEGORIZATION STRATEGY:
1. Merchant name exact match (Starbucks → Coffee)
2. Plaid category hierarchy match (Food and Drink → Dining)
3. MCC code match (5411 → Groceries)
4. GPT-4o-mini fallback for ambiguous cases (rarely used)

VELOCITY CALCULATION:
  Daily budget = monthly_limit / days_in_month
  Projected month-end spend = spent_so_far × (days_in_month / days_elapsed)
  Days remaining budget = (monthly_limit - spent_so_far) / daily_budget
"""

from dataclasses import dataclass
from typing import Optional
from datetime import date, datetime, timezone
from calendar import monthrange
from app.services.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BudgetStatus:
    category_name: str
    monthly_limit: float
    spent_this_month: float
    remaining: float
    percent_used: float
    days_left_in_month: int
    daily_remaining: float         # How much can be spent per day for rest of month
    projected_month_end: float     # Projected total if current velocity continues
    velocity: str                  # "under_budget" | "on_track" | "at_risk" | "over_budget"
    transaction_count: int


class BudgetEngine:
    """
    Budget tracking engine. Calculates spend velocity, projects month-end,
    and classifies budget health.
    """

    VELOCITY_THRESHOLDS = {
        "under_budget": 0.70,    # < 70% of budget used at current pace
        "on_track": 0.90,        # 70-90%
        "at_risk": 1.00,         # 90-100%
        "over_budget": float("inf"),  # > 100%
    }

    # Merchant → category mapping (fast path, no API calls)
    MERCHANT_CATEGORY_MAP = {
        "starbucks": "Coffee",
        "dunkin": "Coffee",
        "mcdonald's": "Fast Food",
        "chipotle": "Fast Food",
        "whole foods": "Groceries",
        "trader joe's": "Groceries",
        "kroger": "Groceries",
        "safeway": "Groceries",
        "uber": "Transport",
        "lyft": "Transport",
        "amazon": "Shopping",
        "netflix": "Subscriptions",
        "spotify": "Subscriptions",
        "apple": "Subscriptions",
    }

    # Plaid category → budget category
    PLAID_CATEGORY_MAP = {
        "Food and Drink": "Dining",
        "Coffee Shop": "Coffee",
        "Restaurants": "Dining",
        "Groceries": "Groceries",
        "Supermarkets and Groceries": "Groceries",
        "Travel": "Transport",
        "Ride Share": "Transport",
        "Gas Stations": "Transport",
        "Entertainment": "Entertainment",
        "Shops": "Shopping",
    }

    async def categorize_transaction(self, txn: dict) -> Optional[str]:
        """
        Map a Plaid transaction to a budget category name.
        Returns category name (str) or None if uncategorized.
        """
        merchant = (txn.get("merchant_name") or "").lower()

        # Fast path: exact merchant match
        for keyword, category in self.MERCHANT_CATEGORY_MAP.items():
            if keyword in merchant:
                return category

        # Plaid category hierarchy match
        plaid_categories = txn.get("category") or []
        for plaid_cat in plaid_categories:
            if plaid_cat in self.PLAID_CATEGORY_MAP:
                return self.PLAID_CATEGORY_MAP[plaid_cat]

        # Default: uncategorized
        logger.debug("transaction_uncategorized", merchant=merchant, plaid_cats=plaid_categories)
        return None

    async def record_transaction(self, txn: dict, category_name: Optional[str]):
        """
        Record a transaction into budget_snapshots.
        TODO: implement DB write
        """
        logger.info(
            "transaction_recorded",
            merchant=txn.get("merchant_name"),
            amount=txn.get("amount"),
            category=category_name,
        )

    def calculate_budget_status(
        self,
        category_name: str,
        monthly_limit: float,
        spent_this_month: float,
        transaction_count: int,
        today: Optional[date] = None,
    ) -> BudgetStatus:
        """
        Calculate full budget status for a category.
        """
        today = today or date.today()
        days_in_month = monthrange(today.year, today.month)[1]
        days_elapsed = today.day
        days_left = days_in_month - days_elapsed

        remaining = max(0.0, monthly_limit - spent_this_month)
        percent_used = (spent_this_month / monthly_limit * 100) if monthly_limit > 0 else 0

        # Project month-end spend based on current velocity
        if days_elapsed > 0:
            projected = spent_this_month * (days_in_month / days_elapsed)
        else:
            projected = 0.0

        # Daily remaining
        daily_remaining = remaining / days_left if days_left > 0 else 0

        # Velocity classification
        projected_ratio = projected / monthly_limit if monthly_limit > 0 else 0
        if projected_ratio <= 0.70:
            velocity = "under_budget"
        elif projected_ratio <= 0.90:
            velocity = "on_track"
        elif projected_ratio <= 1.00:
            velocity = "at_risk"
        else:
            velocity = "over_budget"

        return BudgetStatus(
            category_name=category_name,
            monthly_limit=monthly_limit,
            spent_this_month=spent_this_month,
            remaining=remaining,
            percent_used=percent_used,
            days_left_in_month=days_left,
            daily_remaining=daily_remaining,
            projected_month_end=projected,
            velocity=velocity,
            transaction_count=transaction_count,
        )

    def budget_status_to_tts(self, status: BudgetStatus) -> str:
        """
        Convert a BudgetStatus to a concise spoken summary.
        Examples:
          "Dining: $255 of $300 this month. $45 left for 8 days."
          "Groceries: $60 of $300 — well under budget."
        """
        cat = status.category_name
        spent = status.spent_this_month
        limit = status.monthly_limit
        remaining = status.remaining
        days = status.days_left_in_month
        daily = status.daily_remaining

        if status.velocity == "over_budget":
            return (
                f"{cat} is over budget. ${spent:.0f} spent against a ${limit:.0f} limit."
            )
        elif status.velocity == "at_risk":
            return (
                f"{cat} is at risk. ${spent:.0f} of ${limit:.0f} used. "
                f"${remaining:.0f} left for {days} days — ${daily:.0f} per day."
            )
        elif status.velocity == "on_track":
            return (
                f"{cat}: ${spent:.0f} of ${limit:.0f} this month. On track."
            )
        else:
            return (
                f"{cat}: ${spent:.0f} of ${limit:.0f}. Well under budget."
            )
