"""
Generic/Fallback Parser for Unknown Bank Statements

This parser attempts to find transactions in statements from banks
that don't have a dedicated parser yet.
"""

import re
from typing import List
from dateutil import parser as dateparser

from .base import BaseParser, Transaction, AccountInfo, parse_amount, generate_transaction_id, extract_reference_number, categorize

class GenericParser(BaseParser):
    """Generic fallback parser for unknown bank statements"""
    
    DATE_RE = re.compile(
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|'
        r'JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s+\d{4})',
        re.IGNORECASE
    )
    
    def __init__(self):
        super().__init__()
        self.bank_name = "UNKNOWN"
        self.account_type = "savings"
    
    def can_parse(self, text: str) -> bool:
        """Generic parser can always attempt to parse"""
        return True
    
    def extract_account_info(self, text: str) -> AccountInfo:
        """Extract basic account information"""
        # Try to extract account number
        acc_patterns = [
            r'ACCOUNT NUMBER[:\s]*(\d+)',
            r'A/C NO[:\s]*(\d+)',
            r'ACCOUNT NO[:\s]*(\d+)',
            r'\b\d{11,16}\b'
        ]
        
        account_number = "UNKNOWN"
        for pattern in acc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account_number = match.group(1) if 'ACCOUNT' in pattern.upper() else match.group(0)
                break
        
        return AccountInfo(
            bank_name=self.bank_name,
            account_type=self.account_type,
            account_number=account_number,
            ifsc_code=None,
            account_holder=None
        )
    
    def parse(self, file_bytes: bytes, text: str, password: str = None) -> List[Transaction]:
        """Parse using generic patterns"""
        account_info = self.extract_account_info(text)
        transactions = []
        lines = text.splitlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            date_m = self.DATE_RE.match(line)
            if not date_m:
                continue
            
            line_upper = line.upper()
            
            # Skip headers and irrelevant lines
            if any(h in line_upper for h in ["ACCOUNT", "BRANCH", "ADDRESS", "BALANCE AS ON", "STATEMENT", "CIF"]):
                continue
            
            # Look for transaction keywords
            has_keywords = any(kw in line_upper for kw in [
                "TRANSFER", "UPI", "ACH", "NEFT", "RTGS", "IMPS", "DIVIDEND",
                "INTEREST", "SALARY", "PURCHASE", "DEPOSIT", "WITHDRAWAL"
            ])
            
            if not has_keywords:
                continue
            
            try:
                dt = dateparser.parse(date_m.group(0), dayfirst=True).date().isoformat()
            except:
                dt = date_m.group(0)
            
            # Determine debit/credit
            is_debit = any(k in line_upper for k in ["TRANSFER TO", "/DR/", "DEBIT", "WITHDRAWAL", "ACHDR"])
            is_credit = any(k in line_upper for k in ["TRANSFER FROM", "/CR/", "CREDIT", "DEPOSIT", "SALARY", "DIVIDEND", "ACHCR"])
            
            debit_amt = credit_amt = 0
            
            # Try to extract amounts
            debit_pattern = re.findall(r'-\s+(\d{1,10}(?:,\d{3})*(?:\.\d{2}))\s+-', line)
            if debit_pattern:
                debit_amt = parse_amount(debit_pattern[0])
            
            credit_pattern = re.findall(r'-\s+-\s+(\d{1,10}(?:,\d{3})*(?:\.\d{2}))', line)
            if credit_pattern:
                credit_amt = parse_amount(credit_pattern[0])
            
            if debit_amt > 0:
                amt = -debit_amt
                ttype = "debit"
            elif credit_amt > 0:
                amt = credit_amt
                ttype = "credit"
            else:
                # Fallback: find any decimal amounts
                amounts = re.findall(r'\b\d{1,10}(?:,\d{3})*\.\d{2}\b', line)
                if not amounts:
                    continue
                amt = parse_amount(amounts[0])
                if is_credit:
                    ttype = "credit"
                else:
                    amt = -abs(amt)
                    ttype = "debit"
            
            # Clean description
            desc_clean = line[len(date_m.group(0)):].strip()
            desc_clean = re.sub(r'\s{2,}', ' ', desc_clean).strip()
            
            ref_num = extract_reference_number(desc_clean)
            tx_id = generate_transaction_id(dt, amt, desc_clean, account_info.account_number)
            category = categorize(desc_clean)
            
            # Force correction: dividends and salary should ALWAYS be credits (money in)
            if category in ["dividend", "salary"] and ttype == "debit":
                amt = abs(amt)  # Make positive
                ttype = "credit"
            
            transaction = Transaction(
                date=dt,
                description=desc_clean,
                amount=float(amt),
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

