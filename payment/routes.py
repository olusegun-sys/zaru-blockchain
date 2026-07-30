"""
Payment API Routes
==================
REST API endpoints for bank transfers and payments.
"""

import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .bank_transfer import BankTransfer


class TransferRequest(BaseModel):
    bank_code: str = Field(..., description="OPay bank code")
    account_number: str = Field(..., description="Recipient account number")
    amount: float = Field(..., description="Amount in Naira")
    narration: Optional[str] = Field("ZARU Transfer", description="Payment description")


class OpayTransferRequest(BaseModel):
    amount: float = Field(..., description="Amount in Naira")
    account_number: Optional[str] = Field(None, description="Opay account number")
    narration: Optional[str] = Field("ZARU Payment", description="Payment description")


router = APIRouter(prefix="/payment", tags=["Payment"])

bank_transfer = BankTransfer()


@router.post("/transfer")
async def transfer_to_bank(request: TransferRequest) -> Dict[str, Any]:
    try:
        result = await bank_transfer.send_money(
            bank_code=request.bank_code,
            account_number=request.account_number,
            amount=request.amount,
            narration=request.narration
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/opay")
async def credit_opay(request: OpayTransferRequest) -> Dict[str, Any]:
    try:
        result = await bank_transfer.opay.transfer_to_bank(
            amount=request.amount,
            bank_code="999992",
            account_number=request.account_number or os.getenv("OPAY_ACCOUNT_NUMBER"),
            narration=request.narration
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))