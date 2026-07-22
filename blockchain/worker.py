#!/usr/bin/env python
"""
ZARU Super-Mining Worker for Railway
====================================
Deployed as a background worker on Railway's free tier.
Runs 24/7 mining ZARU continuously.

RAILWAY SPECIFIC:
- Railway sets PORT environment variable automatically
- Railway expects logs on stdout
- Workers don't sleep - run forever
- No credit card required with $5 free credit
"""

import sys
import os
import time
import logging
import threading
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import ZARU components
from miner import miner
from wallet import wallet
from database import store
from blockchain.chain_manager import chain_manager


# ============================================
# LOGGING CONFIGURATION
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# ============================================
# HEALTH CHECK SERVER
# ============================================

def start_health_server():
    """
    Start a simple HTTP server for Railway health checks.
    
    WHY: Railway expects a health check endpoint.
    Without this, the worker might be marked as unhealthy.
    """
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/health' or self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'OK')
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                # Suppress health check logs
                pass
        
        # Railway sets PORT, default to 8080 if not set
        port = int(os.getenv('PORT', 8080))
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server running on port {port}")
        server.serve_forever()
        
    except Exception as e:
        logger.warning(f"⚠️ Health server not started: {e}")


# ============================================
# MAIN MINING LOOP
# ============================================

def main():
    """Main mining worker loop."""
    logger.info("=" * 60)
    logger.info("🚀 Starting ZARU Super-Miner on RAILWAY")
    logger.info("=" * 60)
    logger.info(f"   Time: {datetime.now().isoformat()}")
    logger.info(f"   Python: {sys.version}")
    logger.info(f"   Working Dir: {os.getcwd()}")
    
    # Start health server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    try:
        # Create a dedicated mining wallet
        logger.info("📝 Creating mining wallet...")
        address = wallet.create_address(label="Super_Miner_Railway")
        logger.info(f"   ✅ Mining address: {address}")
        
        # Set mining address
        miner.set_mining_address(address)
        logger.info(f"   ✅ Mining address set")
        
        # Get initial balance
        initial_balance = wallet.get_balance(address)
        logger.info(f"   💰 Initial balance: {initial_balance} satoshis")
        
        # Start mining with 4 threads (max power)
        logger.info("⛏️  Starting mining with 4 threads...")
        miner.start_mining(continuous=True, num_threads=4)
        
        # Track stats
        blocks_mined = 0
        start_time = time.time()
        
        # Main monitoring loop
        while True:
            time.sleep(60)  # Check every minute
            
            # Get stats
            stats = miner.get_stats()
            new_blocks = stats['blocks_mined'] - blocks_mined
            blocks_mined = stats['blocks_mined']
            balance = wallet.get_balance(address)
            hash_rate = stats.get('hash_rate', 0)
            difficulty = stats.get('difficulty', 0)
            chain_height = stats.get('chain_height', 0)
            
            # Calculate runtime
            runtime = (time.time() - start_time) / 3600  # hours
            
            # Log progress
            logger.info("=" * 50)
            logger.info(f"📊 MINING STATUS (Runtime: {runtime:.1f}h)")
            logger.info("=" * 50)
            logger.info(f"   Blocks mined: {blocks_mined:,} (new: {new_blocks})")
            logger.info(f"   Balance: {balance:,} satoshis ({balance/100_000_000:.8f} ZARU)")
            logger.info(f"   Hash rate: {hash_rate:,.0f} H/s")
            logger.info(f"   Difficulty: {difficulty}")
            logger.info(f"   Chain height: {chain_height}")
            logger.info(f"   Mining: {miner.is_mining}")
            logger.info("=" * 50)
            
            # Check if miner stopped
            if not miner.is_mining:
                logger.warning("⚠️ Miner stopped! Restarting...")
                miner.start_mining(continuous=True, num_threads=4)
            
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal. Stopping...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("🛑 Stopping miner...")
        miner.stop_mining()
        logger.info("✅ Miner stopped. Goodbye!")


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    main()