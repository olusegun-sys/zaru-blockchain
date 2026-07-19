"""
ZARU Database Package
=====================
Provides storage for blocks, UTXOs, and chain state.
Supports SQLite (development), PostgreSQL (production), and RocksDB (high-performance).
"""

import os
from typing import Optional
from .base_store import BaseStore
from config import settings


def get_store() -> BaseStore:
    """
    Factory function to get the appropriate database backend.
    
    WHY: Automatically selects the right database based on:
    1. Environment variables (DATABASE_URL for production)
    2. Configuration setting (DB_BACKEND)
    3. Operating system (Windows automatically uses SQLite)
    4. Availability of database drivers
    
    This is a classic Factory Pattern - we hide the complexity
    of choosing the right database from the rest of the code.
    """
    
    # ============================================
    # PRODUCTION: PostgreSQL
    # ============================================
    # Check if DATABASE_URL is set (Render.com, Heroku, etc.)
    if os.getenv("DATABASE_URL"):
        try:
            from .postgres_store import PostgresStore
            print("🔧 Using PostgreSQL backend (production)")
            return PostgresStore()
        except ImportError as e:
            print(f"⚠️  PostgreSQL not available: {e}")
            print("   Falling back to SQLite")
        except Exception as e:
            print(f"⚠️  PostgreSQL connection failed: {e}")
            print("   Falling back to SQLite")
    
    # ============================================
    # WINDOWS: SQLite (no compilation needed)
    # ============================================
    if os.name == "nt":
        from .sqlite_store import SQLiteStore
        print("🔧 Using SQLite backend (Windows development)")
        return SQLiteStore()
    
    # ============================================
    # PRODUCTION: RocksDB (Linux only)
    # ============================================
    if settings.DB_BACKEND == "rocksdb":
        try:
            from .rocksdb_store import RocksDBStore
            print("🔧 Using RocksDB backend (production)")
            return RocksDBStore()
        except ImportError:
            print("⚠️  RocksDB not available, falling back to SQLite")
        except Exception as e:
            print(f"⚠️  RocksDB initialization failed: {e}")
            print("   Falling back to SQLite")
    
    # ============================================
    # DEFAULT: SQLite
    # ============================================
    from .sqlite_store import SQLiteStore
    print("🔧 Using SQLite backend (default)")
    return SQLiteStore()


# ============================================
# GLOBAL STORE INSTANCE
# ============================================

# Create a global store instance
# This is the database connection that everything will use
store = get_store()


# ============================================
# EXPORTS
# ============================================

__all__ = [
    'BaseStore',
    'SQLiteStore',
    'RocksDBStore',
    'PostgresStore',  # Added for production
    'store',
    'get_store',
]