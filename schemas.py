from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

# User
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: str

    class Config:
        from_attributes = True

# Token
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Transaction
class TransactionBase(BaseModel):
    txn_date: datetime
    description: str
    merchant: Optional[str] = None
    amount: float
    txn_type: str
    category: Optional[str] = None
    upi_id: Optional[str] = None
    is_recurring: bool = False

class TransactionOut(TransactionBase):
    id: str

    class Config:
        from_attributes = True

# Processing Job
class ProcessingJobOut(BaseModel):
    id: str
    status: str
    progress: float
    total_pages: float
    created_at: datetime

    class Config:
        from_attributes = True
