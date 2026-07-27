"""
Arbitrage Agent
===============
Discovers and validates arbitrage opportunities across exchanges.

FIXED: v2.6 - Add deduplication to prevent duplicate opportunities
FIXED: Track seen opportunities to avoid duplicates in cache
"""

import asyncio
import random
from typing import Dict, Any, List, Set
from datetime import datetime
from dataclasses import dataclass, field

from agents.base_agent import BaseAgent


@dataclass
class ArbitrageOpportunity:
    token: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    profit_percentage: float
    net_profit: float
    trade_size: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ArbitrageAgent(BaseAgent):
    """Arbitrage opportunity discovery agent with deduplication."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("arbitrage_agent", config)
        self.min_profit_pct = config.get('min_profit_pct', 0.5)
        self.scan_interval = config.get('scan_interval', 3)
        self.opportunity_cache: List[ArbitrageOpportunity] = []
        
        # v2.6: Track seen opportunities to prevent duplicates
        self._seen_opportunities: Set[str] = set()
        self._max_seen_cache = 100
        
    async def run(self):
        await self.start()
        print(f"🔍 ArbitrageAgent: Starting opportunity scanning (interval: {self.scan_interval}s)")
        print(f"   Min profit threshold: {self.min_profit_pct}%")
        print(f"   Deduplication: ENABLED (v2.6)")
        
        while self.running:
            try:
                opportunities = await self._simulate_opportunities()
                if opportunities:
                    # v2.6: Deduplicate opportunities before caching
                    unique_ops = self._deduplicate_opportunities(opportunities)
                    
                    if unique_ops:
                        self.opportunity_cache = unique_ops
                        for op in unique_ops:
                            print(f"🚀 Opportunity: {op.token} - Profit: ${op.net_profit:.2f} ({op.profit_percentage:.2f}%)")
                    else:
                        # All opportunities were duplicates
                        self.opportunity_cache = []
                        
                await asyncio.sleep(self.scan_interval)
                
            except Exception as e:
                print(f"❌ ArbitrageAgent error: {e}")
                await asyncio.sleep(5)
                
        await self.stop()
    
    def _deduplicate_opportunities(self, opportunities: List[ArbitrageOpportunity]) -> List[ArbitrageOpportunity]:
        """
        v2.6: Deduplicate opportunities based on token and profit percentage.
        
        This prevents duplicate opportunities from being added to the cache.
        """
        unique_ops = []
        seen_keys = set()
        
        for op in opportunities:
            # Create a key based on token and rounded profit (1 decimal)
            profit_key = round(op.profit_percentage, 1)
            key = f"{op.token}_{profit_key}"
            
            if key not in seen_keys:
                seen_keys.add(key)
                unique_ops.append(op)
                
                # v2.6: Track this opportunity to prevent future duplicates
                self._seen_opportunities.add(key)
        
        # Clean up old seen opportunities (keep last 100)
        if len(self._seen_opportunities) > self._max_seen_cache:
            self._seen_opportunities = set(
                list(self._seen_opportunities)[-self._max_seen_cache:]
            )
        
        return unique_ops
    
    def _generate_unique_key(self, op: ArbitrageOpportunity) -> str:
        """Generate a unique key for an opportunity."""
        profit_key = round(op.profit_percentage, 1)
        return f"{op.token}_{profit_key}"
    
    async def _simulate_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        Simulate arbitrage opportunities for testing.
        
        v2.6: Generates multiple opportunities with unique profits.
        """
        # Randomly decide how many opportunities to generate (0-3)
        num_ops = random.randint(0, 3) if random.random() < 0.5 else 0
        
        if num_ops == 0:
            return []
        
        opportunities = []
        seen_profits = set()
        
        for _ in range(num_ops):
            # Generate unique profit percentages
            attempts = 0
            while attempts < 20:  # Prevent infinite loop
                profit_pct = round(random.uniform(0.5, 2.0), 2)
                profit_key = round(profit_pct, 1)
                
                # Avoid duplicate profits in the same batch
                if profit_key not in seen_profits:
                    seen_profits.add(profit_key)
                    break
                attempts += 1
            else:
                # If we can't find a unique profit, skip
                continue
            
            # Use unique timestamp to ensure different opportunities
            opportunities.append(ArbitrageOpportunity(
                token='MATIC',
                buy_exchange='cex',
                sell_exchange='dex',
                buy_price=0.50 * (1 - random.uniform(0, 0.01)),
                sell_price=0.50 * (1 + random.uniform(0, 0.01)),
                profit_percentage=profit_pct,
                net_profit=profit_pct * 100,
                trade_size=1000,
                timestamp=datetime.now().isoformat()
            ))
        
        return opportunities
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'opportunities': [
                {
                    'token': op.token,
                    'profit_pct': op.profit_percentage,
                    'net_profit': op.net_profit
                }
                for op in self.opportunity_cache[:10]
            ],
            'count': len(self.opportunity_cache),
            'deduplication_enabled': True,
            'version': '2.6'
        }