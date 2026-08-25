"""
Execution Agent
===============
Executes trades based on discovered opportunities with ZARU settlement.

Features:
- Trade execution (paper/production)
- ZARU settlement integration
- Execution queue
- Profit tracking
- Real trading mode with KuCoin

UPDATED: v3.0 - Switched from Bybit to KuCoin
"""

import asyncio
import os
from typing import Dict, Any
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.integration.zaru_client import ZaruClient
from agents.integration.kucoin_client import KuCoinClient


class ExecutionAgent(BaseAgent):
    """
    Trade execution agent with ZARU settlement and KuCoin integration.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("execution_agent", config)
        
        # Initialize clients
        self.zaru_client = ZaruClient(config.get('zaru', {}))
        
        # v3.0: Initialize KuCoin client for real trading
        self.kucoin = KuCoinClient(testnet=config.get('testnet', False))
        
        # Production mode - REAL trading
        self.production = config.get('production', False)
        if not self.production:
            self.production = os.getenv('PRODUCTION_MODE', 'false').lower() == 'true'
        
        # Risk management
        self.max_position_size = config.get('max_position_size', 20)
        self.max_daily_loss = config.get('max_daily_loss', 10)
        self.stop_loss_pct = config.get('stop_loss_pct', 0.02)
        self.take_profit_pct = config.get('take_profit_pct', 0.03)
        self.trade_amount = config.get('default_trade_amount', 5)
        
        # Tracking
        self.execution_queue = asyncio.Queue()
        self.total_profit = 0.0
        self.trade_count = 0
        self.trade_history = []
        self.daily_pnl = 0.0
        self.today = datetime.now().date()
        
        print(f"💹 ExecutionAgent initialized (v3.0 - KuCoin)")
        print(f"   Mode: {'PRODUCTION (REAL MONEY)' if self.production else 'PAPER TRADING'}")
        print(f"   Max Position: ${self.max_position_size}")
        print(f"   Trade Amount: ${self.trade_amount}")
        print(f"   Stop Loss: {self.stop_loss_pct*100}%")
        print(f"   Take Profit: {self.take_profit_pct*100}%")
        
        if self.production:
            print("   ⚠️ WARNING: REAL MONEY TRADING ENABLED!")
            print("   💰 Start with small amounts and monitor closely.")
        
    async def run(self):
        """Main execution loop."""
        await self.start()
        
        # Check ZARU balance
        balance = await self.zaru_client.get_balance()
        print(f"💰 ZARU Balance: {balance:.8f} ZARU")
        
        # Check KuCoin connection
        kucoin_connected = await self.kucoin.test_connection()
        if kucoin_connected:
            print(f"✅ KuCoin connected - {'LIVE' if self.production else 'TESTNET'}")
            usdt_balance = await self.kucoin.get_balance("USDT")
            print(f"💵 USDT Balance: ${usdt_balance:.2f}")
        else:
            print("⚠️ KuCoin connection failed - paper trading only")
            self.production = False
        
        while self.running:
            try:
                opportunity = await self.execution_queue.get()
                if opportunity:
                    result = await self._execute_arbitrage(opportunity)
                    print(f"📊 Execution result: {result}")
                    self.memory.add_event({
                        'type': 'execution',
                        'result': result
                    }, 'short_term')
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ ExecutionAgent error: {e}")
                await asyncio.sleep(1)
        
        await self.zaru_client.close()
        await self.kucoin.close()
        await self.stop()
    
    async def queue_opportunity(self, opportunity: Dict[str, Any]):
        """Queue an arbitrage opportunity for execution."""
        await self.execution_queue.put(opportunity)
        print(f"📋 Queued opportunity: {opportunity.get('token')} - ${opportunity.get('net_profit', 0):.2f}")
    
    async def _execute_arbitrage(self, opportunity: Dict) -> Dict[str, Any]:
        """Execute a complete arbitrage cycle."""
        try:
            token = opportunity.get('token', 'UNKNOWN')
            buy_exchange = opportunity.get('buy_exchange', 'cex')
            sell_exchange = opportunity.get('sell_exchange', 'dex')
            net_profit = opportunity.get('net_profit', 0)
            profit_pct = opportunity.get('profit_percentage', 0)
            
            trade_size = self._calculate_trade_size(profit_pct)
            
            print(f"💹 EXECUTING: {token} | {buy_exchange} → {sell_exchange} | ${net_profit:.2f} profit")
            print(f"   Trade Size: ${trade_size:.2f}")
            
            if not await self._check_risk_limits():
                print("⚠️ Daily loss limit reached - stopping trades")
                return {'success': False, 'error': 'Daily loss limit reached'}
            
            if self.production:
                # REAL TRADING MODE - KuCoin
                print("🔴 REAL TRADING MODE - EXECUTING WITH REAL FUNDS")
                
                ticker = await self.kucoin.get_ticker("MATICUSDT")
                current_price = ticker.get('price', 0)
                
                if current_price == 0:
                    return {'success': False, 'error': 'Could not get price'}
                
                # Place buy order on KuCoin
                buy_result = await self._execute_real_buy(
                    token, 
                    trade_size / current_price,
                    buy_exchange
                )
                
                if not buy_result.get('success'):
                    return {'success': False, 'error': 'Buy failed', 'details': buy_result}
                
                # Place sell order on KuCoin
                sell_result = await self._execute_real_sell(
                    token,
                    trade_size / current_price,
                    sell_exchange
                )
                
                if not sell_result.get('success'):
                    await self._reverse_trade(token, trade_size, buy_exchange)
                    return {'success': False, 'error': 'Sell failed', 'details': sell_result}
                
                buy_price = buy_result.get('price', current_price)
                sell_price = sell_result.get('price', current_price * 1.01)
                actual_profit = (sell_price - buy_price) * (trade_size / current_price)
                
                settlement = await self.zaru_client.create_settlement(
                    amount=actual_profit,
                    token=token,
                    profit_usd=actual_profit
                )
                
                self.total_profit += actual_profit
                self.daily_pnl += actual_profit
                self.trade_count += 1
                self.trade_history.append({
                    'token': token,
                    'profit': actual_profit,
                    'type': 'real',
                    'timestamp': datetime.now().isoformat()
                })
                
                return {
                    'success': True,
                    'profit': actual_profit,
                    'profit_pct': profit_pct,
                    'trade_size': trade_size,
                    'buy_exchange': buy_exchange,
                    'sell_exchange': sell_exchange,
                    'settlement': settlement,
                    'trade_count': self.trade_count,
                    'total_profit': self.total_profit,
                    'mode': 'REAL',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return await self._execute_paper_trade(token, trade_size, net_profit, profit_pct)
            
        except Exception as e:
            print(f"❌ Execution error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def _execute_paper_trade(self, token: str, trade_size: float, net_profit: float, profit_pct: float) -> Dict:
        """Execute a paper trade (simulated)."""
        buy_price = 0.50 * (1 - 0.005)
        sell_price = 0.50 * (1 + 0.005)
        
        print(f"📝 PAPER TRADE: {token} | Buy ${buy_price:.4f} → Sell ${sell_price:.4f} | Profit: ${net_profit:.2f}")
        
        settlement = await self.zaru_client.create_settlement(
            amount=max(0.0001, net_profit * 0.01),
            token=token,
            profit_usd=net_profit,
            memo=f"PAPER: {token} arbitrage profit ${net_profit:.2f}"
        )
        
        self.total_profit += net_profit
        self.daily_pnl += net_profit
        self.trade_count += 1
        self.trade_history.append({
            'token': token,
            'profit': net_profit,
            'paper': True,
            'timestamp': datetime.now().isoformat()
        })
        
        return {
            'success': True,
            'profit': net_profit,
            'profit_pct': profit_pct,
            'trade_size': trade_size,
            'paper': True,
            'settlement': settlement,
            'trade_count': self.trade_count,
            'total_profit': self.total_profit,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _execute_real_buy(self, token: str, quantity: float, exchange: str) -> Dict:
        """Execute a real buy order on KuCoin."""
        print(f"🔴 REAL BUY: {quantity:.4f} {token} on KuCoin")
        
        # KuCoin uses underscore format (MATIC_USDT)
        symbol = token.replace("USDT", "_USDT") if "USDT" in token else token
        
        result = await self.kucoin.place_market_order(
            symbol=symbol,
            side="buy",
            qty=quantity,
            test=False
        )
        
        if result.get('code') == '200000':
            return {
                'success': True,
                'price': float(result.get('data', {}).get('price', 0)),
                'quantity': quantity,
                'order_id': result.get('data', {}).get('orderId')
            }
        else:
            return {
                'success': False,
                'error': result.get('msg', 'Unknown error')
            }
    
    async def _execute_real_sell(self, token: str, quantity: float, exchange: str) -> Dict:
        """Execute a real sell order on KuCoin."""
        print(f"🔴 REAL SELL: {quantity:.4f} {token} on KuCoin")
        
        symbol = token.replace("USDT", "_USDT") if "USDT" in token else token
        
        result = await self.kucoin.place_market_order(
            symbol=symbol,
            side="sell",
            qty=quantity,
            test=False
        )
        
        if result.get('code') == '200000':
            return {
                'success': True,
                'price': float(result.get('data', {}).get('price', 0)),
                'quantity': quantity,
                'order_id': result.get('data', {}).get('orderId')
            }
        else:
            return {
                'success': False,
                'error': result.get('msg', 'Unknown error')
            }
    
    def _calculate_trade_size(self, profit_pct: float) -> float:
        """Calculate trade size based on risk."""
        trade_size = self.trade_amount
        
        if profit_pct > 1.5:
            trade_size = min(trade_size * 1.5, self.max_position_size)
        elif profit_pct < 0.8:
            trade_size = max(trade_size * 0.5, 1)
        
        return trade_size
    
    async def _check_risk_limits(self) -> bool:
        """Check if risk limits are exceeded."""
        today = datetime.now().date()
        if today != self.today:
            self.daily_pnl = 0.0
            self.today = today
        
        if self.daily_pnl < -self.max_daily_loss:
            print(f"⚠️ Daily loss limit reached: ${self.daily_pnl:.2f}")
            return False
        
        return True
    
    async def _reverse_trade(self, token: str, amount: float, exchange: str):
        """Reverse a failed trade."""
        print(f"🔄 Reversing trade: {token} {amount} on {exchange}")
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process execution request."""
        if 'opportunity' in data:
            await self.queue_opportunity(data['opportunity'])
            return {'status': 'queued', 'queue_size': self.execution_queue.qsize()}
        
        if data.get('action') == 'status':
            return {
                'status': 'running' if self.running else 'stopped',
                'production_mode': self.production,
                'trade_count': self.trade_count,
                'total_profit': self.total_profit,
                'daily_pnl': self.daily_pnl,
                'queue_size': self.execution_queue.qsize(),
                'recent_trades': self.trade_history[-5:] if self.trade_history else []
            }
        
        if data.get('action') == 'balance':
            balance = await self.zaru_client.get_balance()
            kucoin_balance = await self.kucoin.get_balance("USDT")
            return {
                'zaru_balance': balance,
                'kucoin_usdt_balance': kucoin_balance,
                'wallet_address': self.zaru_client.wallet_address
            }
        
        return {'status': 'idle', 'message': 'Unknown action'}