import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
from datetime import datetime

DATE_PATTERN = re.compile(r'^[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$')
TRANSACTION_BOUNDARY_PATTERN = re.compile(r'^[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$')
TIME_PATTERN = re.compile(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?$')
_ACCOUNT_REF = re.compile(r'\s+(Paid|Received|Debited|Credited)\s+(by|to).*$', re.IGNORECASE)


def parse_statement_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%b %d, %Y")
    except ValueError:
        return None


def parse_statement_time(time_str: str) -> tuple[int, int, int] | None:
    """Parse '3:45 PM', '15:45', '03:45:22 AM' → (hour, minute, second). Returns None if malformed."""
    m = TIME_PATTERN.match(time_str.strip())
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    second = int(m.group(3) or 0)
    ampm = (m.group(4) or "").upper()
    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour, minute, second


def extract_reference_id(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith(("Transaction ID", "Bank Reference", "UTR No")):
            _, _, value = line.partition(":")
            reference = value.strip() or line.split()[-1].strip()
            return reference[:255] if reference else None
    return None

def extract_text_from_page(page: fitz.Page) -> str:
    """Extract text from a PDF page, falling back to OCR if needed."""
    text = page.get_text("text")
    
    # If very little text is found, it might be a scanned page
    if len(text.strip()) < 50:
        try:
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
            text = pytesseract.image_to_string(img)
        except Exception as e:
            # Silently fallback if Tesseract is not installed locally
            text = ""
            
    return text

def parse_upi_transactions(text: str) -> list:
    """
    State machine parser to find UPI transactions using multiline layout logic 
    (designed for standard structural exports like PhonePe).
    """
    transactions = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for the start of a transaction block: Date string like "Feb 21, 2026"
        if DATE_PATTERN.match(line):
            try:
                date_str = line
                txn_date = parse_statement_date(date_str)
                # Line i+1 typically holds the time (e.g. "3:45 PM"). Skip silently on miss → midnight.
                if txn_date is not None and i + 1 < len(lines):
                    time_parts = parse_statement_time(lines[i + 1])
                    if time_parts:
                        h, m, s = time_parts
                        txn_date = txn_date.replace(hour=h, minute=m, second=s)
                txn_type = lines[i+2].upper() # e.g. "DEBIT" or "CREDIT"
                
                if txn_type not in ["DEBIT", "CREDIT"]:
                    i += 1
                    continue
                    
                amount_str = lines[i+3]
                # Extract amount (remove ₹ and commas)
                amount_match = re.search(r'[\d.,]+', amount_str)
                amount = float(amount_match.group(0).replace(',', '')) if amount_match else 0.0
                
                direction_str = lines[i+4] # e.g. "Paid to" or "Received from"
                
                j = i + 5
                merchant_lines = []
                metadata_lines = []
                while (
                    j < len(lines)
                    and not TRANSACTION_BOUNDARY_PATTERN.match(lines[j])
                ):
                    line_j = lines[j]
                    if line_j.startswith(("Transaction ID", "Bank Reference", "UTR No")):
                        metadata_lines.append(line_j)
                        j += 1
                        continue
                    # Skip account-reference lines like "Paid by XX6239", "Credited to XX1234"
                    if re.match(r'^(Paid|Received|Debited|Credited)\s+(by|to)\s+XX\d+', line_j):
                        j += 1
                        continue
                    merchant_lines.append(line_j)
                    j += 1
                
                merchant_tail = " ".join(merchant_lines).strip()
                
                if direction_str in ["Paid to", "Received from", "Sent to", "Added to"]:
                    merchant = merchant_tail
                    description = f"{direction_str} {merchant}"
                else:
                    description = direction_str + (" " + merchant_tail if merchant_tail else "")
                    merchant = description.replace("Paid to", "").replace("Received from", "").replace("Sent to", "").strip()
                
                merchant = _ACCOUNT_REF.sub('', merchant).strip()
                if not merchant:
                    merchant = "Unknown"
                    
                transactions.append({
                    "txn_date": txn_date,
                    "description": description[:255],
                    "merchant": merchant[:255],
                    "amount": amount,
                    "txn_type": txn_type,
                    "category": None,
                    "upi_id": extract_reference_id(metadata_lines),
                    "is_recurring": False
                })
                i = j # Skip to the next transaction block or metadata
            except Exception as e:
                i += 1
        else:
            i += 1
            
    return transactions
