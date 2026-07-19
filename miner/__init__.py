"""
ZARU Miner Package
==================
Handles Proof of Work mining and block creation.

WHY: The miner finds valid blocks by solving the PoW puzzle.
It takes transactions from the mempool and creates new blocks.
"""

from .miner import Miner, miner

__all__ = [
    'Miner',
    'miner',
]