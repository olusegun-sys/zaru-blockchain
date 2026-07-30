Monica Cash Off-Ramp Client 
============================= 
Integrates with Monica Cash API for USDT to Naira conversion. 
 
Features: 
- Get USDT deposit address 
- Check balance 
- Withdraw to Nigerian bank account 
- Webhook handling for deposits 
 
import os 
import json 
import aiohttp 
from typing import Dict, Any, Optional, List 
from datetime import datetime 
 
 
class MonicaClient: 
    Client for Monica Cash off-ramp API. 
 
    Monica Cash provides crypto-to-Naira conversion with 
    sub-60 second settlement to Nigerian bank accounts. 
 
    BASE_URL = "https://api.monica.cash/v1" 
 
    def __init__(self, config: Dict[str, Any] = None): 
        self.config = config or {} 
        self.api_key = self.config.get('api_key') or os.getenv('MONICA_API_KEY') 
        self.customer_ref = self.config.get('customer_ref') or os.getenv('MONICA_CUSTOMER_REF', 'zaru_user_001') 
        self.bank_account = self.config.get('bank_account') or os.getenv('MONICA_BANK_ACCOUNT') 
        self.bank_code = self.config.get('bank_code') or os.getenv('MONICA_BANK_CODE') 
        self.session = None 
 
        print(f"?? MonicaClient initialized") 
        print(f"   Customer Ref: {self.customer_ref}") 
        print(f"   Bank Account: {self.bank_account or 'Not set'}") 
 
    async def _get_session(self) -
        if self.session is None or self.session.closed: 
            self.session = aiohttp.ClientSession() 
        return self.session 
 
    async def _request(self, method: str, endpoint: str, data: Dict = None) -
        """Make an authenticated request to Monica Cash API.""" 
        session = await self._get_session() 
        headers = { 
            'Authorization': f'Bearer {self.api_key}', 
            'Content-Type': 'application/json' 
        } 
 
        async with session.request( 
            method, 
            f"{self.BASE_URL}{endpoint}", 
            headers=headers, 
            json=data 
        ) as resp: 
            if resp.status 
                error = await resp.text() 
                return {'error': error, 'status': resp.status} 
            return await resp.json() 
 
    async def get_deposit_address(self, asset: str = "USDT", network: str = "TRC20") -, Any]: 
        Get a deposit address for receiving USDT. 
 
        This is where you send USDT from your wallet. 
        Monica automatically converts to Naira and sends to your bank. 
        data = { 
            'customer_ref': self.customer_ref, 
            'asset': asset, 
            'network': network, 
            'label': f'ZARU_Settlement_{datetime.now().strftime("%Y%m%d")}' 
        } 
        return await self._request('POST', '/wallets', data) 
 
    async def get_wallet_balance(self, wallet_id: str) -, Any]: 
        """Get balance of a Monica wallet.""" 
        return await self._request('GET', f'/wallets/{wallet_id}/balance') 
 
    async def get_exchange_rate(self, from_asset: str = "USDT", to_asset: str = "NGN") -, Any]: 
        """Get current exchange rate.""" 
 
    async def withdraw_to_bank(self, amount: float, bank_account: str = None) -, Any]: 
        Withdraw Naira to a Nigerian bank account. 
 
        This is the final step - Naira hits your account. 
        bank_account = bank_account or self.bank_account 
        if not bank_account: 
            return {'error': 'No bank account configured'} 
 
        data = { 
            'customer_ref': self.customer_ref, 
            'amount': amount, 
            'currency': 'NGN', 
            'bank_account': bank_account, 
            'bank_code': self.bank_code, 
            'narration': f'ZARU Off-Ramp Settlement' 
        } 
        return await self._request('POST', '/withdrawals', data) 
 
    async def get_transaction_status(self, tx_id: str) -, Any]: 
        """Check status of a transaction.""" 
        return await self._request('GET', f'/transactions/{tx_id}') 
 
    async def handle_webhook(self, payload: Dict[str, Any]) -, Any]: 
        Handle webhook from Monica Cash. 
 
        Monica sends webhooks for: 
        - deposit.confirmed (USDT received) 
        - withdrawal.completed (Naira sent) 
        event_type = payload.get('event') 
        data = payload.get('data', {}) 
 
        if event_type == 'deposit.confirmed': 
            print(f"? USDT deposit confirmed: {data.get('amount')} USDT") 
            return {'status': 'deposit_confirmed', 'data': data} 
 
        if event_type == 'withdrawal.completed': 
            print(f"? Naira withdrawal completed: ?{data.get('amount')}") 
            return {'status': 'withdrawal_completed', 'data': data} 
 
        return {'status': 'unknown_event', 'event': event_type} 
 
    async def close(self): 
        if self.session and not self.session.closed: 
            await self.session.close() 
