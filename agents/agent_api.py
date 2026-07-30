"""
ZARU Agent-to-Agent API
=======================
Sell trading signals to other AI agents.

This is a lightweight alternative to OpenStall that uses your existing FastAPI infrastructure.
"""

import os
import json
import time
import hmac
import hashlib
import secrets
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel, Field
from datetime import datetime

from agents.price_agent import PriceAgent
from agents.integration.bybit_client import BybitClient

# ============================================
# PYDANTIC MODELS
# ============================================

class SignalRequest(BaseModel):
    """Request for a trading signal."""
    symbol: str = Field("MATICUSDT", description="Trading pair")
    action: str = Field("arbitrage", description="Signal type: arbitrage, price, or both")
    api_key: str = Field(..., description="API key for authentication")

class SignalResponse(BaseModel):
    """Trading signal response."""
    success: bool
    symbol: str
    price: float
    bid: float
    ask: float
    spread: float
    recommendation: str
    timestamp: str

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(title="ZARU Agent API")

# API keys storage (in production, use database)
API_KEYS = {
    "agent_1": {"key": "sk_test_zaru_agent_123", "balance": 100, "credits": 1000},
    "agent_2": {"key": "sk_test_zaru_agent_456", "balance": 50, "credits": 500},
}

def verify_api_key(api_key: str) -> bool:
    """Verify if the API key is valid."""
    for agent_id, data in API_KEYS.items():
        if data["key"] == api_key:
            return True
    return False

def deduct_credits(api_key: str, cost: float = 0.005) -> bool:
    """Deduct credits from an agent's balance."""
    for agent_id, data in API_KEYS.items():
        if data["key"] == api_key:
            if data["credits"] >= cost:
                data["credits"] -= cost
                return True
            return False
    return False

# ============================================
# ENDPOINTS
# ============================================

@app.get("/agent/signal")
async def get_signal(
    symbol: str = "MATICUSDT",
    api_key: str = Header(...)
) -> Dict[str, Any]:
    """
    Get a trading signal.

    This is what other agents call to get your ZARU trading signals.
    """
    # 1. Verify API key
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # 2. Deduct credits
    if not deduct_credits(api_key, 0.005):
        raise HTTPException(status_code=402, detail="Insufficient credits")

    # 3. Get real price data
    bybit = BybitClient()
    ticker = await bybit.get_ticker(symbol)
    await bybit.close()

    price = ticker.get("price", 0)
    bid = ticker.get("bid", price)
    ask = ticker.get("ask", price)

    # 4. Calculate spread and recommendation
    spread = ((ask - bid) / bid) * 100 if bid > 0 else 0
    recommendation = "BUY" if spread > 0.3 else "NEUTRAL"

    return {
        "success": True,
        "symbol": symbol,
        "price": price,
        "bid": bid,
        "ask": ask,
        "spread": round(spread, 2),
        "recommendation": recommendation,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/agent/status")
async def get_status() -> Dict[str, Any]:
    """Get the status of the ZARU agent."""
    return {
        "agent": "ZARU_Trading_Agent",
        "status": "active",
        "version": "2.9.0",
        "capabilities": ["trading_signal", "arbitrage_detection", "price_feed"],
        "price": 0.005,
        "credits_available": sum(data["credits"] for data in API_KEYS.values())
    }

@app.get("/agent/balance")
async def get_balance(api_key: str = Header(...)) -> Dict[str, Any]:
    """Get an agent's balance."""
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    for agent_id, data in API_KEYS.items():
        if data["key"] == api_key:
            return {"credits": data["credits"], "balance": data["balance"]}

    return {"credits": 0, "balance": 0}