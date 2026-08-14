"""
HDFC Bank Statement Parser (Savings/Current Account)

TODO: Implement HDFC bank statement parser when needed
"""

from typing import List
from ..base import BaseParser, Transaction

class HDFCBankStatementParser(BaseParser):
    """Parser for HDFC Bank Statements (Savings/Current) - To be implemented"""
    
    def __init__(self):
        super().__init__()
        self.bank_name = "HDFC"
        self.account_type = "savings"
    
    def can_parse(self, text: str) -> bool:
        """Check if this is an HDFC Bank Statement"""
        # TODO: Implement when needed
        return False
    
    def extract_account_info(self, text: str):
        """Extract account information"""
        # TODO: Implement when needed
        pass
    
    def parse(self, file_bytes: bytes, text: str, password: str = None) -> List[Transaction]:
        """Parse HDFC Bank Statement"""
        # TODO: Implement when needed
        return []

