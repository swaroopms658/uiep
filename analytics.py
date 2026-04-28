import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from pydantic import BaseModel
import models
from database import get_db
from auth import get_current_user
from cache import cache_get, cache_set
from groq_client import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


class CategorySummary(BaseModel):
    category: str
    total_amount: float


class DashboardResponse(BaseModel):
    total_spent: float
    total_received: float
    category_breakdown: List[CategorySummary]


class Insight(BaseModel):
    type: str
    merchant: str
    category: Optional[str]
    count: int
    avg_amount: float
    amount_impact: float
    last_txn_at: Optional[datetime] = None


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    answer: str


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cache_key = f"dashboard:{current_user.id}"
    cached = cache_get(cache_key)
    if cached:
        return DashboardResponse(**cached)

    total_spent = (
        db.query(func.sum(models.Transaction.amount))
        .filter(
            models.Transaction.user_id == current_user.id,
            models.Transaction.txn_type == "DEBIT",
        )
        .scalar()
        or 0.0
    )

    total_received = (
        db.query(func.sum(models.Transaction.amount))
        .filter(
            models.Transaction.user_id == current_user.id,
            models.Transaction.txn_type == "CREDIT",
        )
        .scalar()
        or 0.0
    )

    breakdown_rows = (
        db.query(
            models.Transaction.category,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(
            models.Transaction.user_id == current_user.id,
            models.Transaction.txn_type == "DEBIT",
            models.Transaction.category.isnot(None),
        )
        .group_by(models.Transaction.category)
        .all()
    )

    category_list = [
        CategorySummary(category=row[0], total_amount=row[1])
        for row in breakdown_rows
    ]

    response = DashboardResponse(
        total_spent=total_spent,
        total_received=total_received,
        category_breakdown=category_list,
    )

    cache_set(cache_key, response.model_dump())
    return response


@router.get("/insights", response_model=List[Insight])
def get_insights(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cache_key = f"insights:{current_user.id}"
    cached = cache_get(cache_key)
    if cached:
        return [Insight(**i) for i in cached]

    insights: List[Insight] = []

    DISCRETIONARY = {"Entertainment", "Shopping", "Other"}
    ESSENTIAL = {"Food", "Health", "Bills"}

    # Aggregate ALL transactions per merchant (ignore category split — LLM categorization is inconsistent)
    freq_rows = (
        db.query(
            models.Transaction.merchant,
            func.count(models.Transaction.id).label("count"),
            func.sum(models.Transaction.amount).label("total"),
            # Use the most common category for this merchant
            func.max(models.Transaction.category).label("category"),
            func.max(models.Transaction.txn_date).label("last_txn_at"),
        )
        .filter(
            models.Transaction.user_id == current_user.id,
            models.Transaction.txn_type == "DEBIT",
        )
        .group_by(models.Transaction.merchant)
        .having(func.count(models.Transaction.id) > 5)
        .order_by(func.sum(models.Transaction.amount).desc())
        .all()
    )

    for row in freq_rows:
        merchant, count, total, category, last_txn_at = row
        avg_amount = total / count
        insight_type = "regular_expense" if category in ESSENTIAL else "high_frequency"
        insights.append(
            Insight(
                type=insight_type,
                merchant=merchant,
                category=category,
                count=int(count),
                avg_amount=round(avg_amount, 2),
                amount_impact=round(total, 2),
                last_txn_at=last_txn_at,
            )
        )

    cache_set(cache_key, [i.model_dump() for i in insights])
    return insights


@router.post("/chat", response_model=ChatResponse)
def chat_with_data(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Merchant summary — total paid/received per merchant across ALL transactions
    merchant_rows = (
        db.query(
            models.Transaction.merchant,
            models.Transaction.txn_type,
            func.count(models.Transaction.id).label("count"),
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(models.Transaction.user_id == current_user.id)
        .group_by(models.Transaction.merchant, models.Transaction.txn_type)
        .order_by(func.sum(models.Transaction.amount).desc())
        .all()
    )

    merchant_lines = []
    for row in merchant_rows:
        merchant_lines.append(
            f"{row.merchant} | {row.txn_type} | {row.count} txns | total Rs.{row.total:.2f}"
        )

    # 2. Category summary
    category_rows = (
        db.query(
            models.Transaction.category,
            models.Transaction.txn_type,
            func.sum(models.Transaction.amount).label("total"),
        )
        .filter(models.Transaction.user_id == current_user.id)
        .group_by(models.Transaction.category, models.Transaction.txn_type)
        .all()
    )
    category_lines = [
        f"{r.category} | {r.txn_type} | Rs.{r.total:.2f}" for r in category_rows
    ]

    # 3. Recent 100 individual transactions with dates for time-based questions
    recent_txns = (
        db.query(models.Transaction)
        .filter(models.Transaction.user_id == current_user.id)
        .order_by(models.Transaction.txn_date.desc())
        .limit(100)
        .all()
    )
    recent_lines = [
        f"{t.txn_date.strftime('%d %b %Y')} | {t.merchant} | {t.txn_type} | Rs.{t.amount:.2f}"
        for t in recent_txns
    ]

    context = (
        "=== MERCHANT SUMMARY (all time) ===\n"
        + "\n".join(merchant_lines)
        + "\n\n=== CATEGORY SUMMARY ===\n"
        + "\n".join(category_lines)
        + "\n\n=== RECENT 100 TRANSACTIONS ===\n"
        + "\n".join(recent_lines)
    )

    system_prompt = (
        "You are a financial assistant with access to the user's UPI transaction data. "
        "Answer ONLY using the data provided. "
        "If the answer is not in the data, say 'I don't see that in your transaction history.' "
        "Never guess or make up amounts. Be concise and specific with numbers."
    )

    try:
        answer = chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context}\n\nQuestion: {request.query}"},
        ])
        return ChatResponse(answer=answer.strip())
    except RuntimeError as exc:
        logger.warning("Groq rate limit: %s", exc)
        return ChatResponse(
            answer="All AI keys are currently rate-limited. Please wait a minute and try again."
        )
    except Exception as exc:
        logger.error("Groq API error (%s): %s", type(exc).__name__, exc, exc_info=True)
        return ChatResponse(
            answer="I couldn't process your request right now. Please try again later."
        )


@router.delete("/reset")
def reset_database(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete the current user's transactions (for testing)."""
    try:
        db.query(models.Transaction).filter(
            models.Transaction.user_id == current_user.id
        ).delete()
        db.commit()
        # Bust cached analytics for this user
        from cache import cache_delete
        cache_delete(f"dashboard:{current_user.id}")
        cache_delete(f"insights:{current_user.id}")
        return {"status": "success", "message": "Your transactions were deleted."}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
