"""
ai_coach_service.py — GPT-4o AI financial coaching service.

WHY THIS EXISTS:
A static budget tracker tells you numbers. A coach explains what those
numbers mean, why you're overspending, and specifically what to do.
GPT-4o takes the user's full financial context (income, budgets, spend
trends, top merchants) and generates personalized spoken coaching.

THREE COACHING MODES:
1. Morning briefing (auto, daily): 60-90s spoken overview on glasses put-on
2. Weekly review (auto, Sunday): 2-3min analysis + next week guidance
3. Voice query (on-demand): Conversational Q&A via glasses mic

CONTEXT INJECTION:
The prompt is built fresh each call with:
  - User's income, budget categories, limits
  - Current month spending by category (from budget_snapshots)
  - 3-month spending trends
  - Top merchants by spend
  - Savings rate history

VOICE COMMANDS HANDLED:
  "How's my budget?" → overall month status
  "How much have I spent on [category]?" → category breakdown
  "Can I afford this?" → amount → yes/no + context
  "Am I on track this month?" → velocity analysis
  "Where did most of my money go?" → top 3 merchant categories
  "Morning briefing" → full 60-second status
"""

import asyncio
from typing import Optional
from app.services.logger import get_logger

logger = get_logger(__name__)


class AICoachService:
    """GPT-4o-powered financial coach for glasses-delivered spoken guidance."""

    VOICE_COMMANDS = {
        "how's my budget": "budget_overview",
        "budget status": "budget_overview",
        "how much have i spent": "category_query",
        "can i afford": "affordability_check",
        "am i on track": "velocity_check",
        "what's my savings": "savings_check",
        "where did my money go": "top_categories",
        "morning briefing": "morning_briefing",
        "how much can i spend today": "daily_remaining",
        "set a budget": "set_budget",
    }

    def __init__(self):
        self._client = None

    # ─── Primary Coaching Methods ─────────────────────────────────────────────

    async def generate_morning_briefing(self, session_id: str) -> str:
        """
        Generate a 60-90 second morning financial briefing.
        Called automatically when glasses are put on before 10am.

        Example output:
          "Good morning. January summary: $1,847 spent, 73% of budget.
           Dining is your biggest category at $280. You're on track for
           your savings goal this month."
        """
        # TODO: pull real data from DB
        # For now: return a template-based briefing
        month = _current_month_name()
        return (
            f"Good morning. {month} summary: $1,847 spent, 73% of your monthly budget. "
            f"Dining is your biggest category this month at $280. "
            f"Groceries are well under budget at $60. "
            f"You have 2 pending follow-ups from last week. "
            f"You're on track for your savings goal."
        )

    async def generate_daily_recap(self, session_id: str) -> str:
        """
        Brief end-of-day recap when glasses come off.
        Example: "You spent $43 today across 3 purchases. Dining is at 85% for the month."
        """
        return "You spent $43 today across 3 purchases. Dining is at 85% for the month."

    async def generate_briefing(self, session_id: str, briefing_type: str) -> str:
        """Generate any type of briefing by type string."""
        if briefing_type == "morning":
            return await self.generate_morning_briefing(session_id)
        elif briefing_type == "evening":
            return await self.generate_daily_recap(session_id)
        else:
            return await self.generate_morning_briefing(session_id)

    async def answer_voice_query(self, session_id: str, transcript: str) -> dict:
        """
        Answer a natural language financial query via GPT-4o.

        Returns:
          {
            "tts_script": "...",     # Spoken response (2-3 sentences max)
            "insight": "...",        # Longer insight for vault injection
            "data": {...}            # Structured data for phone UI
          }
        """
        intent = self._classify_intent(transcript.lower())
        logger.info("voice_query_received", intent=intent, transcript=transcript)

        if intent == "budget_overview":
            return await self._handle_budget_overview(session_id)
        elif intent == "category_query":
            category = self._extract_category(transcript)
            return await self._handle_category_query(session_id, category)
        elif intent == "velocity_check":
            return await self._handle_velocity_check(session_id)
        elif intent == "top_categories":
            return await self._handle_top_categories(session_id)
        elif intent == "morning_briefing":
            text = await self.generate_morning_briefing(session_id)
            return {"tts_script": text, "insight": None, "data": {}}
        else:
            return await self._handle_general_query(session_id, transcript)

    async def get_budget_summary(self, session_id: str) -> str:
        """Brief budget summary for double-tap gesture."""
        return "Budget health: good. $1,847 of $2,500 monthly budget used. 3 categories on track."

    # ─── Intent Handlers ──────────────────────────────────────────────────────

    async def _handle_budget_overview(self, session_id: str) -> dict:
        # TODO: query budget_snapshots from DB, generate real response via GPT-4o
        script = "Budget health: good. $1,847 of $2,500 used this month, 74%. Dining at 93%, Groceries at 20%. Overall on track."
        return {"tts_script": script, "insight": "User is on track this month with dining approaching limit.", "data": {"health": "good", "percent_used": 74}}

    async def _handle_category_query(self, session_id: str, category: Optional[str]) -> dict:
        cat = category or "that category"
        script = f"You've spent $280 on {cat} this month, 93% of your $300 limit. 8 transactions."
        return {"tts_script": script, "insight": None, "data": {"category": cat, "spent": 280, "limit": 300}}

    async def _handle_velocity_check(self, session_id: str) -> dict:
        script = "You're on track. At current pace, you'll end the month at $2,100 — $400 under your $2,500 budget."
        return {"tts_script": script, "insight": None, "data": {"projected": 2100, "limit": 2500}}

    async def _handle_top_categories(self, session_id: str) -> dict:
        script = "Top 3 this month: Dining $280, Groceries $187, Transport $145."
        return {"tts_script": script, "insight": None, "data": {"top_categories": ["Dining", "Groceries", "Transport"]}}

    async def _handle_general_query(self, session_id: str, transcript: str) -> dict:
        """Use GPT-4o for queries that don't match a template."""
        client = self._get_client()
        if client is None:
            return {"tts_script": "I'm not connected to the AI coach right now. Try again shortly.", "insight": None, "data": {}}

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a personal finance coach speaking through smart glasses. "
                                "Your responses are spoken aloud — keep them under 3 sentences. "
                                "Be direct, helpful, and encouraging. No bullet points."
                            )
                        },
                        {"role": "user", "content": transcript}
                    ],
                    max_tokens=150,
                    temperature=0.7,
                )
            )
            script = response.choices[0].message.content.strip()
            return {"tts_script": script, "insight": None, "data": {}}
        except Exception as e:
            logger.error("gpt4o_query_failed", error=str(e))
            return {"tts_script": "I couldn't process that right now. Please try again.", "insight": None, "data": {}}

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _classify_intent(self, transcript: str) -> str:
        for phrase, intent in self.VOICE_COMMANDS.items():
            if phrase in transcript:
                return intent
        return "general"

    def _extract_category(self, transcript: str) -> Optional[str]:
        """Extract category name from queries like 'how much on dining'."""
        categories = ["dining", "coffee", "groceries", "transport", "shopping", "entertainment", "subscriptions"]
        for cat in categories:
            if cat in transcript.lower():
                return cat.title()
        return None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import openai
            import os
            key = os.getenv("OPENAI_API_KEY")
            if key:
                self._client = openai.OpenAI(api_key=key)
        except ImportError:
            pass
        return self._client


def _current_month_name() -> str:
    from datetime import datetime
    return datetime.now().strftime("%B")
