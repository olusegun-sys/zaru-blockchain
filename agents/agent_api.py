"""
ZARU Agent-to-Agent API (v2.0 - Enhanced)
=========================================
Sell trading signals to other AI agents with enhanced features.

Features:
- Multiple trading pairs (MATIC, ETH, BTC, SOL)
- Confidence scoring
- Execution advice (buy/sell/hold)
- Historical signal tracking
- Usage analytics
"""

import os
import json
import time
import hashlib
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Request, Header, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from agents.price_agent import PriceAgent
from agents.integration.bybit_client import BybitClient

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(title="ZARU Agent API v2.0")

# ============================================
# API KEYS STORAGE
# ============================================

API_KEYS = {
    "agent_1": {"key": "sk_test_zaru_agent_123", "balance": 100, "credits": 1500, "usage": 0},
    "agent_2": {"key": "sk_live_zaru_agent_456", "balance": 100, "credits": 10000, "usage": 0},
}

# ============================================
# SIGNAL HISTORY (In-memory cache)
# ============================================

signal_history: Dict[str, List[Dict]] = {}
MAX_HISTORY = 100


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
                data["usage"] += 1
                return True
            return False
    return False


def get_agent_data(api_key: str) -> Optional[Dict]:
    """Get agent data by API key."""
    for agent_id, data in API_KEYS.items():
        if data["key"] == api_key:
            return data
    return None


# ============================================
# ENHANCED ENDPOINTS
# ============================================

@app.get("/agent/signal")
async def get_signal(
    symbol: str = Query("MATICUSDT", description="Trading pair (MATICUSDT, ETHUSDT, BTCUSDT, SOLUSDT)"),
    api_key: str = Header(...)
) -> Dict[str, Any]:
    """
    Get an enhanced trading signal.
    
    Returns:
    - Price data (bid/ask)
    - Recommendation (BUY/SELL/NEUTRAL)
    - Confidence score (0-100)
    - Execution advice
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
    
    # 4. Calculate spread
    spread = ((ask - bid) / bid) * 100 if bid > 0 else 0
    
    # 5. ENHANCED: Generate recommendation with confidence
    if spread > 0.5:
        recommendation = "BUY"
        confidence = min(100, abs(spread) * 20)
    elif spread < -0.5:
        recommendation = "SELL"
        confidence = min(100, abs(spread) * 20)
    else:
        recommendation = "NEUTRAL"
        confidence = max(0, 100 - (abs(spread) * 50))
    
    # 6. ENHANCED: Execution advice
    if recommendation == "BUY":
        target = price * 1.005
        stop = price * 0.995
        advice = f"Buy at {price:.4f}, target {target:.4f}, stop {stop:.4f}"
        risk_reward = f"1:{((target - price) / (price - stop)):.1f}"
    elif recommendation == "SELL":
        target = price * 0.995
        stop = price * 1.005
        advice = f"Sell at {price:.4f}, target {target:.4f}, stop {stop:.4f}"
        risk_reward = f"1:{((price - target) / (stop - price)):.1f}"
    else:
        advice = "Wait for clearer signal. Spread too tight."
        risk_reward = "N/A"
    
    # 7. Create response
    response = {
        "success": True,
        "symbol": symbol,
        "price": price,
        "bid": bid,
        "ask": ask,
        "spread": round(spread, 2),
        "recommendation": recommendation,
        "confidence": round(confidence, 1),
        "advice": advice,
        "risk_reward": risk_reward,
        "timestamp": datetime.now().isoformat()
    }
    
    # 8. Store history
    if symbol not in signal_history:
        signal_history[symbol] = []
    signal_history[symbol].append(response)
    if len(signal_history[symbol]) > MAX_HISTORY:
        signal_history[symbol] = signal_history[symbol][-MAX_HISTORY:]
    
    return response


@app.get("/agent/history")
async def get_history(
    symbol: str = Query("MATICUSDT", description="Trading pair"),
    limit: int = Query(10, description="Number of signals to return", ge=1, le=100),
    api_key: str = Header(...)
) -> Dict[str, Any]:
    """Get historical signals for a symbol."""
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    history = signal_history.get(symbol, [])
    return {
        "success": True,
        "symbol": symbol,
        "count": len(history[-limit:]),
        "history": history[-limit:],
        "timestamp": datetime.now().isoformat()
    }


@app.get("/agent/multi")
async def get_multi_signal(
    symbols: str = Query("MATICUSDT,ETHUSDT", description="Comma-separated symbols"),
    api_key: str = Header(...)
) -> Dict[str, Any]:
    """Get signals for multiple symbols in one call."""
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Deduct credits (1 call = 0.005 credits)
    if not deduct_credits(api_key, 0.005):
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    symbol_list = [s.strip() for s in symbols.split(",")]
    results = {}
    
    for symbol in symbol_list:
        bybit = BybitClient()
        ticker = await bybit.get_ticker(symbol)
        await bybit.close()
        
        price = ticker.get("price", 0)
        bid = ticker.get("bid", price)
        ask = ticker.get("ask", price)
        spread = ((ask - bid) / bid) * 100 if bid > 0 else 0
        
        if spread > 0.5:
            rec = "BUY"
        elif spread < -0.5:
            rec = "SELL"
        else:
            rec = "NEUTRAL"
        
        results[symbol] = {
            "price": price,
            "bid": bid,
            "ask": ask,
            "spread": round(spread, 2),
            "recommendation": rec,
            "confidence": round(min(100, abs(spread) * 20), 1)
        }
    
    return {
        "success": True,
        "symbols": symbol_list,
        "signals": results,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/agent/status")
async def get_status() -> Dict[str, Any]:
    """Get the status of the ZARU agent."""
    total_credits = sum(data["credits"] for data in API_KEYS.values())
    total_usage = sum(data["usage"] for data in API_KEYS.values())
    
    return {
        "agent": "ZARU_Trading_Agent",
        "status": "active",
        "version": "2.0.0",
        "capabilities": ["trading_signal", "multi_symbol", "history", "arbitrage_detection"],
        "price": 0.005,
        "credits_available": total_credits,
        "total_usage": total_usage,
        "supported_symbols": ["MATICUSDT", "ETHUSDT", "BTCUSDT", "SOLUSDT"],
        "history_count": sum(len(h) for h in signal_history.values()),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/agent/balance")
async def get_balance(api_key: str = Header(...)) -> Dict[str, Any]:
    """Get an agent's balance."""
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    data = get_agent_data(api_key)
    if data:
        return {
            "credits": data["credits"],
            "balance": data["balance"],
            "usage": data["usage"]
        }
    
    return {"credits": 0, "balance": 0, "usage": 0}


@app.post("/agent/credits")
async def add_credits(
    api_key: str = Header(...),
    amount: int = Query(..., description="Number of credits to add")
) -> Dict[str, Any]:
    """Add credits to an agent (for testing/development)."""
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    for agent_id, data in API_KEYS.items():
        if data["key"] == api_key:
            data["credits"] += amount
            return {
                "success": True,
                "credits": data["credits"],
                "added": amount,
                "timestamp": datetime.now().isoformat()
            }
    
    return {"success": False, "error": "Agent not found"}


# ============================================
# HEALTH CHECK
# ============================================

@app.get("/agent/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for OpenStall worker."""
    return {
        "status": "healthy",
        "agent": "ZARU_Trading_Agent",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }


# ============================================
# WEBHOOK FOR OPENSTALL (v2.0)
# ============================================

@app.post("/agent/webhook")
async def webhook_handler(request: Request) -> Dict[str, Any]:
    """
    Handle OpenStall webhook requests.
    
    OpenStall will POST to this endpoint when a task is assigned.
    """
    try:
        payload = await request.json()
        
        # Extract task details
        task_id = payload.get("task_id")
        input_data = payload.get("input", {})
        symbol = input_data.get("symbol", "MATICUSDT")
        
        # Get API key from the request
        api_key = request.headers.get("api-key")
        
        if not api_key:
            return {"error": "Missing API key"}
        
        # Verify API key
        if not verify_api_key(api_key):
            return {"error": "Invalid API key"}
        
        # Get signal
        bybit = BybitClient()
        ticker = await bybit.get_ticker(symbol)
        await bybit.close()
        
        price = ticker.get("price", 0)
        bid = ticker.get("bid", price)
        ask = ticker.get("ask", price)
        spread = ((ask - bid) / bid) * 100 if bid > 0 else 0
        
        if spread > 0.5:
            recommendation = "BUY"
        elif spread < -0.5:
            recommendation = "SELL"
        else:
            recommendation = "NEUTRAL"
        
        # Return response to OpenStall
        return {
            "success": True,
            "task_id": task_id,
            "output": {
                "symbol": symbol,
                "price": price,
                "recommendation": recommendation,
                "spread": round(spread, 2),
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}