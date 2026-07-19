"""
ZARU API Package
================
REST API for wallet, blockchain, and mining operations.
"""

from .main import app
from .routes import router

__all__ = [
    'app',
    'router',
]