"""
ZARU API Main Module
====================
FastAPI application setup and configuration.

CORS: Explicitly configured to allow all origins.
"""

import sys
import os
from contextlib import asynccontextmanager

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.routes import router


# ============================================
# APPLICATION LIFECYCLE
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    print("🚀 Starting ZARU API...")
    print(f"   Environment: {'TESTNET' if settings.IS_TESTNET else 'MAINNET'}")
    print(f"   API Port: {settings.API_PORT}")
    
    # Initialize services
    from blockchain.chain_manager import chain_manager
    from mempool import mempool
    from miner import miner
    from wallet import wallet
    from network import get_node
    
    # Start network node ONLY if explicitly enabled
    if os.getenv("ZARU_NETWORK_ENABLED", "false").lower() == "true":
        try:
            node = get_node()
            node.start()
            print(f"✅ Network node started on port {settings.NODE_PORT}")
        except Exception as e:
            print(f"⚠️  Network node not started: {e}")
    else:
        print("ℹ️  Network node disabled (API-only mode)")
    
    print("✅ ZARU API ready!")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down ZARU API...")
    try:
        from network import get_node
        node = get_node()
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

# ============================================
# CORS MIDDLEWARE - EXPLICITLY ALLOW ALL
# ============================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🌐 CORS: Allowing all origins")


# ============================================
# INCLUDE ROUTER
# ============================================

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
    from network import get_node
    
    node = get_node()
    is_running = node.running if hasattr(node, 'running') else False
    
    return {
        "status": "healthy",
        "chain_height": chain_manager.get_height(),
        "mempool_size": mempool.get_mempool_size(),
        "peer_count": node.get_peer_count() if hasattr(node, 'get_peer_count') else 0,
        "is_mining": False,
        "network_enabled": is_running
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