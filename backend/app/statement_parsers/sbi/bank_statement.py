"""
SBI Bank Statement Parser (Savings/Current Account)

Format:
    DD MMM YYYY DESCRIPTION - DEBIT - CREDIT - BALANCE
    
    Example:
    18 OCT 2024 UPI/DR/123456789/AMAZON - 1,234.56 - - 10,000.00
    19 OCT 2024 SALARY CREDIT - - 50,000.00 75,000.00
"""

import re
import io
from typing import List
import pdfplumber
from dateutil import parser as dateparser

from ..base import BaseParser, Transaction, AccountInfo, parse_amount, generate_transaction_id, extract_reference_number, categorize

class SBIBankStatementParser(BaseParser):
    """Parser for SBI Bank Statements (Savings/Current)"""
    
    # Date pattern: DD MMM YYYY (e.g., "18 OCT 2024")
    DATE_RE = re.compile(
        r"^\s*(\d{2}\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s+\d{4})",
        re.IGNORECASE
    )
    
    # Amount pattern
    AMT = r"(\d{1,10}(?:,\d{3})*\.\d{2})"
    DEBIT_RE = re.compile(rf"-\s+{AMT}\s+-")
    CREDIT_RE = re.compile(rf"-\s+-\s+{AMT}")
    
    def __init__(self):
        super().__init__()
        self.bank_name = "SBI"
        self.account_type = "savings"  # Default, can be updated
    
    
    def can_parse(self, text: str) -> bool:
        """Check if this is an SBI Bank Statement"""
        text_upper = text.upper()
        
        # Must have SBI indicators
        has_sbi = (
            "STATE BANK OF INDIA" in text_upper or 
            "SBIN" in text_upper or 
            "MICR CODE" in text_upper
        )
        
        if not has_sbi:
            return False
        
        # Must have bank statement specific keywords (not credit card)
        # These appear in bank statements but not credit card statements
        has_bank_statement_keywords = (
            "ACCOUNT DESCRIPTION" in text_upper or
            "DRAWING POWER" in text_upper or
            "IFS CODE" in text_upper or
            ("IFSC" in text_upper and "ACCOUNT NUMBER" in text_upper) or
            ("ACCOUNT NAME" in text_upper and "BALANCE AS ON" in text_upper)
        )

        
        # Exclude if it's clearly a credit card statement header
        # Check only the first 1000 characters to avoid matching footer warnings
        header_text = text_upper[:1000]
        is_credit_card_statement = (
            "CREDIT CARD NUMBER" in header_text or
            "CARD ACCOUNT" in header_text or
            ("SBI CARD" in header_text and "STATEMENT DATE" in header_text)
        )

        
        return has_bank_statement_keywords and not is_credit_card_statement

    
    def extract_account_info(self, text: str) -> AccountInfo:
        """Extract account information from SBI bank statement"""
        # Extract account number
        acc_patterns = [
            r'ACCOUNT NUMBER[:\s]*(\d+)',
            r'A/C NO[:\s]*(\d+)',
            r'ACCOUNT NO[:\s]*(\d+)',
            r'\b\d{11}\b'  # SBI account numbers are typically 11 digits
        ]
        
        account_number = "UNKNOWN"
        for pattern in acc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account_number = match.group(1) if 'ACCOUNT' in pattern.upper() else match.group(0)
                break
        
        # Extract IFSC code
        ifsc_code = None
        ifsc_match = re.search(r'(IFSC|IFS)[:\s]*(SBIN\d{7})', text, re.IGNORECASE)
        if ifsc_match:
            ifsc_code = ifsc_match.group(2)
        
        # Determine account type
        account_type = "savings"
        text_upper = text.upper()
        if "CURRENT" in text_upper or "CURRENT ACCOUNT" in text_upper:
            account_type = "current"
        elif "SAVINGS" in text_upper or "SB" in text_upper:
            account_type = "savings"
        
        # Extract account holder name
        account_holder = None
        name_patterns = [
            r'ACCOUNT NAME[:\s]*([A-Z\s\.]+)',
            r'MR[\.:]?\s+([A-Z\s]+)',
            r'MRS[\.:]?\s+([A-Z\s]+)',
            r'MS[\.:]?\s+([A-Z\s]+)'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account_holder = match.group(1).strip()
                break
        
        return AccountInfo(
            bank_name=self.bank_name,
            account_type=account_type,
            account_number=account_number,
            ifsc_code=ifsc_code,
            account_holder=account_holder
        )
    
    def parse(self, file_bytes: bytes, text: str, password: str = None) -> List[Transaction]:
        """Parse SBI Bank Statement"""
        account_info = self.extract_account_info(text)
        self.account_type = account_info.account_type  # Update parser's account type
        
        transactions = []
        
        # Re-open PDF with pdfplumber for better parsing
        if password:
            pdf = pdfplumber.open(io.BytesIO(file_bytes), password=password)
        else:
            pdf = pdfplumber.open(io.BytesIO(file_bytes))
        
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            lines = [ln.strip() for ln in page_text.splitlines()]
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                m = self.DATE_RE.match(line)
                if not m:
                    i += 1
                    continue
                
                date_str = m.group(1)
                try:
                    dt = dateparser.parse(date_str).date().isoformat()
                except:
                    dt = date_str
                
                full_desc = line
                
                # Handle multi-line descriptions
                if i + 1 < len(lines):
                    nxt = lines[i + 1]
                    if not self.DATE_RE.match(nxt):
                        if "ACHCr" in line or "ACHCR" in line.upper():
                            full_desc += " " + nxt
                            i += 1
                        elif (nxt.startswith("UPI/") or nxt.startswith("UPI")
                              or "/DR/" in nxt or "/CR/" in nxt or nxt.startswith("- ")):
                            full_desc += " " + nxt
                            i += 1
                
                # Extract amounts
                debit_match = self.DEBIT_RE.search(line)
                debit = parse_amount(debit_match.group(1)) if debit_match else 0.0
                
                credit_match = self.CREDIT_RE.search(line)
                credit = parse_amount(credit_match.group(1)) if credit_match else 0.0
                
                if debit == 0 and credit == 0:
                    amt_candidates = re.findall(self.AMT, line)
                    if len(amt_candidates) >= 2:
                        val = parse_amount(amt_candidates[-2])
                        if "/DR/" in line.upper() or "TRANSFER TO" in line.upper():
                            debit = val
                        else:
                            credit = val
                
                if debit > 0:
                    amount = -debit
                    ttype = "debit"
                else:
                    amount = credit
                    ttype = "credit"
                
                desc = full_desc[len(date_str):].strip()
                desc = re.sub(r"-\s+\d[\d,.]*\s+-", "", desc)
                desc = re.sub(r"-\s+-\s+\d[\d,.]*", "", desc)
                desc = re.sub(r"\s{2,}", " ", desc).strip()
                
                # Extract reference number
                ref_num = extract_reference_number(desc)
                
                # Generate unique transaction ID
                tx_id = generate_transaction_id(dt, amount, desc, account_info.account_number)
                
                # Categorize
                category = categorize(desc)
                
                # Force correction: dividends and salary should ALWAYS be credits (money in)
                if category in ["dividend", "salary"] and ttype == "debit":
                    amount = abs(amount)  # Make positive
                    ttype = "credit"
                
                transaction = Transaction(
                    date=dt,
                    description=desc,
                    amount=amount,
                    type=ttype,
                    category=category,
                    bank_name=account_info.bank_name,
                    account_type=account_info.account_type,
                    account_number=account_info.account_number,
                    transaction_id=tx_id,
                    reference_number=ref_num
                )
                
                transactions.append(transaction)
                i += 1
        
        pdf.close()
        return transactions

