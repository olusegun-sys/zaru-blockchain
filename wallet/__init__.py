"""
ZARU Wallet Package
===================
Key management, address generation, and transaction creation.

WHY: The wallet handles all user-facing cryptocurrency operations.
It manages keys, creates addresses, checks balances, and sends transactions.
"""

from .wallet import Wallet, wallet
from .key_store import KeyStore

__all__ = [
    'Wallet',
    'wallet',
    'KeyStore',
]