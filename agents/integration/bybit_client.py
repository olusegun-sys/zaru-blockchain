"""
Bybit API Client for AI Agents
================================
Handles authentication, price fetching, and order execution on Bybit.

SUPPORTS:
- Testnet (sandbox) and Mainnet
- HMAC SHA256 authentication
- Spot trading
- Market and Limit orders
"""

import os
import hmac
import hashlib
import time
import json
from typing import Dict, Any, Optional, List
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class BybitClient:
    """Bybit API client for AI trading agents."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True
    ):
        """
        Initialize Bybit client.
        
        Args:
            api_key: Bybit API key (default: from .env)
            api_secret: Bybit API secret (default: from .env)
            testnet: Use testnet/sandbox (default: True)
        """
        self.api_key = api_key or os.getenv("BYBIT_API_KEY")
        self.api_secret = api_secret or os.getenv("BYBIT_API_SECRET")
        self.testnet = testnet or os.getenv("BYBIT_TESTNET", "true").lower() == "true"
        
        # Use testnet URLs for safety
        if self.testnet:
            self.base_url = "https://api-testnet.bybit.com"
            self.ws_url = "wss://stream-testnet.bybit.com/v5/public/spot"
        else:
            self.base_url = "https://api.bybit.com"
            self.ws_url = "wss://stream.bybit.com/v5/public/spot"
        
        self.session = None
        self.recv_window = "5000"
        
        print(f"🔗 BybitClient initialized")
        print(f"   Environment: {'TESTNET' if self.testnet else 'PRODUCTION'}")
        print(f"   API Key: {self.api_key[:8] if self.api_key else 'NOT SET'}...")
        print(f"   Base URL: {self.base_url}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _generate_signature(self, params: Dict[str, Any]) -> tuple:
        """
        Generate HMAC SHA256 signature for Bybit API.
        
        Bybit uses: param_str = timestamp + api_key + recv_window + params_json
        """
        timestamp = str(int(time.time() * 1000))
        
        # Sort params alphabetically
        sorted_params = sorted(params.items())
        param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
        
        # Build the signature string
        sign_str = timestamp + self.api_key + self.recv_window + param_str
        
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    def _get_headers(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Generate headers with authentication."""
        signature, timestamp = self._generate_signature(params)
        
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "Content-Type": "application/json"
        }
    
    # ============================================
    # MARKET DATA
    # ============================================
    
    async def get_ticker(self, symbol: str = "MATICUSDT") -> Dict[str, Any]:
        """
        Get current ticker price for a symbol.
        
        Args:
            symbol: Trading pair (e.g., MATICUSDT, ETHUSDT)
        
        Returns:
            {
                'symbol': 'MATICUSDT',
                'price': 0.5234,
                'bid': 0.5233,
                'ask': 0.5235,
                'volume': 1234567.89
            }
        """
        session = await self._get_session()
        
        async with session.get(
            f"{self.base_url}/v5/market/tickers",
            params={"category": "spot", "symbol": symbol}
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("retCode") == 0:
                    ticker = data["result"]["list"][0]
                    return {
                        "symbol": ticker.get("symbol", symbol),
                        "price": float(ticker.get("lastPrice", 0)),
                        "bid": float(ticker.get("bid1Price", 0)),
                        "ask": float(ticker.get("ask1Price", 0)),
                        "volume": float(ticker.get("volume24h", 0)),
                        "high": float(ticker.get("highPrice24h", 0)),
                        "low": float(ticker.get("lowPrice24h", 0))
                    }
            return {"symbol": symbol, "price": 0.0}
    
    async def get_multiple_tickers(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get prices for multiple symbols."""
        results = {}
        for symbol in symbols:
            results[symbol] = await self.get_ticker(symbol)
        return results
    
    async def get_klines(self, symbol: str = "MATICUSDT", interval: str = "1", limit: int = 100) -> List[Dict]:
        """
        Get candlestick/OHLCV data.
        
        Args:
            symbol: Trading pair
            interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
            limit: Number of candles (max 1000)
        """
        session = await self._get_session()
        
        async with session.get(
            f"{self.base_url}/v5/market/kline",
            params={
                "category": "spot",
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("retCode") == 0:
                    return data["result"]["list"]
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
        """
        Place a market order.
        
        Args:
            symbol: Trading pair
            side: "Buy" or "Sell"
            qty: Quantity in base currency
            test: If True, validate only (no real order)
        
        Returns:
            Order response from Bybit
        """
        params = {
            "category": "spot",
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "GTC"
        }
        
        if test:
            params["test"] = "1"
        
        session = await self._get_session()
        
        async with session.post(
            f"{self.base_url}/v5/order/create",
            headers=self._get_headers(params),
            json=params
        ) as resp:
            return await resp.json()
    
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        test: bool = True
    ) -> Dict[str, Any]:
        """
        Place a limit order.
        
        Args:
            symbol: Trading pair
            side: "Buy" or "Sell"
            qty: Quantity in base currency
            price: Limit price
            test: If True, validate only (no real order)
        """
        params = {
            "category": "spot",
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": "GTC"
        }
        
        if test:
            params["test"] = "1"
        
        session = await self._get_session()
        
        async with session.post(
            f"{self.base_url}/v5/order/create",
            headers=self._get_headers(params),
            json=params
        ) as resp:
            return await resp.json()
    
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details by ID."""
        params = {"category": "spot", "orderId": order_id}
        session = await self._get_session()
        
        async with session.get(
            f"{self.base_url}/v5/order/info",
            headers=self._get_headers(params),
            params=params
        ) as resp:
            return await resp.json()
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order by ID."""
        params = {"category": "spot", "orderId": order_id}
        session = await self._get_session()
        
        async with session.post(
            f"{self.base_url}/v5/order/cancel",
            headers=self._get_headers(params),
            json=params
        ) as resp:
            return await resp.json()
    
    # ============================================
    # ACCOUNT INFO
    # ============================================
    
    async def get_balance(self, asset: str = "USDT") -> float:
        """Get balance for a specific asset."""
        params = {"accountType": "UNIFIED", "coin": asset}
        session = await self._get_session()
        
        async with session.get(
            f"{self.base_url}/v5/account/wallet-balance",
            headers=self._get_headers(params),
            params=params
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("retCode") == 0:
                    for coin in data["result"]["list"][0]["coin"]:
                        if coin["coin"] == asset:
                            return float(coin["walletBalance"])
            return 0.0
    
    async def get_positions(self) -> List[Dict]:
        """Get current positions."""
        params = {"category": "spot"}
        session = await self._get_session()
        
        async with session.get(
            f"{self.base_url}/v5/position/list",
            headers=self._get_headers(params),
            params=params
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("retCode") == 0:
                    return data["result"]["list"]
            return []
    
    # ============================================
    # UTILITY
    # ============================================
    
    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def test_connection(self) -> bool:
        """Test if API keys are valid."""
        try:
            price = await self.get_ticker("MATICUSDT")
            return price.get("price", 0) > 0
        except Exception as e:
            print(f"⚠️ Connection test failed: {e}")
            return False


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_bybit_client(api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True) -> BybitClient:
    """Factory function to create a Bybit client."""
    return BybitClient(api_key=api_key, api_secret=api_secret, testnet=testnet)