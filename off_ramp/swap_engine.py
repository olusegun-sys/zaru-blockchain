"""
ZARU to USDT Swap Engine
========================
Handles conversion of ZARU to USDT for off-ramp.
"""

import json
import time
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
from datetime import datetime

from wallet import wallet


class SwapEngine:
    """Handles ZARU to USDT conversion."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.usdt_address = self.config.get('usdt_address', 'ZARU_USDT_WALLET_ADDRESS')
        self.exchange_rate_file = Path("data/exchange_rates.json")
        self.default_rate = 0.0001

        self._load_rate_cache()
        print(f"💱 SwapEngine initialized")
        print(f"   Rate: 1 ZARU = {self.current_rate:.6f} USDT")

    def _load_rate_cache(self):
        try:
            if self.exchange_rate_file.exists():
                with open(self.exchange_rate_file) as f:
                    data = json.load(f)
                    self.current_rate = data.get('rate', self.default_rate)
                    return
        except:
            pass
        self.current_rate = self.default_rate

    async def get_exchange_rate(self) -> float:
        return self.current_rate

    async def set_exchange_rate(self, rate: float) -> None:
        self.current_rate = rate
        print(f"✅ Exchange rate updated: 1 ZARU = {rate:.6f} USDT")

    async def swap_zaru_to_usdt(self, zaru_amount: int, from_address: str) -> Tuple[bool, str, Optional[Dict]]:
        try:
            rate = await self.get_exchange_rate()
            usdt_amount = zaru_amount * rate
            print(f"💱 Swapping {zaru_amount} ZARU → {usdt_amount:.6f} USDT")

            success, message, tx = wallet.send(
                to_address=self.usdt_address,
                amount=zaru_amount,
                from_address=from_address,
                fee=0,
                memo=f"Swap: {zaru_amount} ZARU to USDT"
            )

            if not success:
                return False, f"Swap failed: {message}", None

            return True, "Swap successful", {
                'zaru_amount': zaru_amount,
                'usdt_amount': usdt_amount,
                'rate': rate,
                'tx_id': tx.tx_id if tx else None,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return False, f"Swap error: {e}", None