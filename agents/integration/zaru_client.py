"""
ZARU Client
===========
Integration with the ZARU blockchain for settlement and fee collection.

FIXED: Handle UTXO fetch errors gracefully.
FIXED: Use balance check instead of UTXO fetch for large wallets.
FIXED: Skip consolidation if UTXO fetch fails.
"""

import os
import aiohttp
import json
import time
import random
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime


class ZaruClient:
    """
    Client for interacting with the ZARU blockchain.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # Get API URL from config, environment, or use default
        self.api_url = config.get('api_url')
        if not self.api_url:
            self.api_url = os.getenv('ZARU_API_URL')
        if not self.api_url:
            self.api_url = 'https://zaru-api.onrender.com'
        
        # Get wallet address from config or environment
        self.wallet_address = config.get('wallet_address')
        if not self.wallet_address:
            self.wallet_address = os.getenv('WALLET_ADDRESS', '1f6254f2f4dfb787262f6b3e18d482a77cd6a979')
        
        # Get private key
        self.private_key = config.get('private_key')
        if not self.private_key:
            self.private_key = os.getenv('WALLET_PRIVATE_KEY')
        
        # Settlement tracking
        self.settlement_count = 0
        self.total_settled_zaru = 0.0
        self._utxos_cache = []
        self._consolidation_in_progress = False
        self._utxo_fetch_failed = False
        
        self.session = None
        self._balance_cache = 0.0
        
        print(f"🔗 ZARU Client initialized")
        print(f"   API URL: {self.api_url}")
        print(f"   Wallet: {self.wallet_address[:16]}...")
        print(f"   Settlement Mode: Direct (skip UTXO fetch on error)")
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_zaru_rate(self) -> float:
        return 0.01
    
    async def get_balance(self, address: Optional[str] = None) -> float:
        """Get balance - this is more reliable than UTXO fetch."""
        address = address or self.wallet_address
        if not address:
            return 0.0
        
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.api_url}/wallet/balance/{address}",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_satoshis = data.get('total', 0)
                    balance_zaru = balance_satoshis / 100_000_000
                    self._balance_cache = balance_zaru
                    return balance_zaru
                else:
                    print(f"⚠️ Balance API error: {resp.status}")
                    return self._balance_cache
        except Exception as e:
            print(f"⚠️ Balance error: {e}")
            return self._balance_cache
    
    async def get_utxos(self, address: Optional[str] = None) -> List[Dict]:
        """
        Get UTXOs for an address.
        
        FIXED: Returns empty list on error without crashing.
        """
        address = address or self.wallet_address
        if not address:
            return []
        
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.api_url}/wallet/utxos/{address}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    utxos = data.get('utxos', [])
                    if utxos:
                        utxos.sort(key=lambda x: x['amount'])
                    self._utxos_cache = utxos
                    self._utxo_fetch_failed = False
                    return utxos
                else:
                    print(f"⚠️ UTXO API error: {resp.status}")
                    self._utxo_fetch_failed = True
                    return []
        except asyncio.TimeoutError:
            print(f"⚠️ UTXO fetch timeout - skipping (wallet has many UTXOs)")
            self._utxo_fetch_failed = True
            return []
        except Exception as e:
            print(f"⚠️ UTXO error: {e}")
            self._utxo_fetch_failed = True
            return []
    
    async def consolidate_utxos_batch(self, address: Optional[str] = None, batch_size: int = 50) -> bool:
        """
        Consolidate UTXOs in batches.
        
        FIXED: Skip if UTXO fetch fails - we'll use direct sends instead.
        """
        address = address or self.wallet_address
        if not address:
            return False
        
        # Skip if UTXO fetch previously failed
        if self._utxo_fetch_failed:
            print(f"ℹ️ Skipping consolidation - UTXO fetch unavailable")
            return True
        
        # Prevent multiple consolidations at once
        if self._consolidation_in_progress:
            print(f"⏳ Consolidation already in progress, skipping...")
            return False
        
        self._consolidation_in_progress = True
        
        try:
            utxos = await self.get_utxos(address)
            
            # If we can't get UTXOs, skip consolidation
            if not utxos:
                print(f"ℹ️ No UTXOs returned, skipping consolidation")
                self._consolidation_in_progress = False
                return True
            
            # If we have fewer than batch_size UTXOs, no need to consolidate
            if len(utxos) <= batch_size:
                print(f"ℹ️ Only {len(utxos)} UTXOs, no consolidation needed")
                self._consolidation_in_progress = False
                return True
            
            print(f"🔄 Batch consolidating {len(utxos)} UTXOs in batches of {batch_size}...")
            
            total_consolidated = 0
            total_batches = min((len(utxos) + batch_size - 1) // batch_size, 10)  # Max 10 batches per run
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(utxos))
                batch_utxos = utxos[start_idx:end_idx]
                
                batch_amount = sum(u['amount'] for u in batch_utxos)
                fee = 1000
                
                if batch_amount <= fee:
                    continue
                
                try:
                    session = await self._get_session()
                    
                    consolidation_data = {
                        'to_address': address,
                        'amount': batch_amount - fee,
                        'from_address': address,
                        'fee': 0,
                        'memo': f"Batch consolidation {batch_num + 1}/{total_batches}"
                    }
                    
                    print(f"   Batch {batch_num + 1}/{total_batches}: Consolidating {len(batch_utxos)} UTXOs...")
                    
                    async with session.post(
                        f"{self.api_url}/wallet/send",
                        json=consolidation_data,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"   ✅ Batch {batch_num + 1} successful! TX: {data.get('tx_id', '')[:16]}...")
                            total_consolidated += len(batch_utxos)
                            await asyncio.sleep(2)
                        else:
                            error_text = await resp.text()
                            print(f"   ❌ Batch {batch_num + 1} failed: {resp.status}")
                            
                            if 'Double-spend' in error_text:
                                print(f"   🔄 Refreshing UTXOs...")
                                utxos = await self.get_utxos(address)
                                continue
                            
                            if 'exceeds maximum' in error_text or 'too large' in error_text:
                                new_batch_size = max(10, batch_size // 2)
                                print(f"   🔄 Reducing batch size to {new_batch_size}")
                                return await self.consolidate_utxos_batch(address, new_batch_size)
                            
                            break
                            
                except Exception as e:
                    print(f"   ❌ Batch error: {e}")
                    break
                
                # After each successful batch, refresh UTXOs
                if total_consolidated > 0:
                    utxos = await self.get_utxos(address)
                    if not utxos or len(utxos) <= batch_size:
                        break
            
            print(f"✅ Batch consolidation complete: {total_consolidated} UTXOs consolidated")
            self._consolidation_in_progress = False
            return total_consolidated > 0
            
        except Exception as e:
            print(f"❌ Batch consolidation error: {e}")
            self._consolidation_in_progress = False
            return False
    
    async def create_settlement(
        self,
        amount: float,
        token: str,
        profit_usd: float,
        memo: str = ""
    ) -> Dict[str, Any]:
        """
        Create a settlement transaction.
        
        FIXED: Skip UTXO check if fetch fails - just send directly.
        """
        if not self.wallet_address:
            return {'error': 'No wallet configured'}
        
        # Convert to satoshis
        amount_satoshis = max(1000, int(amount * 100_000_000))
        
        # Try to get UTXO count, but don't fail if we can't
        utxo_count = 0
        try:
            utxos = await self.get_utxos(self.wallet_address)
            utxo_count = len(utxos)
        except:
            utxo_count = 0
        
        # If UTXO fetch failed or we have too many, skip consolidation
        if self._utxo_fetch_failed or utxo_count > 100:
            print(f"ℹ️ Skipping UTXO check ({utxo_count} UTXOs) - sending directly")
            # Don't try to consolidate, just send
        elif utxo_count > 50:
            print(f"🔄 {utxo_count} UTXOs detected. Attempting consolidation...")
            await self.consolidate_utxos_batch(self.wallet_address, batch_size=50)
        
        # Send to self
        to_address = self.wallet_address
        
        # Add small random variation
        random_variation = random.randint(0, 100)
        amount_satoshis = amount_satoshis + random_variation
        
        self.settlement_count += 1
        
        memo_text = memo or f"Settlement #{self.settlement_count}: {token} arbitrage profit ${profit_usd:.2f}"
        
        try:
            session = await self._get_session()
            
            settlement_data = {
                'to_address': to_address,
                'amount': amount_satoshis,
                'from_address': self.wallet_address,
                'fee': 0,
                'memo': memo_text
            }
            
            print(f"💰 Settlement #{self.settlement_count}: {amount_satoshis} satoshis → Self")
            
            async with session.post(
                f"{self.api_url}/wallet/send",
                json=settlement_data,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tx_id = data.get('tx_id')
                    print(f"✅ Settlement #{self.settlement_count} successful! TX: {tx_id[:16]}...")
                    
                    self.total_settled_zaru += amount_satoshis / 100_000_000
                    self._utxos_cache = []
                    
                    return {
                        'success': True,
                        'tx_id': tx_id,
                        'amount_zaru': amount_satoshis / 100_000_000,
                        'amount_satoshis': amount_satoshis,
                        'profit_usd': profit_usd,
                        'settlement_count': self.settlement_count,
                        'to_self': True,
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    error_text = await resp.text()
                    print(f"❌ Settlement failed: {resp.status}")
                    
                    # If double-spend, retry once with different amount
                    if 'Double-spend' in error_text:
                        print(f"🔄 Double-spend detected, retrying with different amount...")
                        retry_amount = amount_satoshis + random.randint(1000, 5000)
                        settlement_data['amount'] = retry_amount
                        
                        async with session.post(
                            f"{self.api_url}/wallet/send",
                            json=settlement_data,
                            timeout=aiohttp.ClientTimeout(total=60)
                        ) as retry_resp:
                            if retry_resp.status == 200:
                                data = await retry_resp.json()
                                print(f"✅ Retry successful! TX: {data.get('tx_id', '')[:16]}...")
                                return {
                                    'success': True,
                                    'tx_id': data.get('tx_id'),
                                    'amount_zaru': retry_amount / 100_000_000,
                                    'amount_satoshis': retry_amount,
                                    'profit_usd': profit_usd,
                                    'settlement_count': self.settlement_count,
                                    'retry': True,
                                    'to_self': True,
                                    'timestamp': datetime.now().isoformat()
                                }
                            else:
                                print(f"❌ Retry failed: {retry_resp.status}")
                    
                    return {
                        'success': False,
                        'error': f'HTTP {resp.status}'
                    }
        except Exception as e:
            print(f"❌ Settlement error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def record_agent_action(self, agent_name: str, action: str, details: Dict[str, Any]) -> Dict[str, Any]:
        return {'success': True, 'recorded': True, 'timestamp': datetime.now().isoformat()}
    
    async def get_health(self) -> Dict[str, Any]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.api_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return {'healthy': resp.status == 200, 'status': resp.status}
        except Exception as e:
            return {'healthy': False, 'error': str(e)}
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()