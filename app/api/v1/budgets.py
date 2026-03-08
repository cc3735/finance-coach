"""budgets.py — Budget category CRUD endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/api/v1/budgets", tags=["Budgets"])


class BudgetCategoryCreate(BaseModel):
    name: str
    monthly_limit: float
    alert_at_percent: int = 80
    icon: Optional[str] = None


class BudgetCategoryResponse(BaseModel):
    id: str
    name: str
    monthly_limit: float
    alert_at_percent: int
    icon: Optional[str]


@router.get("", response_model=List[BudgetCategoryResponse])
async def list_budgets():
    """List all budget categories for the authenticated user."""
    # TODO: DB query
    return []


@router.post("", response_model=BudgetCategoryResponse, status_code=201)
async def create_budget(body: BudgetCategoryCreate):
    """Create a new budget category."""
    import uuid
    return BudgetCategoryResponse(id=str(uuid.uuid4()), **body.dict())


@router.put("/{budget_id}", response_model=BudgetCategoryResponse)
async def update_budget(budget_id: str, body: BudgetCategoryCreate):
    """Update an existing budget category."""
    return BudgetCategoryResponse(id=budget_id, **body.dict())
