import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
from datetime import datetime

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
        if re.match(r'^[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$', line):
            try:
                date_str = line
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
                while j < len(lines) and not lines[j].startswith("Transaction ID") and not lines[j].startswith("Bank Reference") and not lines[j].startswith("UTR No") and not re.match(r'^[A-Z][a-z]{2}\s\d{1,2},\s\d{4}$', lines[j]):
                    merchant_lines.append(lines[j])
                    j += 1
                
                merchant_tail = " ".join(merchant_lines).strip()
                
                if direction_str in ["Paid to", "Received from", "Sent to", "Added to"]:
                    merchant = merchant_tail
                    description = f"{direction_str} {merchant}"
                else:
                    description = direction_str + (" " + merchant_tail if merchant_tail else "")
                    merchant = description.replace("Paid to", "").replace("Received from", "").replace("Sent to", "").strip()
                
                if not merchant:
                    merchant = "Unknown"
                    
                transactions.append({
                    "txn_date": date_str,  # Needs actual conversion to datetime object later
                    "description": description[:255],
                    "merchant": merchant[:255],
                    "amount": amount,
                    "txn_type": txn_type,
                    "category": None,
                    "upi_id": None,
                    "is_recurring": False
                })
                i = j # Skip to the next transaction block or metadata
            except Exception as e:
                i += 1
        else:
            i += 1
            
    return transactions
