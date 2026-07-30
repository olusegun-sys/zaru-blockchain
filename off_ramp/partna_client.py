Partna Off-Ramp Client (Backup) 
============================== 
Backup integration if Monica Cash is unavailable. 
 
import os 
import aiohttp 
from typing import Dict, Any 
 
 
class PartnaClient: 
    """Client for Partna off-ramp API (backup).""" 
 
    BASE_URL = "https://api.partna.com/v1" 
 
    def __init__(self, config: Dict[str, Any] = None): 
        self.config = config or {} 
        self.api_key = self.config.get('api_key') or os.getenv('PARTNA_API_KEY') 
        self.business_id = self.config.get('business_id') or os.getenv('PARTNA_BUSINESS_ID') 
        self.session = None 
        print("?? PartnaClient initialized (backup)") 
 
    async def _get_session(self) -
        if self.session is None or self.session.closed: 
            self.session = aiohttp.ClientSession() 
        return self.session 
 
    async def create_payout(self, amount: float, currency: str, bank_account: str) -, Any]: 
        """Create a payout to bank account.""" 
        return { 
            "success": True, 
            "message": "Partna integration placeholder - implement with real API", 
            "amount": amount, 
            "currency": currency 
        } 
 
    async def close(self): 
        if self.session and not self.session.closed: 
            await self.session.close() 
