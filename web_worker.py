#!/usr/bin/env python
"""
ZARU Web Worker for Render Free Tier
====================================
Runs as a web service with Flask to keep the miner alive.
Render pings /health every few minutes, which keeps the service awake.
The miner runs in a background thread while Flask handles requests.

FIXED: Uses PostgreSQL to sync with the API database.
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime

# Force PostgreSQL for the miner
os.environ["ZARU_DB_BACKEND"] = "postgresql"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify

# Import ZARU components
from miner import miner
from wallet import wallet
from blockchain.chain_manager import chain_manager

# ============================================
# LOGGING CONFIGURATION
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================
# FLASK APP
# ============================================

app = Flask(__name__)

# Global state
mining_active = False
mining_address = None
start_time = time.time()
blocks_mined = 0

# ============================================
# ROUTES
# ============================================

@app.route('/')
@app.route('/health')
def health():
    """Health check endpoint - keeps the service alive on Render."""
    stats = miner.get_stats() if mining_active else {}
    return jsonify({
        "status": "healthy",
        "mining": mining_active,
        "address": mining_address,
        "blocks_mined": stats.get('blocks_mined', 0),
        "chain_height": chain_manager.get_height(),
        "uptime_seconds": int(time.time() - start_time),
        "uptime_hours": round((time.time() - start_time) / 3600, 2),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/start')
def start_mining_route():
    """Start the mining process via API."""
    global mining_active, mining_address
    if not mining_active:
        try:
            # FORCE: Use the specific wallet address
            mining_address = "1f6254f2f4dfb787262f6b3e18d482a77cd6a979"
            logger.info(f"💰 FORCED MINING ADDRESS: {mining_address}")
            
            miner.set_mining_address(mining_address)
            miner.start_mining(continuous=True, num_threads=2)
            mining_active = True
            logger.info(f"✅ Mining started with address: {mining_address}")
            return jsonify({"status": "started", "address": mining_address})
        except Exception as e:
            logger.error(f"❌ Failed to start mining: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "already_running", "address": mining_address})

@app.route('/stop')
def stop_mining_route():
    """Stop the mining process via API."""
    global mining_active
    if mining_active:
        miner.stop_mining()
        mining_active = False
        logger.info("⛏️ Mining stopped")
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})

@app.route('/status')
def status():
    """Detailed status endpoint."""
    stats = miner.get_stats() if mining_active else {}
    balance = 0
    if mining_address:
        try:
            balance = wallet.get_balance(mining_address)
        except:
            pass
    return jsonify({
        "mining": mining_active,
        "address": mining_address,
        "balance_satoshis": balance,
        "balance_zar": balance / 100000000 if balance else 0,
        "blocks_mined": stats.get('blocks_mined', 0),
        "hash_rate": stats.get('hash_rate', 0),
        "chain_height": chain_manager.get_height(),
        "uptime_hours": round((time.time() - start_time) / 3600, 2),
        "timestamp": datetime.now().isoformat()
    })

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 Starting ZARU Web Worker on RENDER")
    logger.info("=" * 60)
    logger.info(f"   Time: {datetime.now().isoformat()}")
    logger.info(f"   Python: {sys.version}")
    logger.info(f"   Working Dir: {os.getcwd()}")
    logger.info(f"   Database Backend: {os.getenv('ZARU_DB_BACKEND', 'SQLite')}")
    
    # FORCE: Use the specific wallet address
    mining_address = "1f6254f2f4dfb787262f6b3e18d482a77cd6a979"
    logger.info(f"💰 FORCED MINING ADDRESS: {mining_address}")
    
    # Set the mining address
    miner.set_mining_address(mining_address)
    
    # Start mining with 2 threads
    miner.start_mining(continuous=True, num_threads=2)
    mining_active = True
    
    logger.info(f"✅ Mining started successfully!")
    logger.info(f"   Address: {mining_address}")
    logger.info(f"   Threads: 2")
    logger.info(f"   Mode: Continuous")
    logger.info(f"   Database: PostgreSQL (shared with API)")
    
    # Run Flask web server
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    logger.info("=" * 60)
    app.run(host="0.0.0.0", port=port)