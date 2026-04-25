"""
Telebirr receipt auto-verifier.
Fetches the official telebirr transaction page and extracts:
  - Credited Party Name  (የገንዘብ ተቀባይ ስም/Credited Party name)
  - Invoice No.          (የክፍያ ቁጥር/Invoice No.)
  - Settled Amount       (የተከፈለው መጠን/Settled Amount)
Then validates:
  - Name must match ALLOWED_RECEIVER_NAME
  - Invoice must not already exist in DB
"""

import re
import urllib.request
import urllib.error
from decimal import Decimal, InvalidOperation
from typing import Optional

from asgiref.sync import sync_to_async

ALLOWED_RECEIVER_NAME = "Miki Tefer Hira"
TELEBIRR_DOMAIN = "transactioninfo.ethiotelecom.et"


def _extract_url(text: str) -> Optional[str]:
    """Pull the first telebirr URL from arbitrary text."""
    match = re.search(
        r"https?://[^\s\"'<>]*" + re.escape(TELEBIRR_DOMAIN) + r"[^\s\"'<>]*",
        text,
        re.IGNORECASE,
    )
    return match.group(0) if match else None


def _fetch_page(url: str) -> str:
    """Download the receipt page HTML."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        if hasattr(e, 'reason'):
            raise urllib.error.URLError(f"Network error: {e.reason}")
        raise
    except Exception as e:
        raise Exception(f"Failed to fetch receipt page: {str(e)}")


def _strip_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _extract_credited_name(html: str) -> Optional[str]:
    """
    Extract credited party name.
    The page has a row like:
      የገንዘብ ተቀባይ ስም/Credited Party name   |   Miki Tefer Hira
    """
    patterns = [
        # Table cell after the label cell containing "Credited Party name"
        r"Credited\s+Party\s+name[^<]*</td>\s*<td[^>]*>(.*?)</td>",
        # Amharic label variant
        r"የገንዘብ\s+ተቀባይ\s+ስም[^<]*</td>\s*<td[^>]*>(.*?)</td>",
        # Generic fallback: value after the label in same row
        r"Credited\s+Party\s*[Nn]ame.*?<td[^>]*>\s*([A-Za-z][A-Za-z\s]{2,40})\s*</td>",
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE | re.DOTALL)
        if m:
            val = _strip_tags(m.group(1))
            if val:
                return val
    return None


def _extract_invoice_no(html: str) -> Optional[str]:
    """
    Extract invoice number from the invoice details table.
    The receipt has a section header 'የክፍያ ዝርዝር/Invoice details'
    followed by a table with columns: Invoice No. | Payment date | Settled Amount
    The invoice value is alphanumeric like DDO76OOTOZ (mix of letters and digits).
    """
    # First isolate the invoice details section to avoid grabbing TIN No.
    section_match = re.search(
        r"Invoice\s+details(.*?)(?:Stamp\s+Duty|Total\s+Paid|Payment\s+Mode|$)",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    search_html = section_match.group(1) if section_match else html

    patterns = [
        # First <td> in a table row — must contain letters AND digits (not pure number like TIN)
        r"<td[^>]*>\s*([A-Z]{1,5}\d[A-Z0-9]{4,18})\s*</td>",
        r"<td[^>]*>\s*([A-Z0-9]{3,5}[0-9]{2,}[A-Z0-9]{2,})\s*</td>",
        # Explicit label match
        r"Invoice\s+No\.?\s*[^<]*</t[dh]>\s*(?:<[^>]+>)*\s*([A-Z0-9]{6,20})",
        r"የክፍያ\s+ቁጥር[^<]*</t[dh]>.*?<td[^>]*>\s*([A-Z0-9]{6,20})\s*</td>",
    ]
    for p in patterns:
        m = re.search(p, search_html, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).strip()
            # Must contain at least one letter to distinguish from pure numeric TIN
            if val and re.search(r"[A-Za-z]", val):
                return val
    return None


def _extract_amount(html: str) -> Optional[str]:
    """
    Extract settled amount (not total paid — the base amount before fees).
    Row: Invoice No. | Payment date | Settled Amount
    Value like: 50.00 Birr
    """
    patterns = [
        # Third <td> in the invoice row — after invoice no and date
        r"<td[^>]*>\s*[A-Z0-9]{6,20}\s*</td>\s*<td[^>]*>[^<]+</td>\s*<td[^>]*>\s*([\d,]+\.?\d*)\s*(?:Birr)?",
        # Settled Amount label then value
        r"Settled\s+Amount[^<]*</th>.*?<td[^>]*>\s*([\d,]+\.?\d*)\s*(?:Birr)?",
        r"የተከፈለው\s+መጠን[^<]*</th>.*?<td[^>]*>\s*([\d,]+\.?\d*)\s*(?:Birr)?",
        # Inline
        r"Settled\s+Amount[^:]*:?\s*([\d,]+\.?\d*)\s*Birr",
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE | re.DOTALL)
        if m:
            val = m.group(1).replace(",", "").strip()
            if val:
                return val
    return None


def _parse_amount(raw: str) -> Optional[Decimal]:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


@sync_to_async
def _invoice_exists(invoice_no: str) -> bool:
    from wallet.models import Deposit
    return Deposit.objects.filter(invoice_no=invoice_no).exists()


@sync_to_async
def _approve_deposit(transaction_id: int, amount: Decimal, invoice_no: str, extracted_text: str):
    """Approve the deposit: update transaction + wallet balance."""
    from wallet.models import Transaction, Deposit
    from django.utils import timezone

    transaction = Transaction.objects.select_related("user__wallet").get(id=transaction_id)
    deposit = transaction.deposit_detail

    deposit.invoice_no = invoice_no
    deposit.extracted_text = extracted_text
    deposit.save()

    transaction.amount = amount
    transaction.status = "approved"
    transaction.processed_at = timezone.now()
    transaction.save()

    wallet = transaction.user.wallet
    wallet.main_balance += amount
    wallet.save()

    return transaction


async def verify_receipt(text: str, transaction_id: int) -> dict:
    """
    Main entry point.
    Returns dict with keys:
      success (bool), message (str), amount (Decimal|None), invoice_no (str|None)
    """
    # 1. Extract URL
    url = _extract_url(text)
    if not url:
        return {"success": False, "message": "❌ No valid telebirr receipt URL found in your message."}

    # 2. Fetch page
    try:
        html = _fetch_page(url)
    except urllib.error.URLError as e:
        return {
            "success": False,
            "message": (
                f"❌ Network error accessing receipt page.\n"
                f"Error: {str(e.reason)}\n\n"
                f"Please check:\n"
                f"1. The receipt URL is correct\n"
                f"2. Your internet connection\n"
                f"3. Try again in a moment"
            ),
            "extracted_text": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "message": (
                f"❌ Could not verify receipt.\n"
                f"Error: {str(e)}\n\n"
                f"Please try again or contact support."
            ),
            "extracted_text": str(e)
        }

    # 3. Extract fields
    credited_name = _extract_credited_name(html)
    invoice_no = _extract_invoice_no(html)
    raw_amount = _extract_amount(html)

    extracted_text = f"Name: {credited_name} | Invoice: {invoice_no} | Amount: {raw_amount}"

    # 4. Validate name
    if not credited_name or ALLOWED_RECEIVER_NAME.lower() not in credited_name.lower():
        return {
            "success": False,
            "message": (
                f"❌ Receipt rejected.\n"
                f"Credited name found: <b>{credited_name or 'Not found'}</b>\n"
                f"Expected: <b>{ALLOWED_RECEIVER_NAME}</b>"
            ),
            "invoice_no": invoice_no,
            "extracted_text": extracted_text,
        }

    # 5. Validate invoice
    if not invoice_no:
        return {"success": False, "message": "❌ Could not extract invoice number from receipt."}

    if await _invoice_exists(invoice_no):
        return {
            "success": False,
            "message": f"❌ This receipt (Invoice #{invoice_no}) has already been used.",
            "invoice_no": invoice_no,
            "extracted_text": extracted_text,
        }

    # 6. Parse amount
    if not raw_amount:
        return {"success": False, "message": "❌ Could not extract amount from receipt."}

    amount = _parse_amount(raw_amount)
    if not amount or amount <= 0:
        return {"success": False, "message": f"❌ Invalid amount on receipt: {raw_amount}"}

    # 7. Approve
    await _approve_deposit(transaction_id, amount, invoice_no, extracted_text)

    return {
        "success": True,
        "message": (
            f"✅ <b>Deposit Approved!</b>\n\n"
            f"Amount: <b>{amount} Birr</b>\n"
            f"Invoice: #{invoice_no}\n"
            f"Credited to: {credited_name}"
        ),
        "amount": amount,
        "invoice_no": invoice_no,
        "extracted_text": extracted_text,
    }
