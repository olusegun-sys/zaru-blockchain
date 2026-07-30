"""
ZARU AI Agent Base Class
========================
Base class for all AI trading agents with common functionality.

Features:
- Layered memory system
- Lifecycle management
- Abstract process method
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class AgentMemory:
    """Layered memory structure for agents."""
    short_term: List[Dict] = field(default_factory=list)
    middle_term: List[Dict] = field(default_factory=list)
    long_term: List[Dict] = field(default_factory=list)
    
    def add_event(self, event: Dict, layer: str = "short_term"):
        """Add an event to the appropriate memory layer."""
        event['timestamp'] = datetime.now().isoformat()
        
        if layer == "short_term":
            self.short_term.append(event)
            if len(self.short_term) > 100:
                self.middle_term.append(self.short_term.pop(0))
        elif layer == "middle_term":
            self.middle_term.append(event)
            if len(self.middle_term) > 500:
                self.long_term.append(self.middle_term.pop(0))
        else:
            self.long_term.append(event)
    
    def get_recent(self, count: int = 10) -> List[Dict]:
        """Get recent short-term memories."""
        return self.short_term[-count:] if self.short_term else []
    
    def clear(self):
        """Clear all memory."""
        self.short_term.clear()
        self.middle_term.clear()
        self.long_term.clear()


class BaseAgent(ABC):
    """
    Base class for all trading agents.
    
    Features:
    - Layered memory for context retention
    - Lifecycle management (start/stop)
    - Abstract process method for subclasses
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.memory = AgentMemory()
        self.running = False
        self._task = None
        
    @abstractmethod
    async def run(self, *args, **kwargs):
        """Main agent execution loop. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input data and return decision. Must be implemented by subclasses."""
        pass
    
    async def start(self):
        """Start the agent."""
        if self.running:
            print(f"⚠️ Agent {self.name} is already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self.run())
        print(f"✅ Agent {self.name} started")
        
    async def stop(self):
        """Stop the agent gracefully."""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print(f"🛑 Agent {self.name} stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            'name': self.name,
            'running': self.running,
            'type': self.__class__.__name__,
            'memory_size': len(self.memory.short_term)
        }