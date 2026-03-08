"""coaching.py — AI coaching session history and weekly review endpoints."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/coaching", tags=["AI Coaching"])


@router.get("/sessions")
async def list_coaching_sessions(limit: int = 20):
    """List recent AI coaching sessions."""
    return {"sessions": [], "count": 0}


@router.get("/weekly-review")
async def get_weekly_review():
    """Get or trigger the Sunday weekly review coaching session."""
    return {"status": "not_generated", "message": "Weekly review generates automatically on Sundays."}
