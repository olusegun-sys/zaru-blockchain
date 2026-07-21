"""
ZARU Configuration Module
==========================
Simple configuration using Python dataclasses + dotenv.

FIXED: Handles Render.com deployment with proper PORT parsing.
ADDED: Burn mechanism and easy difficulty for bot mining.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ============================================
# HELPER FUNCTIONS FOR PORT PARSING
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
    render_port = os.getenv("PORT")
    if render_port:
        try:
            port = int(render_port)
            print(f"✅ Using Render PORT: {port}")
            return port
        except (ValueError, TypeError):
            print(f"⚠️  Invalid Render PORT: {render_port}")
    
    return _parse_port("ZARU_API_PORT", 8332)


def _get_node_port() -> int:
    """Get node port with proper fallback."""
    return _parse_port("ZARU_NODE_PORT", 8333)


class Settings(BaseModel):
    """
    Configuration settings for ZARU.
    Loaded from environment variables with sensible defaults.
    """
    
    # ============================================
    # NETWORK SETTINGS
    # ============================================
    
    NODE_HOST: str = os.getenv("ZARU_NODE_HOST", "0.0.0.0")
    NODE_PORT: int = _get_node_port()
    API_HOST: str = os.getenv("ZARU_API_HOST", "0.0.0.0")
    API_PORT: int = _get_api_port()
    
    # ============================================
    # BLOCKCHAIN SETTINGS
    # ============================================
    
    INITIAL_COIN_SUPPLY: int = 21_000_000
    COINBASE_MATURITY: int = 100
    BLOCK_TIME_SECONDS: int = 600
    MAX_BLOCK_SIZE_BYTES: int = 1_000_000
    DIFFICULTY_ADJUSTMENT_INTERVAL: int = 2016
    
    # 🔥 BURN ADDRESS - All burned coins go here
    BURN_ADDRESS: str = "ZARU_BURN_0000000000000000000000000000000000000000"
    BURN_PERCENTAGE: int = 1  # 1% of fees burned
    
    # ============================================
    # MINING SETTINGS - EASY MODE FOR BOTS
    # ============================================
    
    # Mainnet difficulty (hard)
    INITIAL_DIFFICULTY: int = 0x1d00ffff
    
    # Easy difficulty for bot mining (10,000x easier)
    EASY_DIFFICULTY: int = 0x0000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    MIN_TARGET: int = 0x00000000ffff0000000000000000000000000000000000000000000000000000
    MAX_TARGET: int = 0x00000000ffff0000000000000000000000000000000000000000000000000000
    
    # Auto-adjust difficulty based on block time
    AUTO_DIFFICULTY: bool = True
    TARGET_BLOCK_TIME: int = 60  # Target 60 seconds for easy mining
    
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
    
    IS_TESTNET: bool = os.getenv("ZARU_TESTNET", "true").lower() == "true"
    TESTNET_PORT: int = int(os.getenv("ZARU_TESTNET_PORT", "18333"))
    TESTNET_API_PORT: int = int(os.getenv("ZARU_TESTNET_API_PORT", "18332"))
    
    # ============================================
    # PYDANTIC V2 CONFIG
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
    """Get the database file path."""
    return get_data_dir() / f"{settings.DB_NAME}.db"


def get_db_backend() -> str:
    """Get the configured database backend"""
    if os.getenv("DATABASE_URL"):
        return "postgresql"
    
    if os.name == "nt" and settings.DB_BACKEND == "rocksdb":
        print("⚠️  Windows detected: Falling back to SQLite backend")
        return "sqlite"
    
    return settings.DB_BACKEND


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
    print(f"Burn Address: {settings.BURN_ADDRESS[:20]}...")
    print(f"Burn Percentage: {settings.BURN_PERCENTAGE}%")
    print(f"Easy Difficulty: {settings.EASY_DIFFICULTY}")
    
    if os.getenv("RENDER"):
        print(f"Platform: Render.com")
        print(f"Render PORT: {os.getenv('PORT')}")
    
    print("=" * 50)


if __name__ != "__main__":
    print_config_summary()