"""
ZARU Miner Module
=================
Handles Proof of Work mining and block creation.

WHY: The miner is the "engine" that creates new blocks.
It takes transactions from the mempool, builds a candidate block,
and performs Proof of Work to find a valid nonce.

THINK OF IT LIKE: A gold miner panning for gold.
The miner sifts through transactions (dirt) to find the most
profitable ones, packages them into a block (nugget), and
does the hard work (PoW) to validate it.

HOW IT WORKS:
1. Get transactions from mempool
2. Create a candidate block with those transactions
3. Perform Proof of Work (find valid nonce)
4. Submit mined block to Chain Manager
5. Collect mining reward
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
    Handles Proof of Work mining.
    
    The miner creates candidate blocks and finds valid nonces
    through Proof of Work. It supports multi-threaded mining
    and integrates with the mempool and chain manager.
    """
    
    def __init__(
        self,
        chain_manager: Optional[ChainManager] = None,
        mempool: Optional[Mempool] = None,
        utxo_set: Optional[UTXOSet] = None,
        store=None,
        address: Optional[str] = None
    ):
        """
        Initialize the miner.
        
        Args:
            chain_manager: Chain Manager instance (creates new if None)
            mempool: Mempool instance (creates new if None)
            utxo_set: UTXO set instance (creates new if None)
            store: Database store instance (uses global if None)
            address: Mining reward address (required for mining)
        """
        self.store = store if store else db_store
        self.chain_manager = chain_manager if chain_manager else ChainManager(self.store)
        self.mempool = mempool if mempool else Mempool(self.chain_manager.utxo_set, self.store)
        self.utxo_set = utxo_set if utxo_set else self.chain_manager.utxo_set
        
        # Mining configuration
        self.address = address
        self.is_mining = False
        self.mining_thread = None
        self.stop_event = threading.Event()
        
        # Statistics
        self.stats = MiningStats()
        
        # Performance
        self.hash_count = 0
        self.last_hash_rate_check = time.time()
        
        print(f"✅ Miner initialized")
        print(f"   Address: {address or 'Not set - mining disabled'}")
        print(f"   Difficulty: {self.chain_manager.get_difficulty()}")
    
    # ============================================
    # MINING CONFIGURATION
    # ============================================
    
    def set_mining_address(self, address: str) -> None:
        """
        Set the mining reward address.
        
        Args:
            address: Address to receive mining rewards
        
        WHY: Miners need an address to receive block rewards.
        """
        self.address = address
        print(f"✅ Mining address set: {address}")
    
    def set_difficulty(self, difficulty: int) -> None:
        """
        Manually set mining difficulty.
        
        Args:
            difficulty: New difficulty target
        
        WHY: Useful for testing or manual adjustment.
        """
        print(f"⚙️  Setting difficulty to {difficulty}")
        self.chain_manager._difficulty = difficulty
        self.chain_manager.store.put_chain_state('difficulty', difficulty)
    
    # ============================================
    # BLOCK CREATION
    # ============================================
    
    def create_block_template(self) -> Optional[Block]:
        """
        Create a candidate block for mining.
        
        Returns:
            Optional[Block]: Block template ready for mining
        
        WHY: This creates a block with transactions from the mempool
        that is ready for Proof of Work.
        """
        # Check if mining address is set
        if not self.address:
            print("❌ Mining address not set! Use set_mining_address()")
            return None
        
        # Get transactions from mempool
        transactions = self.mempool.prepare_for_mining()
        
        # Create coinbase transaction (mining reward)
        # Reward = 50 ZARU (simplified - no halving yet)
        reward = 50_000_000  # 50 ZARU in satoshis
        coinbase = create_coinbase_transaction(self.address, reward)
        
        # Add coinbase as first transaction
        all_transactions = [coinbase] + transactions
        
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
        
        # Add transactions
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
        print(f"   Transactions: {len(block.transactions)}")
        print(f"   Difficulty: {difficulty}")
        print(f"   Reward: {reward} satoshis")
        
        return block
    
    # ============================================
    # PROOF OF WORK
    # ============================================
    
    def mine_block(self, block: Optional[Block] = None) -> Optional[Block]:
        """
        Mine a single block (find valid nonce).
        
        Args:
            block: Block to mine (creates new template if None)
        
        Returns:
            Optional[Block]: Mined block or None if mining failed
        
        WHY: This is the core mining function. It tries different
        nonce values until it finds one that produces a valid hash.
        """
        # Create block template if not provided
        if block is None:
            block = self.create_block_template()
            if not block:
                return None
        
        print(f"⛏️  Mining block {block.header.block_height}...")
        print(f"   Target: {block.header.difficulty_target}")
        
        start_time = time.time()
        attempts = 0
        
        # Mining loop
        while not self.stop_event.is_set():
            # Try current nonce
            block.header.nonce = attempts
            block_hash = block.compute_hash()
            
            # Check if hash meets target
            hash_int = int(block_hash, 16)
            if hash_int < block.header.difficulty_target:
                # Found a valid nonce!
                elapsed = time.time() - start_time
                block.hash = block_hash
                block.size = block.compute_size()
                block.transaction_count = len(block.transactions)
                
                # Update statistics
                self.stats.blocks_mined += 1
                self.stats.total_hashes += attempts
                self.stats.total_time += elapsed
                self.stats.last_block_time = elapsed
                self.stats.attempts = attempts
                self.stats.hash_rate = self.stats.total_hashes / max(self.stats.total_time, 1)
                
                print(f"✅ Block mined in {elapsed:.2f}s after {attempts:,} attempts")
                print(f"   Nonce: {attempts}")
                print(f"   Block hash: {block_hash}")
                print(f"   Hash rate: {self.stats.hash_rate:,.0f} hashes/second")
                
                return block
            
            attempts += 1
            
            # Log progress occasionally
            if attempts % 100000 == 0:
                print(f"   Attempts: {attempts:,}, Current hash: {block_hash[:16]}...")
            
            # Update hash rate
            self.hash_count += 1
        
        print("⛏️  Mining stopped")
        return None
    
    def mine_block_parallel(
        self, 
        block: Optional[Block] = None,
        num_threads: int = 4
    ) -> Optional[Block]:
        """
        Mine a block using multiple threads.
        
        Args:
            block: Block to mine (creates new template if None)
            num_threads: Number of threads to use
        
        Returns:
            Optional[Block]: Mined block or None if mining failed
        
        WHY: Multi-threading speeds up mining by trying
        different nonces simultaneously.
        """
        # Create block template if not provided
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
            """Mine a range of nonces in a thread."""
            nonce = start_nonce
            local_block = Block.from_dict(block.to_dict())
            
            while not found_event.is_set() and not self.stop_event.is_set():
                local_block.header.nonce = nonce
                block_hash = local_block.compute_hash()
                
                hash_int = int(block_hash, 16)
                if hash_int < local_block.header.difficulty_target:
                    # Found!
                    local_block.hash = block_hash
                    local_block.size = local_block.compute_size()
                    local_block.transaction_count = len(local_block.transactions)
                    return local_block
                
                nonce += step
                
                # Update stats periodically
                if nonce % 10000 == 0:
                    self.hash_count += 10000
            
            return None
        
        # Start mining threads
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for i in range(num_threads):
                future = executor.submit(mine_range, i, num_threads)
                futures.append(future)
            
            # Wait for any thread to find a block
            for future in as_completed(futures):
                result = future.result()
                if result:
                    found_block = result
                    found_event.set()
                    break
        
        if found_block:
            elapsed = time.time() - start_time
            
            # Update statistics
            self.stats.blocks_mined += 1
            self.stats.total_hashes += self.hash_count
            self.stats.total_time += elapsed
            self.stats.last_block_time = elapsed
            self.stats.hash_rate = self.stats.total_hashes / max(self.stats.total_time, 1)
            
            print(f"✅ Block mined in {elapsed:.2f}s with {num_threads} threads")
            print(f"   Nonce: {found_block.header.nonce:,}")
            print(f"   Block hash: {found_block.hash}")
            print(f"   Total hashes: {self.hash_count:,}")
            print(f"   Hash rate: {self.stats.hash_rate:,.0f} hashes/second")
            
            return found_block
        
        print("⛏️  Mining stopped")
        return None
    
    # ============================================
    # SUBMIT MINED BLOCK
    # ============================================
    
    def submit_block(self, block: Block) -> Tuple[bool, str]:
        """
        Submit a mined block to the Chain Manager.
        
        Args:
            block: Mined block to submit
        
        Returns:
            Tuple[bool, str]: (success, message)
        
        WHY: After mining, we submit the block to the chain.
        This integrates the block into the blockchain.
        """
        # Check if block is mined (has valid PoW)
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        # Submit to Chain Manager
        success, message = self.chain_manager.add_block(block)
        
        if success:
            # Remove transactions from mempool
            self.mempool.confirm_block(block)
            print(f"✅ Block {block.header.block_height} submitted to chain")
        
        return success, message
    
    # ============================================
    # CONTINUOUS MINING
    # ============================================
    
    def start_mining(
        self,
        continuous: bool = True,
        num_threads: int = 1,
        block: Optional[Block] = None
    ) -> None:
        """
        Start mining continuously.
        
        Args:
            continuous: Whether to mine continuously (default: True)
            num_threads: Number of threads to use
            block: Block to mine (creates new template if None)
        
        WHY: For production mining, we want to continuously
        mine new blocks as transactions arrive.
        """
        if self.is_mining:
            print("⚠️  Miner already running")
            return
        
        if not self.address:
            print("❌ Mining address not set! Use set_mining_address()")
            return
        
        self.is_mining = True
        self.stop_event.clear()
        
        def mining_loop():
            """Main mining loop."""
            print(f"🚀 Started mining (continuous={continuous})")
            
            while self.is_mining and not self.stop_event.is_set():
                # Check if we're still on the best chain
                # If not, create a new block template
                if not block:
                    block = self.create_block_template()
                
                if not block:
                    print("❌ Failed to create block template")
                    time.sleep(5)
                    continue
                
                # Mine the block
                if num_threads > 1:
                    mined = self.mine_block_parallel(block, num_threads)
                else:
                    mined = self.mine_block(block)
                
                if mined:
                    # Submit the block
                    success, message = self.submit_block(mined)
                    
                    if success:
                        print(f"✅ Block {mined.header.block_height} added to chain")
                        
                        # Update chain state
                        new_difficulty = self.chain_manager.get_difficulty()
                        print(f"   New difficulty: {new_difficulty}")
                        
                        # Reset block for next mining
                        block = None
                    else:
                        print(f"❌ Failed to submit block: {message}")
                        time.sleep(1)
                else:
                    # Mining was stopped
                    break
                
                # If not continuous, stop after one block
                if not continuous:
                    break
            
            self.is_mining = False
            print("⛏️  Mining stopped")
        
        # Start mining thread
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
        """
        Get mining statistics.
        
        Returns:
            Dict: Mining statistics
        """
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
        }
    
    def get_hash_rate(self) -> float:
        """
        Get current hash rate.
        
        Returns:
            float: Hash rate in hashes per second
        """
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
        
        Args:
            difficulty: Custom difficulty (lower = easier to mine)
        
        Returns:
            Optional[Block]: Mined block
        
        WHY: For testing, we want to mine quickly.
        Lower difficulty means faster mining.
        """
        if difficulty is None:
            # Use a much lower target for testing
            difficulty = 0x0000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        
        # Get transactions from mempool
        transactions = []
        try:
            transactions = self.mempool.get_transactions(10)
        except:
            pass
        
        # Create coinbase
        reward = 50_000_000
        coinbase = create_coinbase_transaction(
            self.address or "TEST_MINER_ADDRESS", 
            reward
        )
        
        all_transactions = [coinbase] + transactions
        
        # Create block
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
        
        # Mine with 4 threads for speed
        mined = self.mine_block_parallel(block, num_threads=4)
        
        if mined:
            print("✅ Test block mined!")
            print(f"   Hash: {mined.hash}")
            print(f"   Nonce: {mined.header.nonce}")
        
        return mined


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_miner(
    chain_manager: Optional[ChainManager] = None,
    mempool: Optional[Mempool] = None,
    utxo_set: Optional[UTXOSet] = None,
    store=None,
    address: Optional[str] = None
) -> Miner:
    """
    Factory function to create a Miner.
    
    WHY: Makes it easy to initialize the Miner
    with either default or custom dependencies.
    """
    return Miner(chain_manager, mempool, utxo_set, store, address)


# ============================================
# GLOBAL INSTANCE
# ============================================

# Create a global Miner instance
miner = Miner()


# ============================================
# TEST FUNCTIONS
# ============================================

def test_miner():
    """
    Quick test to verify Miner is working.
    """
    print("\n🧪 Testing Miner...")
    
    # 1. Set mining address
    test_address = "TEST_MINER_ADDRESS_001"
    miner.set_mining_address(test_address)
    print(f"1. Mining address set: {test_address}")
    
    # 2. Create block template
    block = miner.create_block_template()
    print(f"2. Block template created: Height {block.header.block_height if block else 'None'}")
    
    if block:
        # 3. Mine test block (with lower difficulty)
        mined = miner.mine_test_block()
        print(f"3. Test block mined: {mined.hash[:10] if mined else 'Failed'}")
        
        if mined:
            # 4. Get stats
            stats = miner.get_stats()
            print(f"4. Mining stats:")
            print(f"   Blocks mined: {stats['blocks_mined']}")
            print(f"   Hash rate: {stats['hash_rate']:,.0f} H/s")
    
    print("\n✅ Miner test complete")
    return True


if __name__ == "__main__":
    test_miner()