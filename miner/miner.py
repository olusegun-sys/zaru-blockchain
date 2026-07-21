"""
ZARU Miner Module
=================
Handles Proof of Work mining and block creation.

ADDED: Easy mode for bot mining (reduced difficulty)
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
    """
    
    def __init__(
        self,
        chain_manager: Optional[ChainManager] = None,
        mempool: Optional[Mempool] = None,
        utxo_set: Optional[UTXOSet] = None,
        store=None,
        address: Optional[str] = None,
        easy_mode: bool = True  # NEW: Easy mode for bots
    ):
        """
        Initialize the miner.
        
        Args:
            easy_mode: If True, uses 10,000x easier difficulty
        """
        self.store = store if store else db_store
        self.chain_manager = chain_manager if chain_manager else ChainManager(self.store)
        self.mempool = mempool if mempool else Mempool(self.chain_manager.utxo_set, self.store)
        self.utxo_set = utxo_set if utxo_set else self.chain_manager.utxo_set
        
        self.address = address
        self.is_mining = False
        self.mining_thread = None
        self.stop_event = threading.Event()
        
        # Stats
        self.stats = MiningStats()
        self.hash_count = 0
        self.last_hash_rate_check = time.time()
        
        # NEW: Easy mode
        self.easy_mode = easy_mode
        if easy_mode:
            print("🎯 EASY MODE ENABLED - Mining difficulty reduced 10,000x")
            self.chain_manager._difficulty = settings.EASY_DIFFICULTY
            self.chain_manager.store.put_chain_state('difficulty', settings.EASY_DIFFICULTY)
        
        print(f"✅ Miner initialized")
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
    
    def create_block_template(self) -> Optional[Block]:
        """Create a candidate block for mining."""
        if not self.address:
            print("❌ Mining address not set! Use set_mining_address()")
            return None
        
        transactions = self.mempool.prepare_for_mining()
        
        # Mining reward - 50 ZARU (50000000 satoshis)
        reward = 50_000_000
        coinbase = create_coinbase_transaction(self.address, reward)
        all_transactions = [coinbase] + transactions
        
        tip_hash = self.chain_manager.get_tip_hash()
        height = self.chain_manager.get_height()
        difficulty = self.chain_manager.get_difficulty()
        
        block = Block()
        block.header = BlockHeader(
            version=1,
            prev_block_hash=tip_hash,
            timestamp=int(time.time()),
            difficulty_target=difficulty,
            block_height=height
        )
        
        for tx in all_transactions:
            block.add_transaction(tx)
        
        block.header.merkle_root = block.compute_merkle_root()
        block.hash = block.compute_hash()
        block.size = block.compute_size()
        block.transaction_count = len(block.transactions)
        
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
        
        def mine_range(start_nonce: int, step: int) -> Optional[Block]:
            nonce = start_nonce
            local_block = Block.from_dict(block.to_dict())
            
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
                
                if nonce % 10000 == 0:
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
            self.mempool.confirm_block(block)
            print(f"✅ Block {block.header.block_height} submitted to chain")
        
        return success, message
    
    # ============================================
    # CONTINUOUS MINING
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
            print(f"🚀 Started mining (continuous={continuous}, easy={self.easy_mode})")
            
            while self.is_mining and not self.stop_event.is_set():
                if not block:
                    block = self.create_block_template()
                
                if not block:
                    print("❌ Failed to create block template")
                    time.sleep(5)
                    continue
                
                if num_threads > 1:
                    mined = self.mine_block_parallel(block, num_threads)
                else:
                    mined = self.mine_block(block)
                
                if mined:
                    success, message = self.submit_block(mined)
                    
                    if success:
                        print(f"✅ Block {mined.header.block_height} added to chain")
                        block = None
                    else:
                        print(f"❌ Failed to submit block: {message}")
                        time.sleep(1)
                else:
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
        """Mine a test block with lower difficulty."""
        if difficulty is None:
            difficulty = settings.EASY_DIFFICULTY
        
        transactions = []
        try:
            transactions = self.mempool.get_transactions(10)
        except:
            pass
        
        reward = 50_000_000
        coinbase = create_coinbase_transaction(
            self.address or "TEST_MINER_ADDRESS", 
            reward
        )
        
        all_transactions = [coinbase] + transactions
        
        block = Block()
        block.header = BlockHeader(
            version=1,
            prev_block_hash=self.chain_manager.get_tip_hash(),
            timestamp=int(time.time()),
            difficulty_target=difficulty,
            block_height=self.chain_manager.get_height()
        )
        
        for tx in all_transactions:
            block.add_transaction(tx)
        
        block.header.merkle_root = block.compute_merkle_root()
        block.hash = block.compute_hash()
        block.size = block.compute_size()
        block.transaction_count = len(block.transactions)
        
        print("🧪 Mining test block...")
        mined = self.mine_block_parallel(block, num_threads=4)
        
        if mined:
            print("✅ Test block mined!")
            print(f"   Hash: {mined.hash}")
            print(f"   Nonce: {mined.header.nonce}")
        
        return mined


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_miner(chain_manager=None, mempool=None, utxo_set=None, store=None, address=None, easy_mode=True) -> Miner:
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