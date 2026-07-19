"""
ZARU Background Mining Worker
==============================
Runs continuously on Render to mine blocks.
"""

import os
import sys
import time
import logging

# Add project to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from blockchain.chain_manager import chain_manager
from mempool import mempool
from miner import miner
from database import store

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main mining worker loop."""
    logger.info("🚀 Starting ZARU Mining Worker...")
    logger.info(f"   Environment: {'TESTNET' if settings.IS_TESTNET else 'MAINNET'}")
    
    # Get mining address from environment
    mining_address = os.getenv("ZARU_MINING_ADDRESS")
    if not mining_address:
        logger.error("❌ ZARU_MINING_ADDRESS not set! Please set this environment variable.")
        logger.info("   Create an address via the API first, then set it as ZARU_MINING_ADDRESS")
        return
    
    # Set mining address
    miner.set_mining_address(mining_address)
    logger.info(f"✅ Mining address set: {mining_address[:10]}...")
    
    # Get number of threads from environment (default: 2)
    threads = int(os.getenv("ZARU_MINING_THREADS", 2))
    logger.info(f"✅ Mining threads: {threads}")
    
    # Start mining
    logger.info("⛏️  Starting mining...")
    miner.start_mining(continuous=True, num_threads=threads)
    
    # Keep running
    try:
        while True:
            time.sleep(60)
            stats = miner.get_stats()
            logger.info(f"📊 Mining stats: {stats['blocks_mined']} blocks, {stats['hash_rate']:.0f} H/s")
    except KeyboardInterrupt:
        logger.info("🛑 Stopping miner...")
        miner.stop_mining()


if __name__ == "__main__":
    main()