"""
Base classes and common utilities for all parsers
"""

import re
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional
from decimal import Decimal

# ============================================================
# DATA CLASSES
# ============================================================
@dataclass
class AccountInfo:
    bank_name: str
    account_type: str
    account_number: str
    ifsc_code: Optional[str] = None
    account_holder: Optional[str] = None

@dataclass
class Transaction:
    date: str
    description: str
    amount: float
    type: str  # debit or credit
    category: str
    bank_name: str
    account_type: str
    account_number: str
    transaction_id: str  # unique hash
    reference_number: Optional[str] = None
    
    def to_dict(self):
        return {
            "date": self.date,
            "description": self.description,
            "amount": self.amount,
            "type": self.type,
            "category": self.category,
            "bank_name": self.bank_name,
            "account_type": self.account_type,
            "account_number": self.account_number,
            "transaction_id": self.transaction_id,
            "reference_number": self.reference_number
        }

# ============================================================
# COMMON PATTERNS
# ============================================================
BANK_PATTERNS = {
    "SBI": {
        "keywords": ["STATE BANK OF INDIA", "SBIN", "MICR CODE", "SBI CARD", "SBI CARDS AND PAYMENT"],
        "ifsc_pattern": r"SBIN\d{7}",
        "account_pattern": r"\d{11}"
    },
    "HDFC": {
        "keywords": ["HDFC BANK CREDIT CARDS", "HDFC BANK", "HDFC", "MONEYBACK CREDIT CARD"],
        "ifsc_pattern": r"HDFC\d{7}",
        "account_pattern": r"\d{14}"
    },
    "ICICI": {
        "keywords": ["ICICI BANK", "ICIC"],
        "ifsc_pattern": r"ICIC\d{7}",
        "account_pattern": r"\d{12}"
    },
    "AXIS": {
        "keywords": ["AXIS BANK"],
        "ifsc_pattern": r"UTIB\d{7}",
        "account_pattern": r"\d{15}"
    }
}

ACCOUNT_TYPE_PATTERNS = {
    "savings": ["SAVINGS", "SB", "SAV"],
    "current": ["CURRENT", "CA", "CURR"],
    "credit_card": ["CREDIT CARD", "CC", "CARD ACCOUNT"],
    "debit_card": ["DEBIT CARD", "DC"]
}

CATEGORY_KEYWORDS = {
    "grocery": ["grocery", "dmart", "reliance", "big bazaar", "more", "spencer", "jiomart"],
    "fuel": ["petrol", "hpcl", "bpcl", "iocl", "shell", "fuel", "gas station"],
    "travel": ["uber", "ola", "rapido", "flight", "train", "irctc", "makemytrip", "goibibo", "redbus"],
    "food": ["restaurant", "cafe", "dominos", "zomato", "swiggy", "mcdonald", "kfc", "pizza", "burger"],
    "utilities": ["electricity", "water", "jio", "airtel", "vodafone", "bsnl", "broadband", "internet"],
    "investment": ["upstox", "zerodha", "groww", "mutual fund", "sip", "stock", "bsestarmfr", "indian clearin", "achdr", "yesb"],
    "dividend": ["dividend", "div", "achcr", "final div"],
    "salary": ["salary", "sal credit"],
    "transfer": ["transfer to", "transfer from", "neft", "rtgs", "imps"],
    "upi": ["upi/dr", "upi/cr", "upi", "upi payment", "upi transaction"],
    "cash_withdrawal": ["atm cash", "atm withdrawal", "cash fee"],
    "shopping": ["amazon", "flipkart", "myntra", "ajio"],
    "entertainment": ["bookmyshow", "netflix", "prime", "hotstar"],
    "emi": ["emi", "equated monthly installment", "loan emi", "offus emi", "fp emi", "interest on emi"]
}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def parse_amount(s: str) -> float:
    """Parse amount string to float"""
    s = s.replace(",", "").replace(" ", "")
    return float(Decimal(s))

def generate_transaction_id(date: str, amount: float, desc: str, account_num: str) -> str:
    """Generate unique transaction ID using hash"""
    unique_str = f"{date}_{amount}_{desc}_{account_num}"
    return hashlib.md5(unique_str.encode()).hexdigest()[:16]

def extract_reference_number(desc: str) -> Optional[str]:
    """Extract reference/transaction number from description"""
    ref_patterns = [
        r'\b\d{10,}\b',  # 10+ digit numbers
        r'REF[:\s]*([A-Z0-9]+)',
        r'TXN[:\s]*([A-Z0-9]+)'
    ]
    
    for pattern in ref_patterns:
        match = re.search(pattern, desc)
        if match:
            return match.group(1) if 'REF' in pattern or 'TXN' in pattern else match.group(0)
    return None

def categorize(desc: str) -> str:
    """Categorize transaction based on description"""
    d = desc.lower()
    
    # ACHCr transactions are ALWAYS dividends
    if "achcr" in d:
        return "dividend"
    
    # ACHDr transactions are ALWAYS investments (SIP, mutual funds, etc.)
    if "achdr" in d or "indian clearin" in d:
        return "investment"
    
    # EMI transactions should be checked before other categories
    if any(k in d for k in CATEGORY_KEYWORDS["emi"]):
        return "emi"
    
    # UPI transactions
    if any(k in d for k in CATEGORY_KEYWORDS["upi"]):
        return "upi"
    
    # Check all other categories
    for cat, keys in CATEGORY_KEYWORDS.items():
        if cat in ["emi", "upi"]:  # Skip as already checked
            continue
        if any(k in d for k in keys):
            return cat
    
    return "other"

# ============================================================
# BASE PARSER CLASS
# ============================================================
class BaseParser:
    """Base class for all parsers"""
    
    def __init__(self):
        self.bank_name = "UNKNOWN"
        self.account_type = "UNKNOWN"
    
    def can_parse(self, text: str) -> bool:
        """Check if this parser can handle the given text"""
        raise NotImplementedError("Subclasses must implement can_parse()")
    
    def parse(self, file_bytes: bytes, text: str, password: str = None) -> List[Transaction]:
        """Parse the statement and return list of transactions"""
        raise NotImplementedError("Subclasses must implement parse()")
    
    def extract_account_info(self, text: str) -> AccountInfo:
        """Extract account information from statement"""
        raise NotImplementedError("Subclasses must implement extract_account_info()")

