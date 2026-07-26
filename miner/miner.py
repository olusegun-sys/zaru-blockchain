"""
ZARU Miner Module
=================
Handles Proof of Work mining and block creation.

ADDED: Easy mode for bot mining (reduced difficulty)
FIXED: Coinbase transaction properly added to all mined blocks
FIXED: Mempool transactions now included in blocks
FIXED: UnboundLocalError in mining_loop (block variable initialized)
FIXED: Duplicate block detection to prevent infinite mining loops
FIXED: Failed attempts counter to break out of stuck loops
VERSION: 2.3 - With Duplicate Prevention & Loop Safety
"""

import time
import threading
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import settings
from blockchain.block import Block, BlockHeader
from blockchain.transaction import Transaction, create_coinbase_transaction
from blockchain.chain_manager import ChainManager
from blockchain.utxo import UTXOSet
from mempool import Mempool
from database import store as db_store


@dataclass
class MiningStats:
    """Statistics for mining operations."""
    blocks_mined: int = 0
    total_hashes: int = 0
    total_time: float = 0.0
    last_block_time: float = 0.0
    hash_rate: float = 0.0
    attempts: int = 0


class Miner:
    """
    Handles Proof of Work mining with EASY MODE for bots.
    
    VERSION 2.3: Added duplicate block detection and loop safety.
    """
    
    def __init__(
        self,
        chain_manager: Optional[ChainManager] = None,
        mempool: Optional[Mempool] = None,
        utxo_set: Optional[UTXOSet] = None,
        store=None,
        address: Optional[str] = None,
        easy_mode: bool = True
    ):
        """
        Initialize the miner.
        
        Args:
            easy_mode: If True, uses 10,000x easier difficulty
        """
        self.store = store if store else db_store
        self.chain_manager = chain_manager if chain_manager else ChainManager(self.store)
        self.mempool = mempool if mempool else Mempool()
        self.utxo_set = utxo_set if utxo_set else self.chain_manager.utxo_set
        
        # Pass mempool to chain_manager for confirmation
        self.chain_manager.mempool = self.mempool
        
        self.address = address
        self.is_mining = False
        self.mining_thread = None
        self.stop_event = threading.Event()
        
        # Stats
        self.stats = MiningStats()
        self.hash_count = 0
        self.last_hash_rate_check = time.time()
        
        # Easy mode
        self.easy_mode = easy_mode
        if easy_mode:
            print("🎯 EASY MODE ENABLED - Mining difficulty reduced 10,000x")
            self.chain_manager._difficulty = settings.EASY_DIFFICULTY
            self.chain_manager.store.put_chain_state('difficulty', settings.EASY_DIFFICULTY)
        
        print(f"✅ Miner initialized (VERSION 2.3 - WITH DUPLICATE PREVENTION)")
        print(f"   Address: {address or 'Not set - mining disabled'}")
        print(f"   Difficulty: {self.chain_manager.get_difficulty()}")
        print(f"   Mode: {'Easy' if easy_mode else 'Normal'}")
    
    # ============================================
    # MINING CONFIGURATION
    # ============================================
    
    def set_mining_address(self, address: str) -> None:
        """Set the mining reward address."""
        self.address = address
        print(f"✅ Mining address set: {address}")
    
    def set_difficulty(self, difficulty: int) -> None:
        """Manually set mining difficulty."""
        print(f"⚙️  Setting difficulty to {difficulty}")
        self.chain_manager._difficulty = difficulty
        self.chain_manager.store.put_chain_state('difficulty', difficulty)
    
    def set_easy_mode(self, enabled: bool) -> None:
        """Enable or disable easy mode."""
        self.easy_mode = enabled
        if enabled:
            print("🎯 Easy mode ENABLED")
            self.chain_manager._difficulty = settings.EASY_DIFFICULTY
        else:
            print("🎯 Easy mode DISABLED")
            self.chain_manager._difficulty = settings.INITIAL_DIFFICULTY
        self.chain_manager.store.put_chain_state('difficulty', self.chain_manager._difficulty)
    
    # ============================================
    # BLOCK CREATION
    # ============================================
    
    def create_block_template(self, max_tx_count: int = 100) -> Optional[Block]:
        """
        Create a candidate block for mining with coinbase AND mempool transactions.
        
        FIXED: Now properly includes mempool transactions in the block.
        
        Args:
            max_tx_count: Maximum number of transactions to include from mempool
        """
        if not self.address:
            print("❌ Mining address not set! Use set_mining_address()")
            return None
        
        # Get transactions from mempool
        mempool_txs = self.mempool.get_transactions(max_tx_count)
        print(f"📦 Retrieved {len(mempool_txs)} transactions from mempool")
        
        # Create coinbase transaction (mining reward)
        reward = 50_000_000  # 50 ZARU in satoshis
        coinbase = create_coinbase_transaction(self.address, reward)
        
        # Add coinbase as first transaction, then mempool transactions
        all_transactions = [coinbase] + mempool_txs
        
        # Get current chain state
        tip_hash = self.chain_manager.get_tip_hash()
        height = self.chain_manager.get_height()
        difficulty = self.chain_manager.get_difficulty()
        
        # Create block
        block = Block()
        block.header = BlockHeader(
            version=1,
            prev_block_hash=tip_hash,
            timestamp=int(time.time()),
            difficulty_target=difficulty,
            block_height=height
        )
        
        # Add all transactions (including coinbase and mempool)
        for tx in all_transactions:
            block.add_transaction(tx)
        
        # Compute merkle root
        block.header.merkle_root = block.compute_merkle_root()
        
        # Compute block hash (without PoW)
        block.hash = block.compute_hash()
        block.size = block.compute_size()
        block.transaction_count = len(block.transactions)
        
        print(f"📦 Block template created:")
        print(f"   Height: {height}")
        print(f"   Transactions: {len(block.transactions)} (1 coinbase + {len(mempool_txs)} from mempool)")
        print(f"   Difficulty: {difficulty}")
        print(f"   Reward: {reward} satoshis")
        
        return block
    
    # ============================================
    # PROOF OF WORK
    # ============================================
    
    def mine_block(self, block: Optional[Block] = None) -> Optional[Block]:
        """Mine a single block (find valid nonce)."""
        if block is None:
            block = self.create_block_template()
            if not block:
                return None
        
        print(f"⛏️  Mining block {block.header.block_height}...")
        print(f"   Target: {block.header.difficulty_target}")
        
        start_time = time.time()
        attempts = 0
        
        while not self.stop_event.is_set():
            block.header.nonce = attempts
            block_hash = block.compute_hash()
            
            hash_int = int(block_hash, 16)
            if hash_int < block.header.difficulty_target:
                elapsed = time.time() - start_time
                block.hash = block_hash
                block.size = block.compute_size()
                block.transaction_count = len(block.transactions)
                
                self.stats.blocks_mined += 1
                self.stats.total_hashes += attempts
                self.stats.total_time += elapsed
                self.stats.last_block_time = elapsed
                self.stats.attempts = attempts
                self.stats.hash_rate = self.stats.total_hashes / max(self.stats.total_time, 1)
                
                print(f"✅ Block mined in {elapsed:.2f}s after {attempts:,} attempts")
                print(f"   Nonce: {attempts}")
                print(f"   Block hash: {block_hash}")
                print(f"   Hash rate: {self.stats.hash_rate:,.0f} H/s")
                print(f"   Transactions: {len(block.transactions)}")
                
                return block
            
            attempts += 1
            
            if attempts % 100000 == 0:
                print(f"   Attempts: {attempts:,}, Current hash: {block_hash[:16]}...")
            
            self.hash_count += 1
        
        print("⛏️  Mining stopped")
        return None
    
    def mine_block_parallel(self, block: Optional[Block] = None, num_threads: int = 4) -> Optional[Block]:
        """Mine a block using multiple threads."""
        if block is None:
            block = self.create_block_template()
            if not block:
                return None
        
        print(f"⛏️  Mining block {block.header.block_height} with {num_threads} threads...")
        print(f"   Target: {block.header.difficulty_target}")
        
        start_time = time.time()
        found_block = None
        found_event = threading.Event()
        self.hash_count = 0
        
        def mine_range(start_nonce: int, step: int) -> Optional[Block]:
            nonce = start_nonce
            local_block = Block.from_dict(block.to_dict())
            local_hash_count = 0
            
            while not found_event.is_set() and not self.stop_event.is_set():
                local_block.header.nonce = nonce
                block_hash = local_block.compute_hash()
                
                hash_int = int(block_hash, 16)
                if hash_int < local_block.header.difficulty_target:
                    local_block.hash = block_hash
                    local_block.size = local_block.compute_size()
                    local_block.transaction_count = len(local_block.transactions)
                    return local_block
                
                nonce += step
                local_hash_count += 1
                
                if local_hash_count % 10000 == 0:
                    self.hash_count += 10000
            
            return None
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for i in range(num_threads):
                future = executor.submit(mine_range, i, num_threads)
                futures.append(future)
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    found_block = result
                    found_event.set()
                    break
        
        if found_block:
            elapsed = time.time() - start_time
            
            self.stats.blocks_mined += 1
            self.stats.total_hashes += self.hash_count
            self.stats.total_time += elapsed
            self.stats.last_block_time = elapsed
            self.stats.hash_rate = self.stats.total_hashes / max(self.stats.total_time, 1)
            
            print(f"✅ Block mined in {elapsed:.2f}s with {num_threads} threads")
            print(f"   Nonce: {found_block.header.nonce:,}")
            print(f"   Block hash: {found_block.hash}")
            print(f"   Total hashes: {self.hash_count:,}")
            print(f"   Hash rate: {self.stats.hash_rate:,.0f} H/s")
            print(f"   Transactions: {len(found_block.transactions)}")
            
            return found_block
        
        print("⛏️  Mining stopped")
        return None
    
    # ============================================
    # SUBMIT MINED BLOCK
    # ============================================
    
    def submit_block(self, block: Block) -> Tuple[bool, str]:
        """Submit a mined block to the Chain Manager."""
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        success, message = self.chain_manager.add_block(block)
        
        if success:
            # Remove confirmed transactions from mempool (if not already done)
            self.mempool.confirm_block(block)
            print(f"✅ Block {block.header.block_height} submitted to chain")
        
        return success, message
    
    # ============================================
    # CONTINUOUS MINING - FIXED WITH DUPLICATE DETECTION
    # ============================================
    
    def start_mining(self, continuous: bool = True, num_threads: int = 1, block: Optional[Block] = None) -> None:
        """Start mining continuously."""
        if self.is_mining:
            print("⚠️  Miner already running")
            return
        
        if not self.address:
            print("❌ Mining address not set! Use set_mining_address()")
            return
        
        self.is_mining = True
        self.stop_event.clear()
        
        def mining_loop():
            """
            Main mining loop - FIXED: With duplicate block detection.
            
            VERSION 2.3 CHANGES:
            - Track last submitted block hash
            - Count failed attempts
            - Force new template after too many duplicates
            - Prevent infinite loops
            """
            print(f"🚀 Started mining (continuous={continuous}, easy={self.easy_mode})")
            print(f"🔍 VERSION 2.3 - WITH DUPLICATE PREVENTION")
            
            current_block = block
            last_submitted_hash = None  # Track last submitted block
            failed_attempts = 0          # Count consecutive failures
            max_failed_attempts = 5      # Max failures before forcing new template
            
            while self.is_mining and not self.stop_event.is_set():
                # Create new block template if needed
                if not current_block:
                    current_block = self.create_block_template()
                
                if not current_block:
                    print("❌ Failed to create block template")
                    time.sleep(5)
                    continue
                
                # Check if chain height changed while mining
                current_height = self.chain_manager.get_height()
                if current_block.header.block_height != current_height:
                    print(f"🔄 Chain height changed from {current_block.header.block_height} to {current_height}, refreshing template")
                    current_block = None
                    continue
                
                # Mine the block
                if num_threads > 1:
                    mined = self.mine_block_parallel(current_block, num_threads)
                else:
                    mined = self.mine_block(current_block)
                
                if mined:
                    # FIXED: Check for duplicate block
                    if mined.hash == last_submitted_hash:
                        failed_attempts += 1
                        print(f"⚠️ Duplicate block detected (attempt {failed_attempts}/{max_failed_attempts}), skipping submission")
                        
                        if failed_attempts >= max_failed_attempts:
                            print("🔄 Too many duplicate blocks, forcing new template")
                            current_block = None
                            failed_attempts = 0
                            time.sleep(2)
                            continue
                        
                        time.sleep(1)
                        continue
                    
                    # Submit the block
                    success, message = self.submit_block(mined)
                    
                    if success:
                        print(f"✅ Block {mined.header.block_height} added to chain")
                        current_block = None          # Get new template for next block
                        last_submitted_hash = mined.hash
                        failed_attempts = 0
                    else:
                        print(f"❌ Failed to submit block: {message}")
                        
                        # If validation failed with height mismatch, refresh template
                        if "height" in message.lower():
                            print("🔄 Height mismatch, refreshing template")
                            current_block = None
                            failed_attempts = 0
                        else:
                            # Don't retry the same block
                            last_submitted_hash = mined.hash
                            failed_attempts += 1
                            time.sleep(1)
                else:
                    # No block mined (stopped or error)
                    break
                
                if not continuous:
                    break
            
            self.is_mining = False
            print("⛏️  Mining stopped")
        
        self.mining_thread = threading.Thread(target=mining_loop, daemon=True)
        self.mining_thread.start()
    
    def stop_mining(self) -> None:
        """Stop continuous mining."""
        if not self.is_mining:
            return
        
        print("⛏️  Stopping mining...")
        self.stop_event.set()
        self.is_mining = False
        
        if self.mining_thread:
            self.mining_thread.join(timeout=5)
        
        print("⛏️  Mining stopped")
    
    # ============================================
    # MINING STATISTICS
    # ============================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get mining statistics."""
        return {
            'blocks_mined': self.stats.blocks_mined,
            'total_hashes': self.stats.total_hashes,
            'total_time': self.stats.total_time,
            'last_block_time': self.stats.last_block_time,
            'hash_rate': self.stats.hash_rate,
            'is_mining': self.is_mining,
            'address': self.address,
            'difficulty': self.chain_manager.get_difficulty(),
            'chain_height': self.chain_manager.get_height(),
            'easy_mode': self.easy_mode,
            'version': '2.3',
        }
    
    def get_hash_rate(self) -> float:
        """Get current hash rate."""
        return self.stats.hash_rate
    
    def reset_stats(self) -> None:
        """Reset mining statistics."""
        self.stats = MiningStats()
        self.hash_count = 0
        print("📊 Mining statistics reset")
    
    # ============================================
    # TESTING HELPERS
    # ============================================
    
    def mine_test_block(self, difficulty: Optional[int] = None) -> Optional[Block]:
        """
        Mine a test block with lower difficulty.
        
        FIXED: Ensures coinbase transaction is added to the block.
        """
        print("🔍 VERSION 2.3 - WITH DUPLICATE PREVENTION (mine_test_block)")
        
        if difficulty is None:
            difficulty = settings.EASY_DIFFICULTY
        
        # Get transactions from mempool
        mempool_txs = self.mempool.get_transactions(10)
        print(f"📦 Retrieved {len(mempool_txs)} transactions from mempool")
        
        # Create coinbase transaction (mining reward)
        reward = 50_000_000  # 50 ZARU
        coinbase = create_coinbase_transaction(
            self.address or "TEST_MINER_ADDRESS", 
            reward
        )
        print(f"🔍 Created coinbase: {coinbase.tx_id[:16]}... for {self.address or 'TEST_MINER_ADDRESS'}")
        
        # Add coinbase as first transaction
        all_transactions = [coinbase] + mempool_txs
        print(f"🔍 Total transactions: {len(all_transactions)} (1 coinbase + {len(mempool_txs)} from mempool)")
        
        # Create block
        block = Block()
        block.header = BlockHeader(
            version=1,
            prev_block_hash=self.chain_manager.get_tip_hash(),
            timestamp=int(time.time()),
            difficulty_target=difficulty,
            block_height=self.chain_manager.get_height()
        )
        
        # Add ALL transactions (including coinbase and mempool)
        for tx in all_transactions:
            block.add_transaction(tx)
        
        # Update merkle root
        block.header.merkle_root = block.compute_merkle_root()
        block.hash = block.compute_hash()
        block.size = block.compute_size()
        block.transaction_count = len(block.transactions)
        
        print("🧪 Mining test block...")
        print(f"   Coinbase reward: {reward} satoshis (0.5 ZARU)")
        print(f"   Transactions: {len(block.transactions)} (including coinbase and mempool)")
        print(f"   Block height: {block.header.block_height}")
        print(f"   Mining address: {self.address or 'TEST_MINER_ADDRESS'}")
        
        # Mine with multiple threads
        mined = self.mine_block_parallel(block, num_threads=4)
        
        if mined:
            print("✅ Test block mined!")
            print(f"   Hash: {mined.hash}")
            print(f"   Nonce: {mined.header.nonce}")
            print(f"   Transactions: {len(mined.transactions)}")
            print(f"   Coinbase included: {len([tx for tx in mined.transactions if tx.is_coinbase])}")
        else:
            print("❌ Failed to mine test block")
        
        return mined


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_miner(
    chain_manager: Optional[ChainManager] = None,
    mempool: Optional[Mempool] = None,
    utxo_set: Optional[UTXOSet] = None,
    store=None,
    address: Optional[str] = None,
    easy_mode: bool = True
) -> Miner:
    """Factory function to create a Miner."""
    return Miner(chain_manager, mempool, utxo_set, store, address, easy_mode)


# ============================================
# GLOBAL INSTANCE
# ============================================

miner = Miner(easy_mode=True)


if __name__ == "__main__":
    print("Miner module loaded")
    print(f"Easy mode: {miner.easy_mode}")
    print(f"Difficulty: {miner.chain_manager.get_difficulty()}")