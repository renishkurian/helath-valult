"""
Expense Tracker PDF Statement Parsers

This package provides parsers for different bank statements:
- SBI Credit Card
- SBI Bank Statement (Savings/Current)
- HDFC Credit Card
- HDFC Bank Statement (TODO)
- Generic fallback parser

Usage:
    from parsers import parse_statement_file
    
    result = parse_statement_file(file_bytes, filename, password="secret")
    
    print(result["account_info"])
    print(result["transactions"])
    print(result["summary"])
"""

import io
import pdfplumber
from pypdf import PdfReader
from typing import Dict, List
from collections import defaultdict

from .base import Transaction, AccountInfo
from .sbi import SBICreditCardParser, SBIBankStatementParser
from .hdfc import HDFCCreditCardParser, HDFCBankStatementParser
from .generic import GenericParser

# List of all available parsers (order matters - more specific first)
ALL_PARSERS = [
    SBICreditCardParser(),
    SBIBankStatementParser(),
    HDFCCreditCardParser(),
    HDFCBankStatementParser(),
    GenericParser(),  # Fallback - always last
]

# ============================================================
# PDF UTILITIES
# ============================================================
def is_pdf_encrypted(b: bytes) -> bool:
    """Check if PDF is encrypted"""
    try:
        reader = PdfReader(io.BytesIO(b))
        return reader.is_encrypted
    except:
        return False

def test_pdf_password(b: bytes, password: str) -> bool:
    """Test if a password works for an encrypted PDF"""
    try:
        reader = PdfReader(io.BytesIO(b))
        if not reader.is_encrypted:
            return True
        return reader.decrypt(password)
    except:
        return False

def decrypt_pdf(b: bytes, password: str) -> bytes:
    """Decrypt PDF with password"""
    reader = PdfReader(io.BytesIO(b))
    if reader.is_encrypted:
        if not reader.decrypt(password):
            raise ValueError("Invalid PDF password")
    return b

def extract_text_from_pdf(b: bytes, password: str = None) -> str:
    """Extract all text from PDF"""
    text = []
    if is_pdf_encrypted(b):
        if not password:
            raise ValueError("PDF is password protected but no password provided")
        decrypt_pdf(b, password)
    
    with pdfplumber.open(io.BytesIO(b), password=password) as pdf:
        for p in pdf.pages:
            text.append(p.extract_text() or "")
    return "\n".join(text)

# ============================================================
# SUMMARY GENERATION
# ============================================================
def generate_summary(transactions: List[Transaction]) -> Dict:
    """Generate comprehensive summary with bank/account breakdown"""
    # Overall summary
    total_debit = sum(abs(t.amount) for t in transactions if t.type == "debit")
    total_credit = sum(t.amount for t in transactions if t.type == "credit")
    
    # Category breakdown
    category_summary = defaultdict(lambda: {"debit": 0, "credit": 0, "count": 0})
    for t in transactions:
        cat = t.category
        if t.type == "debit":
            category_summary[cat]["debit"] += abs(t.amount)
        else:
            category_summary[cat]["credit"] += t.amount
        category_summary[cat]["count"] += 1
    
    # Bank/Account breakdown
    account_summary = defaultdict(lambda: {"debit": 0, "credit": 0, "count": 0})
    for t in transactions:
        key = f"{t.bank_name}_{t.account_type}_{t.account_number[-4:]}"
        if t.type == "debit":
            account_summary[key]["debit"] += abs(t.amount)
        else:
            account_summary[key]["credit"] += t.amount
        account_summary[key]["count"] += 1
    
    # Dividend summary
    dividends = [t for t in transactions if t.category == "dividend"]
    dividend_total = sum(t.amount for t in dividends)
    
    return {
        "total_transactions": len(transactions),
        "total_debit": total_debit,
        "total_credit": total_credit,
        "net_flow": total_credit - total_debit,
        "category_summary": dict(category_summary),
        "account_summary": dict(account_summary),
        "dividend_summary": {
            "total": dividend_total,
            "count": len(dividends),
            "items": [t.to_dict() for t in dividends]
        }
    }

# ============================================================
# MAIN PARSER FUNCTION
# ============================================================
def parse_statement_file(file_bytes: bytes, filename: str, password: str = None) -> Dict:
    """
    Main parser function - automatically detects bank and uses appropriate parser
    
    Args:
        file_bytes: PDF file content as bytes
        filename: Name of the file (for logging/debugging)
        password: Optional PDF password
    
    Returns:
        dict with keys:
            - account_info: Bank name, account type, account number, etc.
            - transactions: List of parsed transactions
            - summary: Aggregated statistics and summaries
    
    Raises:
        ValueError: If PDF is encrypted and password is invalid/missing
    """
    # Extract text from PDF
    text = extract_text_from_pdf(file_bytes, password=password)
    
    # Find appropriate parser
    selected_parser = None
    for parser in ALL_PARSERS:
        if parser.can_parse(text):
            selected_parser = parser
            break
    
    if not selected_parser:
        # This should never happen since GenericParser always returns True
        selected_parser = GenericParser()
    
    # Parse transactions
    transactions = selected_parser.parse(file_bytes, text, password=password)
    
    # Get account info
    account_info = selected_parser.extract_account_info(text)
    
    # Generate summary
    summary = generate_summary(transactions)
    
    return {
        "account_info": {
            "bank_name": account_info.bank_name,
            "account_type": account_info.account_type,
            "account_number": account_info.account_number,
            "ifsc_code": account_info.ifsc_code,
            "account_holder": account_info.account_holder
        },
        "transactions": [t.to_dict() for t in transactions],
        "summary": summary,
        "parser_used": selected_parser.__class__.__name__  # For debugging
    }

# ============================================================
# EXPORTS
# ============================================================
__all__ = [
    'parse_statement_file',
    'is_pdf_encrypted',
    'test_pdf_password',
    'extract_text_from_pdf',
    'Transaction',
    'AccountInfo',
]

