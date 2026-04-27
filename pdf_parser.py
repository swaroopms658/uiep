import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
from datetime import datetime

DATE_PATTERN = re.compile(r'^[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$')
TRANSACTION_BOUNDARY_PATTERN = re.compile(r'^[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$')
_ACCOUNT_REF = re.compile(r'\s+(Paid|Received|Debited|Credited)\s+(by|to).*$', re.IGNORECASE)


def parse_statement_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%b %d, %Y")
    except ValueError:
        return None


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
