#!/usr/bin/env python
"""
ZARU Mining Bot
================
Automated mining bot that mines blocks continuously.

HOW IT WORKS:
1. Creates/uses a mining wallet
2. Mines blocks continuously
3. Collects rewards
4. Reports statistics
"""

import sys
import os
import time
import json
import random
import logging
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from blockchain.chain_manager import chain_manager
from blockchain.utxo import UTXOSet
from mempool import mempool
from miner import miner
from wallet import wallet
from database import store

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MiningBot:
    """
    Automated mining bot.
    Mines blocks, collects rewards, and reports stats.
    """
    
    def __init__(self, address=None, threads=2, easy_mode=True):
        """Initialize the mining bot."""
        self.address = address
        self.threads = threads
        self.easy_mode = easy_mode
        self.running = False
        self.blocks_mined = 0
        self.total_reward = 0
        self.start_time = None
        
        # Create wallet if no address provided
        if not self.address:
            self.address = self._create_wallet()
        
        # Configure miner
        miner.set_mining_address(self.address)
        miner.easy_mode = easy_mode
        
        logger.info(f"🤖 Mining Bot initialized")
        logger.info(f"   Address: {self.address[:10]}...")
        logger.info(f"   Threads: {threads}")
        logger.info(f"   Mode: {'Easy' if easy_mode else 'Normal'}")
    
    def _create_wallet(self):
        """Create a new wallet address for mining."""
        address = wallet.create_address(label="Mining Bot")
        logger.info(f"📝 Created new mining address: {address[:10]}...")
        return address
    
    def start(self):
        """Start the mining bot."""
        if self.running:
            logger.warning("Bot already running")
            return
        
        self.running = True
        self.start_time = time.time()
        
        logger.info("🚀 Starting mining bot...")
        logger.info(f"   Mining address: {self.address[:10]}...")
        logger.info(f"   Using {self.threads} thread(s)")
        
        # Start mining
        miner.start_mining(
            continuous=True,
            num_threads=self.threads,
            block=None
        )
        
        # Monitor mining
        self._monitor()
    
    def _monitor(self):
        """Monitor mining progress."""
        while self.running:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                # Get stats
                stats = miner.get_stats()
                new_blocks = stats['blocks_mined'] - self.blocks_mined
                self.blocks_mined = stats['blocks_mined']
                
                # Get balance
                balance = wallet.get_balance(self.address)
                self.total_reward = balance
                
                # Calculate hash rate
                hash_rate = stats['hash_rate']
                
                # Log progress
                elapsed = time.time() - self.start_time
                logger.info(f"📊 Mining Status:")
                logger.info(f"   Blocks mined: {self.blocks_mined} (new: {new_blocks})")
                logger.info(f"   Total reward: {self.total_reward} satoshis")
                logger.info(f"   Balance: {self.total_reward / 100_000_000:.8f} ZARU")
                logger.info(f"   Hash rate: {hash_rate:,.0f} H/s")
                logger.info(f"   Running: {elapsed/60:.1f} minutes")
                
                # Check if we've mined a block recently
                if new_blocks == 0 and elapsed > 600:
                    logger.warning("⚠️  No blocks mined in 10 minutes. Checking...")
                    if not miner.is_mining:
                        logger.warning("Miner stopped! Restarting...")
                        miner.start_mining(continuous=True, num_threads=self.threads)
                
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                logger.error(f"Error in monitor: {e}")
    
    def stop(self):
        """Stop the mining bot."""
        self.running = False
        miner.stop_mining()
        
        # Final stats
        elapsed = time.time() - self.start_time
        logger.info("🛑 Mining bot stopped")
        logger.info(f"   Total blocks mined: {self.blocks_mined}")
        logger.info(f"   Total reward: {self.total_reward} satoshis")
        logger.info(f"   Runtime: {elapsed/60:.1f} minutes")
        logger.info(f"   Balance: {self.total_reward / 100_000_000:.8f} ZARU")
    
    def get_stats(self):
        """Get bot statistics."""
        return {
            'address': self.address,
            'blocks_mined': self.blocks_mined,
            'total_reward': self.total_reward,
            'balance': self.total_reward / 100_000_000,
            'is_running': self.running,
            'threads': self.threads,
            'easy_mode': self.easy_mode,
        }


def main():
    """Main entry point."""
    # Parse command line args
    import argparse
    parser = argparse.ArgumentParser(description='ZARU Mining Bot')
    parser.add_argument('--address', help='Mining address (creates one if not provided)')
    parser.add_argument('--threads', type=int, default=2, help='Number of threads')
    parser.add_argument('--easy', action='store_true', default=True, help='Easy mode')
    parser.add_argument('--once', action='store_true', help='Mine one block and exit')
    
    args = parser.parse_args()
    
    # Create bot
    bot = MiningBot(
        address=args.address,
        threads=args.threads,
        easy_mode=args.easy
    )
    
    if args.once:
        # Mine one block
        block = miner.mine_test_block()
        if block:
            success, msg = miner.submit_block(block)
            logger.info(f"Block mined: {success} - {msg}")
    else:
        # Run continuously
        try:
            bot.start()
        except KeyboardInterrupt:
            bot.stop()
            logger.info("👋 Goodbye!")


if __name__ == "__main__":
    main()