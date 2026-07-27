"""
Orchestrator
============
Main orchestrator for the AI agent trading system.

FIXED: v2.8 - Use rounded key for duplicate detection (1 decimal)
FIXED: v2.8 - Prevent duplicate queuing with in-flight tracking
FIXED: v2.8 - Only process one opportunity per scan
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
        
        # v2.8: Track executed opportunities with rounded key
        self.executed_opportunities: Set[str] = set()
        self.executed_timestamps: Set[str] = set()  # Track exact opportunities
        self.max_executed_cache = 200
        
        # v2.8: Track in-flight opportunities to prevent duplicate queuing
        self.in_flight: Set[str] = set()
        
        self._init_agents()
    
    def _init_agents(self):
        self.agents['price'] = PriceAgent(self.config.get('price_agent', {}))
        self.agents['arbitrage'] = ArbitrageAgent(self.config.get('arbitrage_agent', {}))
        self.agents['execution'] = ExecutionAgent(self.config.get('execution_agent', {}))
        print(f"✅ Initialized {len(self.agents)} agents")
        print(f"✅ Orchestrator v2.8 - Enhanced duplicate prevention enabled")
    
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
        
        v2.8: Uses rounded profit (1 decimal) for grouping.
        """
        profit_key = round(opportunity.profit_percentage, 1)
        key_string = f"{opportunity.token}_{profit_key}"
        return hashlib.md5(key_string.encode()).hexdigest()[:16]
    
    def _generate_exact_key(self, opportunity) -> str:
        """
        Generate an exact key for precise duplicate detection.
        
        v2.8: Uses exact profit + timestamp for uniqueness.
        """
        key_string = f"{opportunity.token}_{opportunity.profit_percentage:.3f}_{opportunity.timestamp}"
        return hashlib.md5(key_string.encode()).hexdigest()[:16]
    
    async def _orchestrator_loop(self):
        """Main orchestrator loop with enhanced duplicate prevention."""
        while self.running:
            try:
                arbitrage = self.agents.get('arbitrage')
                execution = self.agents.get('execution')
                
                if arbitrage and execution and arbitrage.opportunity_cache:
                    # v2.8: Only process ONE opportunity per scan
                    best_op = arbitrage.opportunity_cache.pop(0)
                    
                    # Clear the rest (we only want the best)
                    if arbitrage.opportunity_cache:
                        arbitrage.opportunity_cache.clear()
                    
                    # Generate keys for duplicate detection
                    op_key = self._generate_opportunity_key(best_op)
                    exact_key = self._generate_exact_key(best_op)
                    
                    # v2.8: Check if this exact opportunity is already in-flight
                    if exact_key in self.in_flight:
                        print(f"⏭️ Opportunity already in-flight: {best_op.token} - ${best_op.net_profit:.2f}")
                        continue
                    
                    # Check if a similar opportunity was already executed
                    if op_key in self.executed_opportunities:
                        print(f"⏭️ Skipping duplicate opportunity: {best_op.token} - ${best_op.net_profit:.2f} (profit: {best_op.profit_percentage:.1f}%)")
                        continue
                    
                    # Check if a very similar opportunity was recently executed
                    if hasattr(execution, 'trade_history') and execution.trade_history:
                        last_trade = execution.trade_history[-1]
                        if (last_trade.get('token') == best_op.token and 
                            abs(last_trade.get('profit', 0) - best_op.net_profit) < (best_op.net_profit * 0.01)):
                            print(f"⏭️ Skipping similar opportunity (likely duplicate): {best_op.token} - ${best_op.net_profit:.2f}")
                            continue
                    
                    # v2.8: Mark as in-flight BEFORE queuing
                    self.in_flight.add(exact_key)
                    
                    # Mark as executed
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
                    
                    # v2.8: Remove from in-flight after a short delay
                    async def remove_in_flight():
                        await asyncio.sleep(15)  # Wait for execution to complete
                        self.in_flight.discard(exact_key)
                    
                    asyncio.create_task(remove_in_flight())
                    
                    # v2.8: Clean up old executed opportunities
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
            'in_flight_count': len(self.in_flight),
            'version': '2.8'
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