"""
Off-Ramp API Routes
===================
REST API endpoints for ZARU off-ramp functionality.

Endpoints:
- GET /offramp/rate - Get exchange rate
- POST /offramp/swap - Swap ZARU to USDT
- POST /offramp/withdraw - Withdraw to bank
- POST /offramp/webhook - Monica Cash webhook
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from datetime import datetime

from .monica_client import MonicaClient
from .swap_engine import SwapEngine


# Pydantic models
class SwapRequest(BaseModel):
    zaru_amount: int = Field(..., description="Amount in ZARU satoshis")
    from_address: str = Field(..., description="ZARU address to swap from")


class WithdrawRequest(BaseModel):
    usdt_amount: float = Field(..., description="Amount in USDT")
    bank_account: Optional[str] = Field(None, description="Bank account number")


class SetRateRequest(BaseModel):
    rate: float = Field(..., description="ZARU to USDT rate")


# Router
router = APIRouter(prefix="/offramp", tags=["Off-Ramp"])

# Initialize clients
monica_client = MonicaClient()
swap_engine = SwapEngine()


@router.get("/rate")
async def get_exchange_rate() -> Dict[str, Any]:
    """Get current ZARU/USDT exchange rate."""
    try:
        rate = await swap_engine.get_exchange_rate()
        return {
            "rate": rate,
            "zaru_to_usdt": f"1 ZARU = {rate:.6f} USDT",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rate")
async def set_exchange_rate(request: SetRateRequest) -> Dict[str, Any]:
    """Manually set exchange rate."""
    try:
        await swap_engine.set_exchange_rate(request.rate)
        return {"success": True, "rate": request.rate}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swap")
async def swap_zaru_to_usdt(request: SwapRequest) -> Dict[str, Any]:
    """Swap ZARU to USDT."""
    try:
        success, message, result = await swap_engine.swap_zaru_to_usdt(
            zaru_amount=request.zaru_amount,
            from_address=request.from_address
        )

        if not success:
            raise HTTPException(status_code=400, detail=message)

        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/withdraw")
async def withdraw_to_bank(request: WithdrawRequest) -> Dict[str, Any]:
    """Withdraw USDT to Nigerian bank account."""
    try:
        result = await monica_client.withdraw_to_bank(
            amount=request.usdt_amount,
            bank_account=request.bank_account
        )

        if result.get('error'):
            raise HTTPException(status_code=400, detail=result['error'])

        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def webhook(request: Request) -> Dict[str, Any]:
    """Handle Monica Cash webhook."""
    try:
        payload = await request.json()
        result = await monica_client.handle_webhook(payload)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/deposit-address")
async def get_deposit_address() -> Dict[str, Any]:
    """Get USDT deposit address."""
    try:
        result = await monica_client.get_deposit_address()
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))