"""
ZARU Agent Client
=================
For other agents to call your ZARU trading signals.
"""

import aiohttp
import os
from typing import Dict, Any

API_KEY = os.getenv("ZARU_AGENT_API_KEY", "sk_test_zaru_agent_123")
BASE_URL = os.getenv("ZARU_AGENT_URL", "https://zaru-api.onrender.com/zaru")

async def get_signal(symbol: str = "MATICUSDT") -> Dict[str, Any]:
    """Get a trading signal from ZARU agent."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/agent/signal",
            params={"symbol": symbol},
            headers={"api-key": API_KEY}
        ) as resp:
            return await resp.json()

async def get_balance() -> Dict[str, Any]:
    """Get your balance with the ZARU agent."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/agent/balance",
            headers={"api-key": API_KEY}
        ) as resp:
            return await resp.json()