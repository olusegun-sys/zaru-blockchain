"""
ZARU Configuration Module
==========================
Simple configuration using Python dataclasses + dotenv.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ============================================
# PORT PARSING HELPERS
# ============================================

def _parse_port(env_var: str, default: int) -> int:
    """Parse port from environment variable with safe fallback."""
    value = os.getenv(env_var)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        print(f"⚠️  Invalid port value '{value}' for {env_var}, using default {default}")
        return default


def _get_api_port() -> int:
    """Get API port with Render.com compatibility."""
    # Check if Render's PORT is set
    render_port = os.getenv("PORT")
    if render_port:
        try:
            port = int(render_port)
            print(f"✅ Using Render PORT: {port}")
            return port
        except (ValueError, TypeError):
            print(f"⚠️  Invalid Render PORT: {render_port}")
    
    # Fallback to custom variable
    return _parse_port("ZARU_API_PORT", 8332)


def _get_node_port() -> int:
    """Get node port with proper fallback."""
    return _parse_port("ZARU_NODE_PORT", 8333)


# ============================================
# SETTINGS CLASS
# ============================================

class Settings(BaseModel):
    """Configuration settings for ZARU."""
    
    # Network
    NODE_HOST: str = os.getenv("ZARU_NODE_HOST", "0.0.0.0")
    NODE_PORT: int = _get_node_port()
    API_HOST: str = os.getenv("ZARU_API_HOST", "0.0.0.0")
    API_PORT: int = _get_api_port()
    
    # Blockchain
    INITIAL_COIN_SUPPLY: int = 21_000_000
    COINBASE_MATURITY: int = 100
    BLOCK_TIME_SECONDS: int = 600
    MAX_BLOCK_SIZE_BYTES: int = 1_000_000
    DIFFICULTY_ADJUSTMENT_INTERVAL: int = 2016
    
    # Mining
    INITIAL_DIFFICULTY: int = 0x1d00ffff
    
    # Mempool
    MEMPOOL_MAX_SIZE: int = 10_000
    MEMPOOL_EXPIRY_HOURS: int = 72
    
    # Database
    DATA_DIR: Path = Path(os.getenv("ZARU_DATA_DIR", "./data"))
    DB_NAME: str = os.getenv("ZARU_DB_NAME", "zaru_ledger")
    DB_BACKEND: str = os.getenv("ZARU_DB_BACKEND", "sqlite")
    
    # Peers
    BOOTSTRAP_NODES: List[str] = [
        "zarunode1.example.com:8333",
        "zarunode2.example.com:8333",
    ]
    MAX_PEERS: int = int(os.getenv("ZARU_MAX_PEERS", "125"))
    PEER_CONNECTION_TIMEOUT: int = int(os.getenv("ZARU_PEER_TIMEOUT", "30"))
    
    # Wallet
    DEFAULT_FEE_PER_KB: int = 1000
    MIN_RELAY_FEE: int = 500
    
    # Security
    ENABLE_CORS: bool = os.getenv("ZARU_ENABLE_CORS", "true").lower() == "true"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    RATE_LIMIT_PER_MINUTE: int = 100
    JWT_SECRET_KEY: Optional[str] = os.getenv("ZARU_JWT_SECRET")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path = Path(os.getenv("ZARU_LOG_FILE", "./logs/zaru.log"))
    
    # Testnet
    IS_TESTNET: bool = os.getenv("ZARU_TESTNET", "false").lower() == "true"
    TESTNET_PORT: int = int(os.getenv("ZARU_TESTNET_PORT", "18333"))
    TESTNET_API_PORT: int = int(os.getenv("ZARU_TESTNET_API_PORT", "18332"))
    
    # Pydantic config
    model_config = {
        "arbitrary_types_allowed": True
    }
    
    def is_dev_mode(self) -> bool:
        return self.DB_BACKEND == "sqlite"


# ============================================
# GLOBAL SETTINGS INSTANCE
# ============================================

settings = Settings()


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_data_dir() -> Path:
    data_dir = settings.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_dir() -> Path:
    log_dir = settings.LOG_FILE.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_database_path() -> Path:
    return get_data_dir() / f"{settings.DB_NAME}.db"


def get_db_backend() -> str:
    # Production: PostgreSQL
    if os.getenv("DATABASE_URL"):
        return "postgresql"
    
    # Windows: SQLite
    if os.name == "nt" and settings.DB_BACKEND == "rocksdb":
        print("⚠️  Windows detected: Falling back to SQLite backend")
        return "sqlite"
    
    return settings.DB_BACKEND


# ============================================
# CONFIG SUMMARY
# ============================================

def print_config_summary():
    print("=" * 50)
    print("🔧 ZARU CONFIGURATION SUMMARY")
    print("=" * 50)
    print(f"Environment: {'TESTNET' if settings.IS_TESTNET else 'MAINNET'}")
    print(f"Node Port: {settings.NODE_PORT}")
    print(f"API Port: {settings.API_PORT}")
    print(f"Database Backend: {get_db_backend()}")
    print(f"Data Directory: {get_data_dir()}")
    print(f"Log Level: {settings.LOG_LEVEL}")
    
    if os.getenv("RENDER"):
        print(f"Platform: Render.com")
        print(f"Render PORT: {os.getenv('PORT')}")
    
    print("=" * 50)


if __name__ != "__main__":
    print_config_summary()