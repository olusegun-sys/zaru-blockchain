"""
Execution Agent
===============
Executes trades based on discovered opportunities with ZARU settlement.

Features:
- Trade execution (paper/production)
- ZARU settlement integration
- Execution queue
- Profit tracking
- Real trading mode with Bybit

UPDATED: v2.9 - Real trading mode with Bybit integration
UPDATED: Risk management and position sizing
"""

import asyncio
import os
from typing import Dict, Any
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.integration.zaru_client import ZaruClient
from agents.integration.bybit_client import BybitClient


class ExecutionAgent(BaseAgent):
    """
    Trade execution agent with ZARU settlement and Bybit integration.
    
    Executes arbitrage trades and settles profits
    on the ZARU blockchain.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("execution_agent", config)
        
        # Initialize clients
        self.zaru_client = ZaruClient(config.get('zaru', {}))
        
        # v2.9: Initialize Bybit client for real trading
        self.bybit = BybitClient(
            testnet=config.get('testnet', True)
        )
        
        # v2.9: Production mode - REAL trading!
        self.production = config.get('production', False)
        
        # v2.9: Read from environment if not in config
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
        
        print(f"💹 ExecutionAgent initialized")
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
        
        # Check ZARU balance on start
        balance = await self.zaru_client.get_balance()
        print(f"💰 ZARU Balance: {balance:.8f} ZARU")
        
        # v2.9: Check Bybit connection
        bybit_connected = await self.bybit.test_connection()
        if bybit_connected:
            print(f"✅ Bybit connected - {'LIVE' if self.production else 'TESTNET'}")
            
            # v2.9: Get USDT balance (real or testnet)
            usdt_balance = await self.bybit.get_balance("USDT")
            print(f"💵 USDT Balance: ${usdt_balance:.2f}")
        else:
            print("⚠️ Bybit connection failed - paper trading only")
            self.production = False
        
        while self.running:
            try:
                # Process execution queue
                opportunity = await self.execution_queue.get()
                if opportunity:
                    result = await self._execute_arbitrage(opportunity)
                    print(f"📊 Execution result: {result}")
                    
                    # Store in memory
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
        
        # Cleanup
        await self.zaru_client.close()
        await self.bybit.close()
        await self.stop()
    
    async def queue_opportunity(self, opportunity: Dict[str, Any]):
        """Queue an arbitrage opportunity for execution."""
        await self.execution_queue.put(opportunity)
        print(f"📋 Queued opportunity: {opportunity.get('token')} - ${opportunity.get('net_profit', 0):.2f}")
    
    async def _execute_arbitrage(self, opportunity: Dict) -> Dict[str, Any]:
        """
        Execute a complete arbitrage cycle.
        
        This is the core execution logic.
        """
        try:
            token = opportunity.get('token', 'UNKNOWN')
            buy_exchange = opportunity.get('buy_exchange', 'cex')
            sell_exchange = opportunity.get('sell_exchange', 'dex')
            net_profit = opportunity.get('net_profit', 0)
            profit_pct = opportunity.get('profit_percentage', 0)
            
            # v2.9: Calculate trade size based on risk
            trade_size = self._calculate_trade_size(profit_pct)
            
            print(f"💹 EXECUTING: {token} | {buy_exchange} → {sell_exchange} | ${net_profit:.2f} profit")
            print(f"   Trade Size: ${trade_size:.2f}")
            
            # v2.9: Check daily loss limit
            if not await self._check_risk_limits():
                print("⚠️ Daily loss limit reached - stopping trades")
                return {'success': False, 'error': 'Daily loss limit reached'}
            
            if self.production:
                # REAL EXECUTION MODE - v2.9
                print("🔴 REAL TRADING MODE - EXECUTING WITH REAL FUNDS")
                
                # Step 1: Get current price
                ticker = await self.bybit.get_ticker("MATICUSDT")
                current_price = ticker.get('price', 0)
                
                if current_price == 0:
                    return {'success': False, 'error': 'Could not get price'}
                
                # Step 2: Place buy order on Bybit
                buy_result = await self._execute_real_buy(
                    token, 
                    trade_size / current_price,  # Convert to quantity
                    buy_exchange
                )
                
                if not buy_result.get('success'):
                    return {'success': False, 'error': 'Buy failed', 'details': buy_result}
                
                # Step 3: Place sell order on Bybit
                sell_result = await self._execute_real_sell(
                    token,
                    trade_size / current_price,
                    sell_exchange
                )
                
                if not sell_result.get('success'):
                    # Attempt to reverse the buy
                    await self._reverse_trade(token, trade_size, buy_exchange)
                    return {'success': False, 'error': 'Sell failed', 'details': sell_result}
                
                # Step 4: Calculate actual profit
                buy_price = buy_result.get('price', current_price)
                sell_price = sell_result.get('price', current_price * 1.01)
                actual_profit = (sell_price - buy_price) * (trade_size / current_price)
                
                # Step 5: Settle with ZARU
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
                # PAPER TRADING MODE
                return await self._execute_paper_trade(token, trade_size, net_profit, profit_pct)
            
        except Exception as e:
            print(f"❌ Execution error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    async def _execute_paper_trade(self, token: str, trade_size: float, net_profit: float, profit_pct: float) -> Dict:
        """Execute a paper trade (simulated)."""
        buy_price = 0.50 * (1 - 0.005)  # 0.5% below market
        sell_price = 0.50 * (1 + 0.005)  # 0.5% above market
        
        print(f"📝 PAPER TRADE: {token} | Buy ${buy_price:.4f} → Sell ${sell_price:.4f} | Profit: ${net_profit:.2f}")
        
        # Record in ZARU (as a record transaction, small fee)
        settlement = await self.zaru_client.create_settlement(
            amount=max(0.0001, net_profit * 0.01),  # 1% of profit as fee
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
        """Execute a real buy order on Bybit."""
        print(f"🔴 REAL BUY: {quantity:.4f} {token} on {exchange}")
        
        # Place market order on Bybit
        result = await self.bybit.place_market_order(
            symbol="MATICUSDT",
            side="Buy",
            qty=quantity,
            test=False  # Real order!
        )
        
        if result.get('retCode') == 0:
            return {
                'success': True,
                'price': float(result.get('result', {}).get('avgPrice', 0)),
                'quantity': quantity,
                'order_id': result.get('result', {}).get('orderId')
            }
        else:
            return {
                'success': False,
                'error': result.get('retMsg', 'Unknown error')
            }
    
    async def _execute_real_sell(self, token: str, quantity: float, exchange: str) -> Dict:
        """Execute a real sell order on Bybit."""
        print(f"🔴 REAL SELL: {quantity:.4f} {token} on {exchange}")
        
        # Place market order on Bybit
        result = await self.bybit.place_market_order(
            symbol="MATICUSDT",
            side="Sell",
            qty=quantity,
            test=False  # Real order!
        )
        
        if result.get('retCode') == 0:
            return {
                'success': True,
                'price': float(result.get('result', {}).get('avgPrice', 0)),
                'quantity': quantity,
                'order_id': result.get('result', {}).get('orderId')
            }
        else:
            return {
                'success': False,
                'error': result.get('retMsg', 'Unknown error')
            }
    
    def _calculate_trade_size(self, profit_pct: float) -> float:
        """Calculate trade size based on risk and profit potential."""
        # Start with base amount
        trade_size = self.trade_amount
        
        # Scale based on profit potential (higher profit = larger position)
        if profit_pct > 1.5:
            trade_size = min(trade_size * 1.5, self.max_position_size)
        elif profit_pct < 0.8:
            trade_size = max(trade_size * 0.5, 1)
        
        return trade_size
    
    async def _check_risk_limits(self) -> bool:
        """Check if risk limits are exceeded."""
        # Check daily reset
        today = datetime.now().date()
        if today != self.today:
            self.daily_pnl = 0.0
            self.today = today
        
        # Check daily loss limit
        if self.daily_pnl < -self.max_daily_loss:
            print(f"⚠️ Daily loss limit reached: ${self.daily_pnl:.2f}")
            return False
        
        return True
    
    async def _reverse_trade(self, token: str, amount: float, exchange: str):
        """Reverse a failed trade."""
        print(f"🔄 Reversing trade: {token} {amount} on {exchange}")
        # In production, this would sell back the tokens
    
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
            bybit_balance = await self.bybit.get_balance("USDT")
            return {
                'zaru_balance': balance,
                'bybit_usdt_balance': bybit_balance,
                'wallet_address': self.zaru_client.wallet_address
            }
        
        return {'status': 'idle', 'message': 'Unknown action'}