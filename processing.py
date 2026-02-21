import os
import shutil
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
import models
import schemas
from auth import get_current_user
import uuid
import fitz
from pdf_parser import extract_text_from_page, parse_upi_transactions
from datetime import datetime

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def process_pdf_background(job_id: str, file_path: str):
    db: Session = SessionLocal()
    try:
        job = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id).first()
        if not job:
            return
            
        job.status = "PROCESSING"
        db.commit()
        
        # Open PDF
        doc = fitz.open(file_path)
        total_pages = len(doc)
        job.total_pages = total_pages
        db.commit()
        
        all_transactions = []
        CHUNK_SIZE = 50
        
        for i in range(0, total_pages, CHUNK_SIZE):
            chunk_text = ""
            end_page = min(i + CHUNK_SIZE, total_pages)
            
            for page_num in range(i, end_page):
                page = doc.load_page(page_num)
                chunk_text += extract_text_from_page(page) + "\n"
                
            # Parse the extracted chunk text
            parsed_txns = parse_upi_transactions(chunk_text)
            
            # Fetch categories from LLM
            from llm_categorizer import batched_categorization
            unique_merchants = list(set([txn["merchant"] for txn in parsed_txns if txn["merchant"]]))
            merchant_cat_map = {}
            if unique_merchants:
                try:
                    merchant_cat_map = batched_categorization(unique_merchants)
                except Exception as cat_error:
                    print(f"Categorization error: {cat_error}")
            
            # Save transactions to DB
            for txn_data in parsed_txns:
                # Basic string to date logic omitted for brevity in MVP
                new_txn = models.Transaction(
                    user_id="default_user",
                    txn_date=datetime.utcnow(), # Needs actual parsing in realistic app
                    description=txn_data["description"],
                    merchant=txn_data["merchant"],
                    amount=txn_data["amount"],
                    txn_type=txn_data["txn_type"],
                    category=merchant_cat_map.get(txn_data["merchant"], "Other"), # Assigned LLM Category
                    upi_id=txn_data["upi_id"]
                )
                db.add(new_txn)
            
            db.commit()
            
            # Update Progress
            job.progress = (end_page / total_pages) * 100
            db.commit()

        # Mark job as complete
        job.status = "COMPLETED"
        job.progress = 100.0
        db.commit()
        
        doc.close()
        
        # In a full flow, we would trigger `llm_categorizer.py` here for unknown merchants
        
    except Exception as e:
        job = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            db.commit()
    finally:
        db.close()

@router.post("/statement", response_model=schemas.ProcessingJobOut)
async def upload_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Create Job in DB
    job = models.ProcessingJob(user_id="default_user")
    db.add(job)
    db.commit()
    db.refresh(job)

    # Save file
    file_path = os.path.join(UPLOAD_DIR, f"{job.id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Kick off background task
    background_tasks.add_task(process_pdf_background, job.id, file_path)

    return job

@router.get("/status/{job_id}", response_model=schemas.ProcessingJobOut)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
