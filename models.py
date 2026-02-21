import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    transactions = relationship("Transaction", back_populates="owner")
    jobs = relationship("ProcessingJob", back_populates="owner")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    txn_date = Column(DateTime, nullable=False, index=True)
    description = Column(String, nullable=False)
    merchant = Column(String, index=True)
    amount = Column(Float, nullable=False)
    txn_type = Column(String, nullable=False) # DEBIT / CREDIT
    category = Column(String, index=True)
    upi_id = Column(String, index=True)
    is_recurring = Column(Boolean, default=False)
    
    owner = relationship("User", back_populates="transactions")

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="PENDING") # PENDING, PROCESSING, COMPLETED, FAILED
    progress = Column(Float, default=0.0)
    total_pages = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="jobs")
