"""
OPay API Client for ZARU Payment System
=======================================
Complete OPay integration for bank transfers, virtual wallets, and payments.

IMPORTANT: This requires merchant credentials from OPay.
You need to register as a merchant and get your merchant_id, secret_key, and public_key.
"""

import os
import hmac
import hashlib
import base64
import time
import json
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class OPayClient:
    """
    OPay API Client for bank transfers and payments.
    
    Supported Features:
    - Bank Transfer API: Send money to any Nigerian bank account
    - Bank Transfer (Direct): Create payment order with webhooks
    - Digital Wallet API: Create virtual wallets for customers
    """
    
    BASE_URL_SANDBOX = "https://sandbox.opay.ng"
    BASE_URL_PRODUCTION = "https://api.opay.ng"
    
    BANK_CODES = {
        "OPAY": "999992",
        "FIDELITY": "070",
        "GTB": "058",
        "ACCESS": "044",
        "ZENITH": "057",
        "UBA": "033",
        "FIRSTBANK": "011"
    }
    
    def __init__(self, merchant_id: Optional[str] = None, secret_key: Optional[str] = None, sandbox: bool = True):
        self.merchant_id = merchant_id or os.getenv("OPAY_MERCHANT_ID")
        self.secret_key = secret_key or os.getenv("OPAY_SECRET_KEY")
        self.sandbox = sandbox or os.getenv("OPAY_SANDBOX", "true").lower() == "true"
        self.base_url = self.BASE_URL_SANDBOX if self.sandbox else self.BASE_URL_PRODUCTION
        self.session = None
        
        print(f"🔗 OPayClient initialized")
        print(f"   Environment: {'SANDBOX' if self.sandbox else 'PRODUCTION'}")
        print(f"   Merchant ID: {self.merchant_id[:8] if self.merchant_id else 'NOT SET'}...")