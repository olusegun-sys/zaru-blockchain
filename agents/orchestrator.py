"""
Orchestrator
============
Main orchestrator for the AI agent trading system.

Manages all agents, coordinates their activities, and handles
state persistence and risk management.
"""

import asyncio
import signal
from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.price_agent import PriceAgent
from agents.arbitrage_agent import ArbitrageAgent
from agents.execution_agent import ExecutionAgent
from agents.sentiment_agent import SentimentAgent
from agents.strategy_agent import StrategyAgent
from agents.rebalance_agent import RebalanceAgent

from agents.utils.logger import get_logger
from agents.utils.metrics import MetricsCollector
from agents.utils.config import load_config


class Orchestrator:
    """
    Main orchestrator for the AI agent trading system.
    
    Features:
    - Agent lifecycle management
    - Inter-agent communication
    - Risk management
    - State persistence
    - Metrics collection
    """
    
    def __init__(self, config_path: str = "config/default.yaml"):
        self.config = load_config(config_path)
        self.logger = get_logger("orchestrator")
        self.metrics = MetricsCollector()
        
        # Initialize agents
        self.agents: Dict[str, any] = {}
        self._init_agents()
        
        self.running = False
        self.tasks: List[asyncio.Task] = []
        
    def _init_agents(self):
        """Initialize all trading agents."""
        self.agents['price'] = PriceAgent(self.config.get('price_agent', {}))
        self.agents['arbitrage'] = ArbitrageAgent(self.config.get('arbitrage_agent', {}))
        self.agents['execution'] = ExecutionAgent(self.config.get('execution_agent', {}))
        
        if self.config.get('sentiment_agent', {}).get('enabled', False):
            self.agents['sentiment'] = SentimentAgent(self.config.get('sentiment_agent', {}))
        
        if self.config.get('strategy_agent', {}).get('enabled', False):
            self.agents['strategy'] = StrategyAgent(self.config.get('strategy_agent', {}))
        
        if self.config.get('rebalance_agent', {}).get('enabled', False):
            self.agents['rebalance'] = RebalanceAgent(self.config.get('rebalance_agent', {}))
        
        self.logger.info(f"Initialized {len(self.agents)} agents")
    
    async def start(self):
        """Start all agents and the orchestrator."""
        self.running = True
        
        # Start each agent
        for name, agent in self.agents.items():
            task = asyncio.create_task(agent.run())
            self.tasks.append(task)
            self.logger.info(f"Started agent: {name}")
        
        # Start orchestrator loop
        await self._orchestrator_loop()
    
    async def _orchestrator_loop(self):
        """Main orchestrator loop."""
        while self.running:
            try:
                # Check agent health
                for name, agent in self.agents.items():
                    if hasattr(agent, 'running') and not agent.running:
                        self.logger.warning(f"Agent {name} is not running, restarting...")
                        # Attempt restart
                        task = asyncio.create_task(agent.run())
                        self.tasks.append(task)
                
                # Collect metrics
                metrics = self._collect_metrics()
                self.logger.info(f"System metrics: {metrics}")
                
                # Risk check
                risk_status = await self._risk_check()
                if risk_status.get('should_stop'):
                    self.logger.warning(f"Risk limit reached: {risk_status}")
                    await self.stop()
                    break
                
                await asyncio.sleep(self.config.get('orchestrator_interval', 10))
                
            except Exception as e:
                self.logger.error(f"Orchestrator error: {e}")
                await asyncio.sleep(5)
    
    def _collect_metrics(self) -> Dict[str, Any]:
        """Collect system metrics."""
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'agents_running': sum(1 for a in self.agents.values() if getattr(a, 'running', False)),
            'opportunities': len(getattr(self.agents.get('arbitrage', None), 'opportunity_cache', [])),
            'execution_queue': self.agents.get('execution', None).execution_queue.qsize() if 'execution' in self.agents else 0
        }
        return metrics
    
    async def _risk_check(self) -> Dict[str, Any]:
        """Perform risk checks."""
        risk_config = self.config.get('risk', {})
        result = {'should_stop': False}
        
        # Check daily loss limit
        daily_loss = self.metrics.get_daily_pnl()
        if daily_loss < risk_config.get('daily_loss_limit', -1000):
            result['should_stop'] = True
            result['reason'] = f"Daily loss limit reached: ${daily_loss:.2f}"
        
        # Check position size
        total_exposure = self.metrics.get_total_exposure()
        if total_exposure > risk_config.get('max_exposure', 10000):
            result['should_stop'] = True
            result['reason'] = f"Max exposure exceeded: ${total_exposure:.2f}"
        
        return result
    
    async def stop(self):
        """Stop all agents and the orchestrator."""
        self.running = False
        self.logger.info("Stopping orchestrator...")
        
        # Stop all agents
        for name, agent in self.agents.items():
            if hasattr(agent, 'stop'):
                await agent.stop()
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Cleanup
        if 'execution' in self.agents:
            await self.agents['execution'].zaru_client.close()
        
        self.logger.info("Orchestrator stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get system status."""
        return {
            'running': self.running,
            'agents': {
                name: {
                    'running': getattr(agent, 'running', False),
                    'type': agent.__class__.__name__
                }
                for name, agent in self.agents.items()
            },
            'metrics': self._collect_metrics()
        }


async def main():
    """Entry point for the trading system."""
    orchestrator = Orchestrator()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())