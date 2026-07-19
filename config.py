"""
ZARU Configuration Module
==========================
Central configuration for the ZARU cryptocurrency node.
All settings are loaded from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configuration settings for ZARU.
    
    WHY: Centralizes all configuration in one place, making it easy to
    change behavior without modifying code. Uses environment variables
    for security (never hardcode secrets).
    """
    
    # ============================================
    # NETWORK SETTINGS
    # ============================================
    
    NODE_HOST: str = "0.0.0.0"  # Bind to all interfaces for P2P
    NODE_PORT: int = 8333       # Default ZARU P2P port
    API_HOST: str = "127.0.0.1" # Localhost for API (security)
    API_PORT: int = 8332        # Default ZARU RPC port
    
    # ============================================
    # BLOCKCHAIN SETTINGS
    # ============================================
    
    INITIAL_COIN_SUPPLY: int = 21_000_000  # 21 million total coins
    COINBASE_MATURITY: int = 100          # Blocks before coinbase output can be spent
    BLOCK_TIME_SECONDS: int = 600          # Target time between blocks (10 min)
    MAX_BLOCK_SIZE_BYTES: int = 1_000_000  # 1 MB max block size
    DIFFICULTY_ADJUSTMENT_INTERVAL: int = 2016  # Recalculate every 2016 blocks
    
    # ============================================
    # MINING SETTINGS
    # ============================================
    
    INITIAL_DIFFICULTY: int = 0x1d00ffff   # Initial target
    
    # ============================================
    # MEMPOOL SETTINGS
    # ============================================
    
    MEMPOOL_MAX_SIZE: int = 10_000         # Maximum transactions in mempool
    MEMPOOL_EXPIRY_HOURS: int = 72         # Remove transactions older than 72 hours
    
    # ============================================
    # DATABASE SETTINGS
    # ============================================
    
    DATA_DIR: Path = Path(os.getenv("ZARU_DATA_DIR", "./data"))
    DB_NAME: str = "zaru_ledger"
    
    # ============================================
    # PEER SETTINGS
    # ============================================
    
    BOOTSTRAP_NODES: List[str] = [
        "zarunode1.example.com:8333",
        "zarunode2.example.com:8333",
    ]
    MAX_PEERS: int = 125
    PEER_CONNECTION_TIMEOUT: int = 30
    
    # ============================================
    # WALLET SETTINGS
    # ============================================
    
    DEFAULT_FEE_PER_KB: int = 1000
    MIN_RELAY_FEE: int = 500
    
    # ============================================
    # SECURITY SETTINGS
    # ============================================
    
    ENABLE_CORS: bool = True
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
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
    
    IS_TESTNET: bool = os.getenv("ZARU_TESTNET", "False").lower() == "true"
    TESTNET_PORT: int = 18333
    TESTNET_API_PORT: int = 18332
    
    class Config:
        """Pydantic configuration for loading from .env file"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


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


# ============================================
# Quick validation on import
# ============================================

if settings.IS_TESTNET:
    print(f"⚠️  ZARU running in TESTNET mode on port {settings.TESTNET_PORT}")
else:
    print(f"✅ ZARU running in MAINNET mode on port {settings.NODE_PORT}") 
