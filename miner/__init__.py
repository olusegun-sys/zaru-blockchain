"""
ZARU Miner Package
==================
Handles Proof of Work mining and block creation.
"""

from .miner import Miner, miner

__all__ = [
    'Miner',
    'miner',
]