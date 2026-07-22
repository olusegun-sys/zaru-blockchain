"""
ZARU Miner Package
==================
Handles Proof of Work mining and block creation.
"""

# Import the Miner class and create a fresh instance
from .miner import Miner

# Create a fresh instance (not from cache)
def get_miner():
    """Get a fresh miner instance."""
    return Miner(easy_mode=True)

# For backward compatibility, create a default instance
miner = get_miner()

__all__ = [
    'Miner',
    'miner',
    'get_miner',
]