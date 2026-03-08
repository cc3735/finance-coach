"""transactions.py — Transaction history and search endpoints."""
from fastapi import APIRouter, Query
from typing import Optional, List
from datetime import date

router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])


@router.get("")
async def list_transactions(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """List transactions with optional filters."""
    # TODO: DB query with filters
    return {"transactions": [], "count": 0}
