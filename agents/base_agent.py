"""
ZARU AI Agent Base Class
========================
Base class for all AI trading agents with common functionality.

Inspired by FinMem layered memory architecture [citation:1] and 
TradingGroup multi-agent collaboration patterns [citation:5].
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

from agents.utils.logger import get_logger
from agents.utils.metrics import MetricsCollector


@dataclass
class AgentMemory:
    """Layered memory structure for agents [citation:1][citation:9]."""
    short_term: List[Dict] = field(default_factory=list)   # Recent events (last 24h)
    middle_term: List[Dict] = field(default_factory=list)  # Weekly trends
    long_term: List[Dict] = field(default_factory=list)    # Historical patterns
    
    def add_event(self, event: Dict, layer: str = "short_term"):
        """Add an event to the appropriate memory layer."""
        event['timestamp'] = datetime.now().isoformat()
        if layer == "short_term":
            self.short_term.append(event)
            if len(self.short_term) > 100:
                # Move to middle term
                self.middle_term.append(self.short_term.pop(0))
        elif layer == "middle_term":
            self.middle_term.append(event)
            if len(self.middle_term) > 500:
                self.long_term.append(self.middle_term.pop(0))
        else:
            self.long_term.append(event)


class BaseAgent(ABC):
    """
    Base class for all trading agents.
    
    Features:
    - Layered memory for context retention [citation:1]
    - Self-reflection for performance improvement [citation:5]
    - Structured logging and metrics
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.memory = AgentMemory()
        self.logger = get_logger(f"agent.{name}")
        self.metrics = MetricsCollector()
        self.running = False
        
    @abstractmethod
    async def run(self, *args, **kwargs):
        """Main agent execution loop."""
        pass
    
    @abstractmethod
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input data and return decision."""
        pass
    
    def reflect(self) -> Dict[str, Any]:
        """
        Self-reflection mechanism to improve decision making [citation:5].
        
        Reviews past decisions, identifies patterns, and suggests improvements.
        """
        recent_events = self.memory.short_term[-10:] if self.memory.short_term else []
        
        reflection = {
            "agent": self.name,
            "timestamp": datetime.now().isoformat(),
            "success_rate": self._calculate_success_rate(),
            "insights": self._extract_insights(recent_events),
            "suggestions": self._generate_suggestions()
        }
        
        self.logger.info(f"Reflection: {reflection}")
        return reflection
    
    def _calculate_success_rate(self) -> float:
        """Calculate success rate from memory."""
        # Implementation based on agent type
        return 0.0
    
    def _extract_insights(self, events: List[Dict]) -> List[str]:
        """Extract insights from recent events."""
        return []
    
    def _generate_suggestions(self) -> List[str]:
        """Generate improvement suggestions."""
        return []
    
    async def start(self):
        """Start the agent."""
        self.running = True
        self.logger.info(f"Agent {self.name} started")
        
    async def stop(self):
        """Stop the agent."""
        self.running = False
        self.logger.info(f"Agent {self.name} stopped")