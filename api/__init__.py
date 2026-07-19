"""
ZARU API Package
================
REST API for wallet, blockchain, and mining operations.

WHY: This package provides the HTTP interface for ZARU.
All endpoints are documented with OpenAPI/Swagger.
"""

from .main import app
from .routes import router

__all__ = [
    'app',
    'router',
]