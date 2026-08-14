"""
SBI Credit Card Statement Parser

Format:
    DD MMM YY DESCRIPTION AMOUNT [C/D/M]
    
    Example:
    31 Oct 25 PAYMENT RECEIVED 000EU015304T36642007527 27,062.60 C
    17 Nov 25 FP EMI 04/06(EXCL TAX 22.14) 3,256.17 M
    15 Nov 25 EDAPPADY 2,500.00 D
"""

import re
from typing import List
from dateutil import parser as dateparser

from ..base import BaseParser, Transaction, AccountInfo, parse_amount, generate_transaction_id, extract_reference_number, categorize

class SBICreditCardParser(BaseParser):
    """Parser for SBI Credit Card statements"""
    
    # Date pattern: DD MMM YY (e.g., "31 Oct 25")
    DATE_RE = re.compile(
        r"^(\d{2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s+\d{2})\s+",
        re.IGNORECASE
    )
    
    # Amount and type at end: "1,234.56 C" or "1,234.56 D" or "1,234.56 M"
    AMOUNT_TYPE_RE = re.compile(
        r"([\d,]+\.\d{2})\s+([CDM])$"
    )
    
    def __init__(self):
        super().__init__()
        self.bank_name = "SBI"
        self.account_type = "credit_card"
    
    def can_parse(self, text: str) -> bool:
        """Check if this is an SBI Credit Card statement"""
        text_upper = text.upper()
        return (
            ("SBI CARD" in text_upper or "SBI CARDS AND PAYMENT" in text_upper) 
            and "CREDIT CARD NUMBER" in text_upper
        )
    
    def extract_account_info(self, text: str) -> AccountInfo:
        """Extract account information from SBI CC statement"""
        # Extract account number: XXXX XXXX XXXX XX42 -> "42"
        acc_pattern = r'CREDIT CARD NUMBER\s+(?:XXXX\s+){3}(?:XX)?(\d{2,4})'
        acc_match = re.search(acc_pattern, text, re.IGNORECASE)
        account_number = acc_match.group(1) if acc_match else "UNKNOWN"
        
        # Extract account holder name (usually appears early in statement)
        name_patterns = [
            r'^([A-Z][A-Z\s]+?)\s+Credit Card Number',  # Name before "Credit Card Number"
            r'MR[\.:]?\s+([A-Z\s]+)',
            r'MRS[\.:]?\s+([A-Z\s]+)',
            r'MS[\.:]?\s+([A-Z\s]+)'
        ]
        
        account_holder = None
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                account_holder = match.group(1).strip()
                break
        
        return AccountInfo(
            bank_name=self.bank_name,
            account_type=self.account_type,
            account_number=account_number,
            ifsc_code=None,  # Credit cards don't have IFSC
            account_holder=account_holder
        )
    
    def parse(self, file_bytes: bytes, text: str, password: str = None) -> List[Transaction]:
        """Parse SBI Credit Card statement"""
        account_info = self.extract_account_info(text)
        transactions = []
        lines = text.splitlines()
        
        for line in lines:
            line = line.strip()
            
            # Look for date pattern
            date_match = self.DATE_RE.match(line)
            if not date_match:
                continue
            
            # Skip header and footer lines
            skip_patterns = [
                "DATE", "TRANSACTION", "AMOUNT", "STATEMENT", "ACCOUNT SUMMARY",
                "REWARD", "SAVINGS", "IMPORTANT", "CHARGES", "PAGE", "SBI CARD",
                "FOR RENISH", "TRANSACTIONS FOR"
            ]
            if any(h in line.upper() for h in skip_patterns):
                continue
            
            # Look for amount and type at end
            amount_type_match = self.AMOUNT_TYPE_RE.search(line)
            if not amount_type_match:
                continue
            
            # Extract date
            date_str = date_match.group(1)  # "31 Oct 25"
            try:
                dt = dateparser.parse(date_str, dayfirst=True).date().isoformat()
            except:
                dt = date_str
            
            # Extract amount and type
            amount_str = amount_type_match.group(1)  # "27,062.60"
            tx_type_code = amount_type_match.group(2)  # "C", "D", or "M"
            
            amount = parse_amount(amount_str)
            
            # Determine transaction type
            if tx_type_code == "C":
                # Credit (payment received, refund, etc.)
                ttype = "credit"
            elif tx_type_code == "D":
                # Debit (purchase, fee, charge)
                amount = -abs(amount)
                ttype = "debit"
            elif tx_type_code == "M":
                # Monthly EMI installment - always debit
                amount = -abs(amount)
                ttype = "debit"
            else:
                # Fallback - assume debit
                amount = -abs(amount)
                ttype = "debit"
            
            # Extract description - everything between date and amount
            date_end = date_match.end()
            amount_start = amount_type_match.start()
            desc = line[date_end:amount_start].strip()
            
            # Clean up description
            desc = re.sub(r'\s+', ' ', desc).strip()
            
            # Extract reference number
            ref_num = extract_reference_number(desc)
            
            # Generate unique transaction ID
            tx_id = generate_transaction_id(dt, amount, desc, account_info.account_number)
            
            # Categorize
            category = categorize(desc)
            
            transaction = Transaction(
                date=dt,
                description=desc,
                amount=float(amount),
                type=ttype,
                category=category,
                bank_name=account_info.bank_name,
                account_type=account_info.account_type,
                account_number=account_info.account_number,
                transaction_id=tx_id,
                reference_number=ref_num
            )
            
            transactions.append(transaction)
        
        return transactions

