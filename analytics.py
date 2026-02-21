from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
import models
from database import get_db
from auth import get_current_user
import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY", "fallback_key"))

router = APIRouter(prefix="/analytics", tags=["analytics"])

class CategorySummary(BaseModel):
    category: str
    total_amount: float

class DashboardResponse(BaseModel):
    total_spent: float
    total_received: float
    category_breakdown: List[CategorySummary]

class Insight(BaseModel):
    type: str # e.g., "high_frequency", "duplicate_subscription"
    description: str
    amount_impact: float

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str

@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    # Calculate Total Spent
    total_spent = db.query(func.sum(models.Transaction.amount))\
        .filter(models.Transaction.txn_type == "DEBIT")\
        .scalar() or 0.0
        
    # Calculate Total Received
    total_received = db.query(func.sum(models.Transaction.amount))\
        .filter(models.Transaction.txn_type == "CREDIT")\
        .scalar() or 0.0

    # Category Breakdown
    breakdown_query = db.query(
        models.Transaction.category, 
        func.sum(models.Transaction.amount).label("total")
    ).filter(
        models.Transaction.txn_type == "DEBIT",
        models.Transaction.category.isnot(None)
    ).group_by(models.Transaction.category).all()
    
    category_list = [CategorySummary(category=row[0], total_amount=row[1]) for row in breakdown_query]

    return DashboardResponse(
        total_spent=total_spent,
        total_received=total_received,
        category_breakdown=category_list
    )

@router.get("/insights", response_model=List[Insight])
def get_insights(db: Session = Depends(get_db)):
    insights = []
    
    # Rule 1: High Frequency Small Spends (e.g. daily coffee)
    # Group by merchant, count > 10, avg amount < 500
    freq_query = db.query(
        models.Transaction.merchant,
        func.count(models.Transaction.id).label("count"),
        func.sum(models.Transaction.amount).label("total")
    ).filter(
        models.Transaction.txn_type == "DEBIT"
    ).group_by(models.Transaction.merchant)\
     .having(func.count(models.Transaction.id) > 5).all()
     
    for row in freq_query:
        if row[2] / row[1] < 500: # avg amount
            insights.append(Insight(
                type="high_frequency",
                description=f"You frequently spend at {row[0]} ({row[1]} times). Consider cutting back to save.",
                amount_impact=row[2]
            ))
            
    # Rule 2: Duplicate Subscriptions
    # Simplified logic: multiple DEBIT transactions same amount, same merchant in different months
    # (Since we have limited datetime logic in this MVP, we mock the logic here)
    # A proper app would use Pandas or complex SQL analytical windows.
    
    return insights

@router.post("/chat", response_model=ChatResponse)
def chat_with_data(request: ChatRequest, db: Session = Depends(get_db)):
    # Fetch recent transactions to build context
    recent_txns = db.query(models.Transaction)\
        .order_by(models.Transaction.id.desc())\
        .limit(50).all()
        
    context = "Here are my recent transactions:\\n"
    for t in recent_txns:
        context += f"Merchant: {t.merchant}, Amount: {t.amount}, Type: {t.txn_type}\\n"
        
    prompt = f"{context}\\n\\nUser question: {request.query}\\nAnswer concisely based ONLY on the data provided."
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
        )
        return ChatResponse(answer=chat_completion.choices[0].message.content.strip())
    except Exception as e:
        return ChatResponse(answer="Sorry, I couldn't process your request right now.")
