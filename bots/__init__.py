"""
ZARU Bots Package
=================
Automated bots for mining, transactions, and wallet generation.
"""

from .mining_bot import MiningBot
from .transaction_bot import TransactionBot
from .wallet_generator import WalletGeneratorBot

__all__ = [
    'MiningBot',
    'TransactionBot',
    'WalletGeneratorBot',
]