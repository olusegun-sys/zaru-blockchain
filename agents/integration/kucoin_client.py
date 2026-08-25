"""
KuCoin API Client for AI Agents
================================
Handles authentication, price fetching, and order execution on KuCoin.

Based on official KuCoin API documentation.
Supports spot trading with HMAC SHA256 authentication.
"""

import os
import hmac
import hashlib
import base64
import time
import json
from typing import Dict, Any, Optional, List
import aiohttp
from dotenv import load_dotenv

load_dotenv()


class KuCoinClient:
    """KuCoin API client for AI trading agents."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        testnet: bool = False
    ):
        self.api_key = api_key or os.getenv("KUCOIN_API_KEY")
        self.api_secret = api_secret or os.getenv("KUCOIN_API_SECRET")
        self.passphrase = passphrase or os.getenv("KUCOIN_API_PASSPHRASE")
        self.testnet = testnet or os.getenv("KUCOIN_TESTNET", "false").lower() == "true"

        # KuCoin uses different endpoints for sandbox vs production
        if self.testnet:
            self.base_url = "https://openapi-sandbox.kucoin.com"
        else:
            self.base_url = "https://api.kucoin.com"

        self.session = None
        self._server_time_offset = 0
        self._last_time_sync = 0

        print(f"🔗 KuCoinClient initialized")
        print(f"   Environment: {'SANDBOX' if self.testnet else 'PRODUCTION'}")
        print(f"   API Key: {self.api_key[:8] if self.api_key else 'NOT SET'}...")
        print(f"   Base URL: {self.base_url}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _sync_server_time(self) -> None:
        """Sync with KuCoin server time."""
        try:
            session = await self._get_session()
            local_time = int(time.time() * 1000)

            async with session.get(
                f"{self.base_url}/api/v1/timestamp",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "200000":
                        server_time = int(data["data"])
                        self._server_time_offset = server_time - local_time
                        self._last_time_sync = time.time()
                        print(f"🕐 Server time synced: offset {self._server_time_offset}ms")
                        return
        except Exception as e:
            print(f"⚠️ Failed to sync server time: {e}")

        self._server_time_offset = 0

    def _get_timestamp(self) -> str:
        """Get timestamp for API requests."""
        local_time = int(time.time() * 1000)
        if self._server_time_offset != 0:
            return str(local_time + self._server_time_offset)
        return str(local_time)

    def _generate_signature(self, method: str, endpoint: str, body: str = "") -> tuple:
        """Generate KuCoin API signature."""
        timestamp = self._get_timestamp()
        # Prehash: timestamp + method + endpoint + body
        prehash = timestamp + method + endpoint + body

        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                prehash.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        # Passphrase is also HMAC-SHA256 encoded in Base64
        passphrase_sig = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                self.passphrase.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        return signature, timestamp, passphrase_sig

    def _get_headers(self, method: str, endpoint: str, body: str = "") -> Dict[str, str]:
        """Generate authenticated headers."""
        signature, timestamp, passphrase = self._generate_signature(method, endpoint, body)

        return {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-PASSPHRASE": passphrase,
            "KC-API-KEY-VERSION": "2",
            "Content-Type": "application/json"
        }

    # ============================================
    # MARKET DATA
    # ============================================

    async def get_ticker(self, symbol: str = "MATIC-USDT") -> Dict[str, Any]:
        """Get current ticker price for a symbol."""
        if not self.api_key or not self.api_secret:
            return {"symbol": symbol, "price": 0.0, "error": "API keys not configured"}

        try:
            session = await self._get_session()

            if time.time() - self._last_time_sync > 300:
                await self._sync_server_time()

            # KuCoin uses dash in symbols (MATIC-USDT)
            symbol_formatted = symbol.replace("USDT", "-USDT") if "USDT" in symbol else symbol

            async with session.get(
                f"{self.base_url}/api/v1/market/orderbook/level1",
                params={"symbol": symbol_formatted},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "200000":
                        ticker = data["data"]
                        return {
                            "symbol": symbol_formatted,
                            "price": float(ticker.get("price", 0)),
                            "bid": float(ticker.get("bestBid", 0)),
                            "ask": float(ticker.get("bestAsk", 0)),
                            "size": float(ticker.get("size", 0))
                        }
                return {"symbol": symbol, "price": 0.0}
        except Exception as e:
            print(f"⚠️ Error fetching {symbol}: {e}")
            return {"symbol": symbol, "price": 0.0}

    async def get_klines(self, symbol: str, interval: str = "1min", limit: int = 100) -> List[Dict]:
        """Get candlestick data."""
        try:
            session = await self._get_session()
            symbol_formatted = symbol.replace("USDT", "-USDT") if "USDT" in symbol else symbol

            async with session.get(
                f"{self.base_url}/api/v1/market/candles",
                params={
                    "symbol": symbol_formatted,
                    "type": interval,
                    "limit": limit
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "200000":
                        return data["data"]
                return []
        except Exception as e:
            print(f"⚠️ Error fetching klines: {e}")
            return []

    # ============================================
    # ORDER MANAGEMENT
    # ============================================

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        test: bool = True
    ) -> Dict[str, Any]:
        """Place a market order."""
        await self._sync_server_time()

        symbol_formatted = symbol.replace("USDT", "-USDT") if "USDT" in symbol else symbol
        endpoint = "/api/v1/orders"
        method = "POST"

        body = json.dumps({
            "symbol": symbol_formatted,
            "side": side.lower(),
            "type": "market",
            "size": str(qty),
            "timeInForce": "GTC"
        })

        try:
            session = await self._get_session()

            async with session.post(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(method, endpoint, body),
                data=body,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()
                if result.get("code") != "200000":
                    print(f"⚠️ Order error: {result.get('msg')}")
                return result
        except Exception as e:
            return {"code": "-1", "msg": str(e)}

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        test: bool = True
    ) -> Dict[str, Any]:
        """Place a limit order."""
        await self._sync_server_time()

        symbol_formatted = symbol.replace("USDT", "-USDT") if "USDT" in symbol else symbol
        endpoint = "/api/v1/orders"
        method = "POST"

        body = json.dumps({
            "symbol": symbol_formatted,
            "side": side.lower(),
            "type": "limit",
            "size": str(qty),
            "price": str(price),
            "timeInForce": "GTC"
        })

        try:
            session = await self._get_session()

            async with session.post(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(method, endpoint, body),
                data=body,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()
                if result.get("code") != "200000":
                    print(f"⚠️ Order error: {result.get('msg')}")
                return result
        except Exception as e:
            return {"code": "-1", "msg": str(e)}

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details."""
        endpoint = f"/api/v1/orders/{order_id}"
        method = "GET"

        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(method, endpoint),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return await resp.json()
        except Exception as e:
            return {"code": "-1", "msg": str(e)}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order."""
        endpoint = f"/api/v1/orders/{order_id}"
        method = "DELETE"

        try:
            session = await self._get_session()

            async with session.delete(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(method, endpoint),
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return await resp.json()
        except Exception as e:
            return {"code": "-1", "msg": str(e)}

    # ============================================
    # ACCOUNT INFO
    # ============================================

    async def get_balance(self, asset: str = "USDT") -> float:
        """Get balance for a specific asset."""
        await self._sync_server_time()

        endpoint = "/api/v1/accounts"
        method = "GET"

        try:
            session = await self._get_session()

            async with session.get(
                f"{self.base_url}{endpoint}",
                headers=self._get_headers(method, endpoint),
                params={"currency": asset},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "200000":
                        accounts = data.get("data", [])
                        for account in accounts:
                            if account.get("currency") == asset:
                                return float(account.get("balance", 0))
                return 0.0
        except Exception as e:
            print(f"⚠️ Error getting balance: {e}")
            return 0.0

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def test_connection(self) -> bool:
        """Test if API keys are valid."""
        if not self.api_key or not self.api_secret:
            print("⚠️ API keys not configured")
            return False

        try:
            await self._sync_server_time()
            price = await self.get_ticker("MATIC-USDT")
            if price.get("price", 0) > 0:
                print(f"✅ KuCoin connection successful! Price: ${price.get('price', 0):.4f}")
                return True
            return False
        except Exception as e:
            print(f"⚠️ Connection test failed: {e}")
            return False