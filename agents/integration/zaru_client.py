"""
ZARU Client
===========
Integration with the ZARU blockchain for settlement and fee collection.

This leverages your existing ZARU infrastructure for:
- Transaction fees (gas in ZARU)
- Profit settlement
- Agent identity and reputation
- Smart contract interactions
"""

import aiohttp
import json
from typing import Dict, Any, Optional
from datetime import datetime

from config import settings


class ZaruClient:
    """
    Client for interacting with the ZARU blockchain.
    
    Uses your existing API endpoints for seamless integration.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.api_url = config.get('api_url', settings.API_URL or 'https://zaru-api.onrender.com')
        self.wallet_address = config.get('wallet_address')
        self.private_key = config.get('private_key')
        self.session = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_zaru_rate(self) -> float:
        """Get current ZARU/USD exchange rate."""
        # In production, this would come from a DEX or oracle
        # For now, use a placeholder or get from API
        return 0.01  # 1 ZARU = $0.01 (placeholder)
    
    async def get_balance(self, address: Optional[str] = None) -> float:
        """Get ZARU balance for an address."""
        address = address or self.wallet_address
        if not address:
            return 0.0
        
        session = await self._get_session()
        async with session.get(f"{self.api_url}/wallet/balance/{address}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get('total', 0) / 100_000_000  # Convert from satoshis
            return 0.0
    
    async def create_settlement(
        self,
        amount: float,
        token: str,
        profit_usd: float,
        memo: str = ""
    ) -> Dict[str, Any]:
        """
        Create a settlement transaction on the ZARU chain.
        
        This uses your existing wallet/send endpoint.
        """
        if not self.wallet_address:
            return {'error': 'No wallet configured'}
        
        # Convert to satoshis
        amount_satoshis = int(amount * 100_000_000)
        
        # Create a settlement transaction
        session = await self._get_session()
        
        # Use the mining address as the recipient for fees
        # In production, this would go to a fee collection address
        settlement_data = {
            'to_address': settings.MINING_ADDRESS,
            'amount': amount_satoshis,
            'from_address': self.wallet_address,
            'fee': 0,
            'memo': f"Settlement: {token} arbitrage profit ${profit_usd:.2f}"
        }
        
        async with session.post(
            f"{self.api_url}/wallet/send",
            json=settlement_data
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {
                    'success': True,
                    'tx_id': data.get('tx_id'),
                    'amount_zaru': amount,
                    'profit_usd': profit_usd,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                error = await resp.text()
                return {'success': False, 'error': error}
    
    async def record_agent_action(
        self,
        agent_name: str,
        action: str,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Record agent actions on-chain for transparency.
        
        This creates an immutable record of agent decisions.
        """
        # Create a record transaction on ZARU
        session = await self._get_session()
        
        record_data = {
            'to_address': settings.MINING_ADDRESS,  # Fee address
            'amount': 1000,  # 0.00001 ZARU fee
            'from_address': self.wallet_address,
            'fee': 0,
            'memo': f"AGENT:{agent_name}:{action}:{json.dumps(details)}"
        }
        
        async with session.post(
            f"{self.api_url}/wallet/send",
            json=record_data
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {'success': True, 'tx_id': data.get('tx_id')}
            return {'success': False, 'error': await resp.text()}
    
    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()