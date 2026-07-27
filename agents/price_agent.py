"""
Price Agent
===========
Monitors prices across CEX and DEX exchanges in real-time.

Uses WebSocket for low-latency price feeds [citation:4][citation:8].
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.integration.cex_client import CEXClient
from agents.integration.dex_client import DEXClient
from agents.integration.aggregator_client import AggregatorClient


class PriceAgent(BaseAgent):
    """
    Real-time price monitoring agent.
    
    Features:
    - WebSocket connections for real-time data [citation:4]
    - CEX/DEX price aggregation
    - Price difference calculation
    - Historical price tracking
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("price_agent", config)
        self.cex_client = CEXClient(config.get('cex', {}))
        self.dex_client = DEXClient(config.get('dex', {}))
        self.aggregator = AggregatorClient(config.get('aggregator', {}))
        
        self.price_cache: Dict[str, Dict[str, float]] = {}
        self.ws_tasks: List[asyncio.Task] = []
        
    async def run(self):
        """Main price monitoring loop."""
        await self.start()
        
        # Start WebSocket connections
        if self.config.get('use_websocket', True):
            await self._start_websocket_feeds()
        
        while self.running:
            try:
                # Poll for prices (fallback if WebSocket fails)
                prices = await self._poll_prices()
                self._update_price_cache(prices)
                
                # Log price differences
                diffs = self._calculate_price_differences(prices)
                if diffs:
                    self.logger.info(f"Price differences: {diffs}")
                    self.metrics.record_prices(prices)
                    
                await asyncio.sleep(self.config.get('poll_interval', 5))
                
            except Exception as e:
                self.logger.error(f"Price monitoring error: {e}")
                await asyncio.sleep(5)
                
        await self.stop()
    
    async def _start_websocket_feeds(self):
        """Start WebSocket connections for real-time data [citation:4]."""
        if self.config.get('cex', {}).get('enabled', True):
            task = asyncio.create_task(self._ws_cex_feed())
            self.ws_tasks.append(task)
            
        if self.config.get('dex', {}).get('enabled', True):
            task = asyncio.create_task(self._ws_dex_feed())
            self.ws_tasks.append(task)
    
    async def _ws_cex_feed(self):
        """WebSocket feed from CEX."""
        async for price in self.cex_client.stream_prices():
            if not self.running:
                break
            self._update_cache('cex', price)
            await self._check_arbitrage_opportunity(price)
    
    async def _ws_dex_feed(self):
        """WebSocket feed from DEX."""
        async for price in self.dex_client.stream_prices():
            if not self.running:
                break
            self._update_cache('dex', price)
            await self._check_arbitrage_opportunity(price)
    
    def _update_cache(self, source: str, price: Dict[str, float]):
        """Update price cache."""
        for token, value in price.items():
            if token not in self.price_cache:
                self.price_cache[token] = {}
            self.price_cache[token][source] = value
    
    async def _poll_prices(self) -> Dict[str, Dict[str, float]]:
        """Poll prices from all sources."""
        prices = {}
        
        # Get CEX prices
        try:
            cex_prices = await self.cex_client.get_prices()
            prices['cex'] = cex_prices
        except Exception as e:
            self.logger.warning(f"CEX poll failed: {e}")
        
        # Get DEX prices via aggregator
        try:
            dex_prices = await self.dex_client.get_prices()
            prices['dex'] = dex_prices
        except Exception as e:
            self.logger.warning(f"DEX poll failed: {e}")
        
        return prices
    
    async def get_price(self, token: str) -> Dict[str, float]:
        """Get current price for a token."""
        return self.price_cache.get(token, {})
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process price data."""
        token = data.get('token')
        if not token:
            return {'error': 'No token specified'}
        
        return {
            'token': token,
            'prices': await self.get_price(token),
            'timestamp': datetime.now().isoformat()
        }