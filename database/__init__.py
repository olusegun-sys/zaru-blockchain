"""
ZARU Database Package
=====================
Provides storage for blocks, UTXOs, and chain state.
"""

import os
from .base_store import BaseStore
from config import settings


def get_store() -> BaseStore:
    """
    Factory function to get the appropriate database backend.
    """
    # Production: PostgreSQL
    if os.getenv("DATABASE_URL"):
        try:
            from .postgres_store import PostgresStore
            print("🔧 Using PostgreSQL backend (production)")
            return PostgresStore()
        except ImportError as e:
            print(f"⚠️  PostgreSQL not available: {e}")
        except Exception as e:
            print(f"⚠️  PostgreSQL connection failed: {e}")
    
    # Windows: SQLite
    if os.name == "nt":
        from .sqlite_store import SQLiteStore
        print("🔧 Using SQLite backend (Windows)")
        return SQLiteStore()
    
    # RocksDB (Linux)
    if settings.DB_BACKEND == "rocksdb":
        try:
            from .rocksdb_store import RocksDBStore
            print("🔧 Using RocksDB backend")
            return RocksDBStore()
        except ImportError:
            print("⚠️  RocksDB not available, falling back to SQLite")
        except Exception as e:
            print(f"⚠️  RocksDB initialization failed: {e}")
    
    # Default: SQLite
    from .sqlite_store import SQLiteStore
    print("🔧 Using SQLite backend (default)")
    return SQLiteStore()


# Global store instance
store = get_store()


__all__ = [
    'BaseStore',
    'SQLiteStore',
    'RocksDBStore',
    'PostgresStore',
    'store',
    'get_store',
]