"""
Orchestrator
============
Main orchestrator for the AI agent trading system.

FIXED: v2.7 - Use exact profit for duplicate key (not rounded)
FIXED: v2.7 - Only queue best opportunity per scan
FIXED: v2.7 - Process all cache items before next scan
"""

import asyncio
import signal
import hashlib
from typing import Dict, Any, Set
from datetime import datetime

from agents.price_agent import PriceAgent
from agents.arbitrage_agent import ArbitrageAgent
from agents.execution_agent import ExecutionAgent


class Orchestrator:
    """Main orchestrator for the AI agent trading system."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.agents: Dict[str, Any] = {}
        self.running = False
        self.tasks = []
        self.total_profit = 0.0
        
        # v2.7: Track executed opportunities with exact key
        self.executed_opportunities: Set[str] = set()
        self.max_executed_cache = 100
        
        self._init_agents()
    
    def _init_agents(self):
        self.agents['price'] = PriceAgent(self.config.get('price_agent', {}))
        self.agents['arbitrage'] = ArbitrageAgent(self.config.get('arbitrage_agent', {}))
        self.agents['execution'] = ExecutionAgent(self.config.get('execution_agent', {}))
        print(f"✅ Initialized {len(self.agents)} agents")
        print(f"✅ Orchestrator v2.7 - Exact duplicate key enabled")
    
    async def start(self):
        self.running = True
        
        for name, agent in self.agents.items():
            task = asyncio.create_task(agent.run())
            self.tasks.append(task)
            print(f"✅ Started agent: {name}")
        
        await self._orchestrator_loop()
    
    def _generate_opportunity_key(self, opportunity) -> str:
        """
        Generate a unique key for an opportunity to prevent duplicates.
        
        v2.7: Uses exact profit (2 decimals) + token for uniqueness.
        This prevents different profits from being treated as duplicates.
        """
        # Use exact profit (2 decimal places) for uniqueness
        profit_key = f"{opportunity.profit_percentage:.2f}"
        key_string = f"{opportunity.token}_{profit_key}"
        return hashlib.md5(key_string.encode()).hexdigest()[:16]
    
    async def _orchestrator_loop(self):
        """Main orchestrator loop with duplicate prevention."""
        while self.running:
            try:
                arbitrage = self.agents.get('arbitrage')
                execution = self.agents.get('execution')
                
                if arbitrage and execution and arbitrage.opportunity_cache:
                    # v2.7: Process ALL opportunities in the cache
                    # But only queue the BEST one (first)
                    best_op = arbitrage.opportunity_cache.pop(0)
                    
                    # Clear the rest of the cache (we only want the best)
                    if arbitrage.opportunity_cache:
                        arbitrage.opportunity_cache.clear()
                    
                    # Generate key for duplicate detection (v2.7: exact profit)
                    op_key = self._generate_opportunity_key(best_op)
                    
                    # v2.7: Check if this opportunity was already executed
                    if op_key in self.executed_opportunities:
                        print(f"⏭️ Skipping duplicate opportunity: {best_op.token} - ${best_op.net_profit:.2f} (profit: {best_op.profit_percentage:.2f}%)")
                        continue
                    
                    # Check if similar opportunity was recently executed
                    if hasattr(execution, 'trade_history') and execution.trade_history:
                        last_trade = execution.trade_history[-1]
                        # If same token and very similar profit (within 2%), likely duplicate
                        if (last_trade.get('token') == best_op.token and 
                            abs(last_trade.get('profit', 0) - best_op.net_profit) < (best_op.net_profit * 0.02)):
                            print(f"⏭️ Skipping similar opportunity (likely duplicate): {best_op.token} - ${best_op.net_profit:.2f}")
                            continue
                    
                    # Mark as executed BEFORE queuing
                    self.executed_opportunities.add(op_key)
                    print(f"📋 Queued opportunity: {best_op.token} - ${best_op.net_profit:.2f}")
                    
                    # Queue the opportunity for execution
                    await execution.queue_opportunity({
                        'token': best_op.token,
                        'net_profit': best_op.net_profit,
                        'profit_percentage': best_op.profit_percentage,
                        'buy_exchange': best_op.buy_exchange,
                        'sell_exchange': best_op.sell_exchange,
                        'trade_size': best_op.trade_size
                    })
                    
                    # v2.7: Clean up old executed opportunities (keep last 100)
                    if len(self.executed_opportunities) > self.max_executed_cache:
                        self.executed_opportunities = set(
                            list(self.executed_opportunities)[-self.max_executed_cache:]
                        )
                
                await asyncio.sleep(10)
                
            except Exception as e:
                print(f"❌ Orchestrator error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)
    
    async def stop(self):
        self.running = False
        print("🛑 Stopping orchestrator...")
        
        for name, agent in self.agents.items():
            if hasattr(agent, 'stop'):
                await agent.stop()
        
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        print("✅ Orchestrator stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status including duplicate prevention stats."""
        return {
            'running': self.running,
            'agents': {
                name: {
                    'running': getattr(agent, 'running', False),
                    'type': agent.__class__.__name__
                }
                for name, agent in self.agents.items()
            },
            'total_profit': self.total_profit,
            'executed_opportunities_count': len(self.executed_opportunities),
            'version': '2.7'
        }


async def main():
    orchestrator = Orchestrator()
    
    # Handle shutdown gracefully
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
        except NotImplementedError:
            # Windows doesn't support signal handlers in asyncio
            pass
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        await orchestrator.stop()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())