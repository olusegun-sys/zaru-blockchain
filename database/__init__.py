"""
ZARU Database Package
=====================
Provides storage for blocks, UTXOs, and chain state.
Supports both SQLite (development) and RocksDB (production).
"""

from .base_store import BaseStore
from .sqlite_store import SQLiteStore
from .rocksdb_store import RocksDBStore
from config import settings


def get_store() -> BaseStore:
    """
    Factory function to get the appropriate database backend
    
    WHY: Automatically selects the right database based on:
    1. Configuration setting (DB_BACKEND)
    2. Operating system (Windows automatically uses SQLite)
    3. Availability of RocksDB
    
    This is a classic Factory Pattern - we hide the complexity
    of choosing the right database from the rest of the code.
    """
    # Windows automatically uses SQLite (avoids compilation issues)
    import os
    if os.name == "nt":
        from .sqlite_store import SQLiteStore
        print("🔧 Windows detected: Using SQLite backend")
        return SQLiteStore()
    
    # Check if RocksDB is configured
    if settings.DB_BACKEND == "rocksdb":
        try:
            from .rocksdb_store import RocksDBStore
            print("🔧 Using RocksDB backend (production)")
            return RocksDBStore()
        except ImportError:
            print("⚠️  RocksDB not available, falling back to SQLite")
            from .sqlite_store import SQLiteStore
            return SQLiteStore()
    
    # Default to SQLite
    from .sqlite_store import SQLiteStore
    print("🔧 Using SQLite backend (development)")
    return SQLiteStore()


# For convenience, create a global store instance
# This is the database connection that everything will use
store = get_store()

__all__ = [
    'BaseStore',
    'SQLiteStore',
    'RocksDBStore',
    'store',
    'get_store',
]