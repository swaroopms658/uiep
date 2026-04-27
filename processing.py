import os
import shutil
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
import models
import schemas
from auth import get_current_user
import fitz
from pdf_parser import extract_text_from_page, parse_upi_transactions
from cache import cache_delete

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _transaction_exists(db: Session, user_id: str, txn: dict) -> bool:
    # Fast path: UPI reference ID is globally unique
    upi_id = txn.get("upi_id")
    if upi_id:
        if db.query(models.Transaction).filter(
            models.Transaction.user_id == user_id,
            models.Transaction.upi_id == upi_id,
        ).first():
            return True

    # Fallback: match on business key (no description — it can vary after cleanup)
    return (
        db.query(models.Transaction)
        .filter(
            models.Transaction.user_id == user_id,
            models.Transaction.txn_date == txn["txn_date"],
            models.Transaction.merchant == txn["merchant"],
            models.Transaction.amount == txn["amount"],
            models.Transaction.txn_type == txn["txn_type"],
        )
        .first()
        is not None
    )


def process_pdf_background(job_id: str, file_path: str):
    db: Session = SessionLocal()
    try:
        job = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id).first()
        if not job:
            return

        job.status = "PROCESSING"
        db.commit()

        doc = fitz.open(file_path)
        total_pages = len(doc)
        job.total_pages = total_pages
        db.commit()

        CHUNK_SIZE = 50

        for i in range(0, total_pages, CHUNK_SIZE):
            end_page = min(i + CHUNK_SIZE, total_pages)
            chunk_text = ""
            for page_num in range(i, end_page):
                chunk_text += extract_text_from_page(doc.load_page(page_num)) + "\n"

            parsed_txns = parse_upi_transactions(chunk_text)

            unique_merchants = list(
                {t["merchant"] for t in parsed_txns if t.get("merchant")}
            )
            merchant_cat_map: dict = {}
            if unique_merchants:
                try:
                    from llm_categorizer import batched_categorization
                    merchant_cat_map = batched_categorization(unique_merchants)
                except Exception as exc:
                    logger.warning("Categorization error (defaulting to Other): %s", exc)

            for txn_data in parsed_txns:
                txn_date = txn_data.get("txn_date") or datetime.utcnow()
                txn_payload = {
                    **txn_data,
                    "txn_date": txn_date,
                    "category": merchant_cat_map.get(txn_data.get("merchant", ""), "Other"),
                }
                if _transaction_exists(db, job.user_id, txn_payload):
                    continue

                db.add(
                    models.Transaction(
                        user_id=job.user_id,
                        txn_date=txn_date,
                        description=txn_data["description"],
                        merchant=txn_data["merchant"],
                        amount=txn_data["amount"],
                        txn_type=txn_data["txn_type"],
                        category=txn_payload["category"],
                        upi_id=txn_data["upi_id"],
                        is_recurring=txn_data.get("is_recurring", False),
                    )
                )

            db.commit()
            job.progress = (end_page / total_pages) * 100
            db.commit()

        job.status = "COMPLETED"
        job.progress = 100.0
        db.commit()
        doc.close()

        # Bust analytics cache so next dashboard reflects new data
        cache_delete(f"dashboard:{job.user_id}")
        cache_delete(f"insights:{job.user_id}")

    except Exception as exc:
        logger.exception("PDF processing failed for job %s", job_id)
        job = db.query(models.ProcessingJob).filter(models.ProcessingJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            db.commit()
    finally:
        db.close()
        try:
            os.remove(file_path)
        except OSError:
            pass


@router.post("/statement", response_model=schemas.ProcessingJobOut)
async def upload_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    job = models.ProcessingJob(user_id=current_user.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    file_path = os.path.join(UPLOAD_DIR, f"{job.id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(process_pdf_background, job.id, file_path)
    logger.info("Queued PDF job %s for user %s", job.id, current_user.id)
    return job


@router.get("/status/{job_id}", response_model=schemas.ProcessingJobOut)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    job = (
        db.query(models.ProcessingJob)
        .filter(
            models.ProcessingJob.id == job_id,
            models.ProcessingJob.user_id == current_user.id,
        )
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
