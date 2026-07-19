"""
ZARU API Main Module
====================
FastAPI application setup and configuration.

WHY: The API provides REST endpoints for:
- Wallet operations (balance, send, addresses)
- Blockchain queries (blocks, transactions, chain info)
- Mining control (start, stop, stats)
- Network monitoring (peers, node info)

THINK OF IT LIKE: A bank's API that allows apps to check balances,
transfer money, and view transaction history.
"""

import sys
import os
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
from api.routes import router


# ============================================
# APPLICATION LIFECYCLE
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    
    WHY: Handles startup and shutdown of services.
    """
    # Startup
    print("🚀 Starting ZARU API...")
    print(f"   Environment: {'TESTNET' if settings.IS_TESTNET else 'MAINNET'}")
    print(f"   API Port: {settings.API_PORT}")
    
    # Initialize services
    from blockchain.chain_manager import chain_manager
    from mempool import mempool
    from miner import miner
    from wallet import wallet
    from network import node
    
    # Start network node (if configured)
    try:
        node.start()
        print(f"✅ Network node started on port {settings.NODE_PORT}")
    except Exception as e:
        print(f"⚠️  Network node not started: {e}")
    
    print("✅ ZARU API ready!")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down ZARU API...")
    try:
        from network import node
        node.stop()
    except:
        pass


# ============================================
# CREATE FASTAPI APP
# ============================================

app = FastAPI(
    title="ZARU API",
    description="ZARU Cryptocurrency REST API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if settings.ENABLE_CORS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router
app.include_router(router)


# ============================================
# ROOT ENDPOINT
# ============================================

@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "ZARU API",
        "version": "1.0.0",
        "status": "running",
        "environment": "testnet" if settings.IS_TESTNET else "mainnet",
        "endpoints": {
            "wallet": "/wallet",
            "blockchain": "/blockchain",
            "mining": "/mining",
            "network": "/network",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    from blockchain.chain_manager import chain_manager
    from mempool import mempool
    from network import node
    
    return {
        "status": "healthy",
        "chain_height": chain_manager.get_height(),
        "mempool_size": mempool.get_mempool_size(),
        "peer_count": node.get_peer_count(),
        "is_mining": False,  # Will be updated from miner
    }


# ============================================
# RUN SERVER (for development)
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True
    )