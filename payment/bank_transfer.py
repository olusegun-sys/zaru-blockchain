"""
Bank Transfer Module
===================
Handles bank transfers to Nigerian bank accounts.

Supports multiple providers:
- OPay Bank Transfer API
- Fallback to manual instructions
"""

import os
from typing import Dict, Any, Optional
from datetime import datetime

from .opay_client import OPayClient


class BankTransfer:
    """
    Bank transfer handler for Nigerian banks.
    
    Supports:
    - Automated transfers via OPay API
    - Manual transfer instructions (fallback)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.opay = OPayClient(
            merchant_id=self.config.get('merchant_id'),
            secret_key=self.config.get('secret_key'),
            sandbox=self.config.get('sandbox', True)
        )
        
        print(f"🏦 BankTransfer initialized")
    
    async def send_money(self, bank_code: str, account_number: str, amount: float, narration: str = "ZARU Transfer") -> Dict[str, Any]:
        """Send money to any Nigerian bank account."""
        return await self.opay.transfer_to_bank(
            amount=amount,
            bank_code=bank_code,
            account_number=account_number,
            narration=narration
        )