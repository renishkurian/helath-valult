"""
HDFC Credit Card Statement Parser

Format:
    DD/MM/YYYY| HH:MM DESCRIPTION C AMOUNT
    
    Example:
    22/10/2025| 00:00 AMAZON PURCHASE C 1,234.56
    23/10/2025| 12:30 FLIPKART + C 500.00  (+ indicates credit/refund)
"""

import re
from typing import List
from dateutil import parser as dateparser

from ..base import BaseParser, Transaction, AccountInfo, parse_amount, generate_transaction_id, extract_reference_number, categorize

class HDFCCreditCardParser(BaseParser):
    """Parser for HDFC Credit Card statements"""
    
    # Date pattern: DD/MM/YYYY| HH:MM
    DATE_RE = re.compile(
        r"(\d{2}/\d{2}/\d{4})\|\s*(\d{2}:\d{2})"
    )
    
    # Amount pattern: optional "+" followed by "C" and amount
    AMOUNT_RE = re.compile(
        r"(?:\+\s*)?C\s*([\d,]+(?:\.\d{2})?)"
    )
    
    def __init__(self):
        super().__init__()
        self.bank_name = "HDFC"
        self.account_type = "credit_card"
    
    def can_parse(self, text: str) -> bool:
        """Check if this is an HDFC Credit Card statement"""
        text_upper = text.upper()
        return (
            ("HDFC BANK CREDIT CARDS" in text_upper or 
             "MONEYBACK CREDIT CARD" in text_upper or 
             "CREDIT CARD STATEMENT" in text_upper) 
            and "HDFC" in text_upper
        )
    
    def extract_account_info(self, text: str) -> AccountInfo:
        """Extract account information from HDFC CC statement"""
        # Extract account number patterns
        acc_patterns = [
            r'CREDIT CARD NO[.\s:]*(\d{4}[X\*]+\d{4})',  # 5459XXXXXX2625
            r'ALTERNATE ACCOUNT NUMBER[:\s]*(\d+)',
        ]
        
        account_number = "UNKNOWN"
        for pattern in acc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                account_number = match.group(1)
                break
        
        # Extract account holder name
        name_patterns = [
            r'CREDIT CARD NO[.\s:]*\d+[X\*]+\d+\s+([A-Z\s]+?)(?:\s+Credit Card|$)',
            r'^([A-Z\s]+?)\s+Credit Card No',
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
        """Parse HDFC Credit Card statement"""
        account_info = self.extract_account_info(text)
        transactions = []
        lines = text.splitlines()
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for date pattern
            date_match = self.DATE_RE.search(line)
            if not date_match:
                i += 1
                continue
            
            # Skip header lines
            if any(h in line.upper() for h in ["DATE & TIME", "TRANSACTION DESCRIPTION", "REWARDS", "AMOUNT", "PI", "DOMESTIC TRANSACTIONS"]):
                i += 1
                continue
            
            date_str = date_match.group(1)  # DD/MM/YYYY
            time_str = date_match.group(2)  # HH:MM
            
            try:
                dt = dateparser.parse(date_str, dayfirst=True).date().isoformat()
            except:
                dt = date_str
            
            # Extract amount
            amount_match = self.AMOUNT_RE.search(line)
            if not amount_match:
                i += 1
                continue
            
            # Get description part first to check for EMI
            date_end = date_match.end()
            amount_start = amount_match.start()
            desc_on_line = line[date_end:amount_start].strip()
            
            # Check if it's a credit (has "+" immediately before "C")
            c_pos = line.find("C")
            is_credit = False
            if c_pos > 0:
                before_c = line[max(0, c_pos-3):c_pos].strip()
                is_credit = before_c.endswith("+")
            
            amount_str = amount_match.group(1)
            amount = parse_amount(amount_str)
            
            # Check for EMI in description
            desc_upper = desc_on_line.upper()
            is_emi = "EMI" in desc_upper
            
            # Also check previous line for EMI
            if i > 0 and not is_emi:
                prev_line_upper = lines[i - 1].strip().upper()
                is_emi = "EMI" in prev_line_upper
            
            if is_emi:
                # EMI is always a debit
                amount = -abs(amount)
                ttype = "debit"
            elif is_credit:
                ttype = "credit"
            else:
                amount = -abs(amount)
                ttype = "debit"
            
            # Build description - HDFC format often has description split across lines
            desc_parts = []
            
            # Look backwards for description start (previous line)
            if i > 0:
                prev_line = lines[i - 1].strip()
                if not self.DATE_RE.search(prev_line) and prev_line:
                    skip_patterns = ["PAGE", "DOMESTIC TRANSACTIONS", "DATE & TIME", "TOTAL AMOUNT", 
                                   "ELIGIBLE FOR", "RENISH KURIAN", "TRANSACTIONS TOTAL", "100%"]
                    if not any(h in prev_line.upper() for h in skip_patterns):
                        if len(prev_line) > 5:
                            has_ref = "Ref#" in prev_line or "REF#" in prev_line
                            has_text = any(c.isalpha() for c in prev_line)
                            is_not_amount = not self.AMOUNT_RE.search(prev_line)
                            is_not_name = len(prev_line.split()) <= 2 and not has_ref
                            if (has_ref or (has_text and not is_not_name)) and is_not_amount:
                                desc_parts.append(prev_line)
            
            # Extract description from current line
            current_desc = line[date_end:amount_start].strip()
            current_desc = re.sub(r'\s+l\s*$', '', current_desc).strip()
            if current_desc:
                desc_parts.append(current_desc)
            
            # Look forward for continuation (next line)
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if not self.DATE_RE.match(next_line) and next_line:
                    skip_patterns = ["PAGE", "DOMESTIC TRANSACTIONS", "TOTAL AMOUNT", 
                                   "ELIGIBLE FOR", "MONEYBACK", "HDFC BANK", "OFFERS ON", "TRANSACTIONS TOTAL"]
                    if not any(h in next_line.upper() for h in skip_patterns):
                        ends_with_paren = next_line.endswith(")") and len(next_line) >= 10
                        is_long_digit = len(next_line) >= 10 and next_line.replace("(", "").replace(")", "").replace("-", "").isdigit()
                        has_ref_marker = "Ref#" in next_line or "REF#" in next_line
                        is_text_continuation = (
                            len(next_line) > 5 and 
                            not self.AMOUNT_RE.search(next_line) and 
                            not next_line.startswith("C") and
                            any(c.isalpha() for c in next_line) and
                            not next_line.upper().startswith("TRANSACTIONS")
                        )
                        
                        if ends_with_paren or is_long_digit or has_ref_marker or is_text_continuation:
                            desc_parts.append(next_line)
                            i += 1
            
            # Combine description
            desc = " ".join(desc_parts)
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = re.sub(r'\s+l\s*$', '', desc).strip()
            
            if not desc or len(desc) < 5:
                desc = line[date_end:amount_start].strip()
                desc = re.sub(r'\s+l\s*$', '', desc).strip()
            
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
            i += 1
        
        return transactions

