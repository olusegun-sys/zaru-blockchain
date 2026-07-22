"""
ZARU Configuration Module
==========================
Simple configuration using Python dataclasses + dotenv.
NO pydantic_settings required - works with just pydantic.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseModel):
    """
    Configuration settings for ZARU.
    Loaded from environment variables with sensible defaults.
    """
    
    # ============================================
    # NETWORK SETTINGS
    # ============================================
    
    NODE_HOST: str = os.getenv("ZARU_NODE_HOST", "0.0.0.0")
    NODE_PORT: int = int(os.getenv("ZARU_NODE_PORT", "8333"))
    API_HOST: str = os.getenv("ZARU_API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("ZARU_API_PORT", "8332"))
    
    # ============================================
    # BLOCKCHAIN SETTINGS
    # ============================================
    
    INITIAL_COIN_SUPPLY: int = 21_000_000
    COINBASE_MATURITY: int = 100
    BLOCK_TIME_SECONDS: int = 600
    MAX_BLOCK_SIZE_BYTES: int = 1_000_000
    DIFFICULTY_ADJUSTMENT_INTERVAL: int = 2016
    
    # ============================================
    # MINING SETTINGS
    # ============================================
    
    INITIAL_DIFFICULTY: int = 0x1d00ffff
    
    # ============================================
    # MEMPOOL SETTINGS
    # ============================================
    
    MEMPOOL_MAX_SIZE: int = 10_000
    MEMPOOL_EXPIRY_HOURS: int = 72
    
    # ============================================
    # DATABASE SETTINGS
    # ============================================
    
    DATA_DIR: Path = Path(os.getenv("ZARU_DATA_DIR", "./data"))
    DB_NAME: str = os.getenv("ZARU_DB_NAME", "zaru_ledger")
    
    # Database backend: 'sqlite' (dev) or 'rocksdb' (production)
    DB_BACKEND: str = os.getenv("ZARU_DB_BACKEND", "sqlite")
    
    # ============================================
    # PEER SETTINGS
    # ============================================
    
    BOOTSTRAP_NODES: List[str] = [
        "zarunode1.example.com:8333",
        "zarunode2.example.com:8333",
    ]
    MAX_PEERS: int = int(os.getenv("ZARU_MAX_PEERS", "125"))
    PEER_CONNECTION_TIMEOUT: int = int(os.getenv("ZARU_PEER_TIMEOUT", "30"))
    
    # ============================================
    # WALLET SETTINGS
    # ============================================
    
    DEFAULT_FEE_PER_KB: int = 1000
    MIN_RELAY_FEE: int = 500
    
    # ============================================
    # SECURITY SETTINGS
    # ============================================
    
    ENABLE_CORS: bool = os.getenv("ZARU_ENABLE_CORS", "true").lower() == "true"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    RATE_LIMIT_PER_MINUTE: int = 100
    JWT_SECRET_KEY: Optional[str] = os.getenv("ZARU_JWT_SECRET")
    
    # ============================================
    # LOGGING SETTINGS
    # ============================================
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path = Path(os.getenv("ZARU_LOG_FILE", "./logs/zaru.log"))
    
    # ============================================
    # TESTNET SETTINGS
    # ============================================
    
    IS_TESTNET: bool = os.getenv("ZARU_TESTNET", "false").lower() == "true"
    TESTNET_PORT: int = int(os.getenv("ZARU_TESTNET_PORT", "18333"))
    TESTNET_API_PORT: int = int(os.getenv("ZARU_TESTNET_API_PORT", "18332"))
    
    # ============================================
    # PYDANTIC V2 CONFIG (FIXED - NO WARNINGS)
    # ============================================
    
    model_config = {
        "arbitrary_types_allowed": True
    }
    
    def is_dev_mode(self) -> bool:
        """Check if we're running in development mode"""
        return self.DB_BACKEND == "sqlite"


# ============================================
# Create a single global settings instance
# ============================================
settings = Settings()


# ============================================
# Helper functions
# ============================================

def get_data_dir() -> Path:
    """Get the data directory, creating it if it doesn't exist"""
    data_dir = settings.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_dir() -> Path:
    """Get the log directory, creating it if it doesn't exist"""
    log_dir = settings.LOG_FILE.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_database_path() -> Path:
    """
    Get the database file path.
    
    WHY: This method is used by the database layer to determine
    where to store the SQLite database file.
    """
    return get_data_dir() / f"{settings.DB_NAME}.db"


def get_db_backend() -> str:
    """Get the configured database backend"""
    # WHY: Automatically use SQLite on Windows to avoid compilation issues
    if os.name == "nt" and settings.DB_BACKEND == "rocksdb":
        print("⚠️  Windows detected: Falling back to SQLite backend")
        print("   (RocksDB requires Visual Studio Build Tools)")
        return "sqlite"
    return settings.DB_BACKEND


# ============================================
# Quick validation on import
# ============================================

def print_config_summary():
    """Print a summary of the configuration"""
    print("=" * 50)
    print("🔧 ZARU CONFIGURATION SUMMARY")
    print("=" * 50)
    print(f"Environment: {'TESTNET' if settings.IS_TESTNET else 'MAINNET'}")
    print(f"Node Port: {settings.NODE_PORT}")
    print(f"API Port: {settings.API_PORT}")
    print(f"Database Backend: {get_db_backend()}")
    print(f"Data Directory: {get_data_dir()}")
    print(f"Log Level: {settings.LOG_LEVEL}")
    
    if os.name == "nt":
        print(f"Operating System: Windows")
        print(f"Database: SQLite (auto-selected for Windows)")
    
    print("=" * 50)


# Print config when imported
if __name__ != "__main__":
    print_config_summary()