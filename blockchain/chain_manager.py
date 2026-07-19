"""
ZARU Chain Manager Module
=========================
Manages the blockchain - adding blocks, handling forks, and maintaining chain state.

WHY: The Chain Manager is the brain of the blockchain. It:
- Validates new blocks before adding them
- Handles chain reorganizations (forks)
- Maintains the "best chain" (longest valid chain)
- Tracks chain state (tip, height, difficulty)

THINK OF IT LIKE: A librarian who manages a collection of books (blocks).
They ensure new books are authentic, maintain the correct order,
and handle cases where multiple books claim to be the same page.
"""

import time
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path

from config import settings
from blockchain.block import Block, BlockHeader, create_genesis_block, calculate_difficulty
from blockchain.transaction import Transaction
from blockchain.utxo import UTXOSet
from database import store as db_store


class ChainManager:
    """
    Manages the blockchain - the authoritative source of chain state.
    
    The Chain Manager maintains:
    1. The current best chain (longest valid chain)
    2. Block validation rules
    3. Fork handling (chain reorganizations)
    4. Chain state (tip, height, difficulty)
    
    HOW IT WORKS:
    - When a new block arrives, we validate it
    - If it extends the best chain, we add it
    - If it creates a fork, we check if it's longer than the best chain
    - If it is, we reorganize (switch to the longer chain)
    """
    
    def __init__(self, store=None, utxo_set=None):
        """
        Initialize the Chain Manager.
        
        Args:
            store: Database store instance (uses global if None)
            utxo_set: UTXO set instance (creates new if None)
        """
        self.store = store if store else db_store
        self.utxo_set = utxo_set if utxo_set else UTXOSet(self.store)
        
        # Chain state cache
        self._tip_hash = None
        self._tip_height = None
        self._difficulty = None
        
        # Initialize chain
        self._initialize_chain()
        
        print(f"✅ Chain Manager initialized: Height {self.get_height()}, Tip: {self.get_tip_hash()[:10]}...")
    
    # ============================================
    # INITIALIZATION
    # ============================================
    
    def _initialize_chain(self) -> None:
        """
        Initialize the blockchain.
        
        If the chain is empty, create the genesis block.
        If the chain exists, load the current state.
        """
        # Check if chain exists
        height = self.store.get_chain_height()
        
        if height == 0:
            print("⛓️  No blockchain found. Creating genesis block...")
            self._create_genesis_chain()
        else:
            print(f"⛓️  Loading existing blockchain (height: {height})...")
            self._load_chain_state()
    
    def _create_genesis_chain(self) -> None:
        """
        Create and initialize the genesis block.
        
        WHY: The genesis block is the first block in the chain.
        It establishes the initial coin supply and sets the foundation.
        """
        # Create genesis block
        genesis = create_genesis_block()
        
        # Apply to UTXO set
        self.utxo_set.apply_block(genesis)
        
        # Store the block
        self.store.put_block(genesis.hash, genesis.to_dict())
        
        # Store chain state
        self.store.put_chain_state('chain_tip', genesis.hash)
        self.store.put_chain_state('chain_height', genesis.header.block_height + 1)
        self.store.put_chain_state('difficulty', genesis.header.difficulty_target)
        
        # Update cache
        self._tip_hash = genesis.hash
        self._tip_height = genesis.header.block_height + 1
        self._difficulty = genesis.header.difficulty_target
        
        print(f"✅ Genesis block created: {genesis.hash[:10]}...")
        print(f"   Initial supply: {settings.INITIAL_COIN_SUPPLY} ZARU")
    
    def _load_chain_state(self) -> None:
        """Load the current chain state from the database."""
        self._tip_hash = self.store.get_chain_state('chain_tip')
        self._tip_height = self.store.get_chain_state('chain_height')
        self._difficulty = self.store.get_chain_state('difficulty')
        
        if self._tip_hash is None or self._tip_height is None:
            # Fallback - recalculate from blocks
            latest = self.store.get_latest_block()
            if latest:
                self._tip_hash = latest['hash']
                self._tip_height = latest['header']['block_height'] + 1
                self._difficulty = latest['header']['difficulty_target']
    
    # ============================================
    # CHAIN QUERY METHODS
    # ============================================
    
    def get_tip_hash(self) -> Optional[str]:
        """Get the hash of the current chain tip."""
        if self._tip_hash is None:
            self._tip_hash = self.store.get_chain_state('chain_tip')
        return self._tip_hash
    
    def get_height(self) -> int:
        """Get the current chain height (number of blocks)."""
        if self._tip_height is None:
            self._tip_height = self.store.get_chain_state('chain_height')
            if self._tip_height is None:
                self._tip_height = self.store.get_chain_height()
        return self._tip_height if self._tip_height else 0
    
    def get_difficulty(self) -> int:
        """Get the current mining difficulty."""
        if self._difficulty is None:
            self._difficulty = self.store.get_chain_state('difficulty')
            if self._difficulty is None:
                self._difficulty = settings.INITIAL_DIFFICULTY
        return self._difficulty
    
    def get_block(self, block_hash: str) -> Optional[Block]:
        """Get a block by hash."""
        data = self.store.get_block(block_hash)
        if data:
            return Block.from_dict(data)
        return None
    
    def get_block_by_height(self, height: int) -> Optional[Block]:
        """Get a block by height."""
        data = self.store.get_block_by_height(height)
        if data:
            return Block.from_dict(data)
        return None
    
    def get_blocks(self, start_height: int, end_height: int) -> List[Block]:
        """Get a range of blocks."""
        blocks = []
        for height in range(start_height, end_height + 1):
            block = self.get_block_by_height(height)
            if block:
                blocks.append(block)
        return blocks
    
    def get_best_chain(self) -> List[Block]:
        """Get all blocks in the current best chain."""
        height = self.get_height()
        blocks = []
        for i in range(height):
            block = self.get_block_by_height(i)
            if block:
                blocks.append(block)
        return blocks
    
    # ============================================
    # BLOCK VALIDATION
    # ============================================
    
    def validate_block(self, block: Block) -> Tuple[bool, str]:
        """
        Validate a block before adding it to the chain.
        
        Args:
            block: Block to validate
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        
        WHY: Before adding a block, we must ensure it's valid.
        This prevents invalid blocks from entering the chain.
        """
        # 1. Check block is not None
        if block is None:
            return False, "Block is None"
        
        # 2. Check block hash is valid
        if not block.hash or len(block.hash) != 64:
            return False, f"Invalid block hash: {block.hash}"
        
        # 3. Check block height is correct
        expected_height = self.get_height()
        if block.header.block_height != expected_height:
            return False, f"Invalid block height: expected {expected_height}, got {block.header.block_height}"
        
        # 4. Check previous block hash matches tip
        tip_hash = self.get_tip_hash()
        if block.header.prev_block_hash != tip_hash:
            return False, f"Previous block hash mismatch: expected {tip_hash}, got {block.header.prev_block_hash}"
        
        # 5. Verify block meets difficulty target
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        # 6. Verify merkle root
        computed_root = block.compute_merkle_root()
        if computed_root != block.header.merkle_root:
            return False, "Merkle root mismatch"
        
        # 7. Check block size
        if block.size > settings.MAX_BLOCK_SIZE_BYTES:
            return False, f"Block size {block.size} exceeds limit {settings.MAX_BLOCK_SIZE_BYTES}"
        
        # 8. Validate all transactions
        for i, tx in enumerate(block.transactions):
            is_valid, error = self.utxo_set.validate_transaction(tx, block.header.block_height)
            if not is_valid:
                return False, f"Transaction {i} invalid: {error}"
        
        # 9. Check coinbase is first transaction
        if block.transactions and not block.transactions[0].is_coinbase:
            return False, "First transaction must be coinbase"
        
        # 10. Validate coinbase reward
        if block.transactions and block.transactions[0].is_coinbase:
            coinbase = block.transactions[0]
            # Calculate block reward (simplified - halving every 210,000 blocks)
            # For now, just check it doesn't exceed supply
            if coinbase.outputs[0].amount > settings.INITIAL_COIN_SUPPLY:
                return False, "Coinbase reward exceeds supply limit"
        
        return True, "Block is valid"
    
    # ============================================
    # BLOCK ADDITION
    # ============================================
    
    def add_block(self, block: Block) -> Tuple[bool, str]:
        """
        Add a block to the blockchain.
        
        Args:
            block: Block to add
        
        Returns:
            Tuple[bool, str]: (success, message)
        
        HOW IT WORKS:
        1. Validate the block
        2. Check if it extends the best chain
        3. If it does, add it to the best chain
        4. If it creates a fork, handle the reorganization
        
        WHY: This is the main entry point for adding blocks.
        It handles all the complexity of validation and chain management.
        """
        try:
            # 1. Validate block
            is_valid, error = self.validate_block(block)
            if not is_valid:
                return False, f"Block validation failed: {error}"
            
            # 2. Check if block extends best chain
            tip_hash = self.get_tip_hash()
            if block.header.prev_block_hash == tip_hash:
                # Block extends best chain - simple case
                return self._add_to_best_chain(block)
            
            # 3. Check if block belongs to a fork
            # Find the fork point
            fork_point = self._find_fork_point(block)
            if fork_point is None:
                return False, "Block does not connect to any known chain"
            
            # 4. Check if fork is longer than best chain
            fork_blocks = self._get_chain_from_block(block)
            current_blocks = self.get_blocks(fork_point, self.get_height() - 1)
            
            if len(fork_blocks) <= len(current_blocks):
                return False, f"Fork is not longer than current chain ({len(fork_blocks)} <= {len(current_blocks)})"
            
            # 5. Reorganize to the longer fork
            return self._handle_reorganization(current_blocks, fork_blocks)
            
        except Exception as e:
            print(f"❌ Error adding block: {e}")
            return False, f"Error: {str(e)}"
    
    def _add_to_best_chain(self, block: Block) -> Tuple[bool, str]:
        """
        Add a block to the best chain (simple case).
        
        Args:
            block: Block to add
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # 1. Apply block to UTXO set
            if not self.utxo_set.apply_block(block):
                return False, "Failed to apply block to UTXO set"
            
            # 2. Store block in database
            if not self.store.put_block(block.hash, block.to_dict()):
                return False, "Failed to store block in database"
            
            # 3. Update chain state
            new_height = self.get_height() + 1
            self.store.put_chain_state('chain_tip', block.hash)
            self.store.put_chain_state('chain_height', new_height)
            
            # 4. Update difficulty (if needed)
            if new_height % settings.DIFFICULTY_ADJUSTMENT_INTERVAL == 0:
                # Calculate new difficulty
                prev_block = self.get_block_by_height(new_height - settings.DIFFICULTY_ADJUSTMENT_INTERVAL - 1)
                if prev_block:
                    new_difficulty = calculate_difficulty(block, prev_block)
                    self.store.put_chain_state('difficulty', new_difficulty)
                    self._difficulty = new_difficulty
            
            # 5. Update cache
            self._tip_hash = block.hash
            self._tip_height = new_height
            
            print(f"✅ Block {block.header.block_height} added to best chain")
            print(f"   Hash: {block.hash[:10]}...")
            print(f"   Tx: {len(block.transactions)}")
            print(f"   New height: {new_height}")
            
            return True, "Block added to best chain"
            
        except Exception as e:
            print(f"❌ Error adding block to best chain: {e}")
            return False, f"Error: {str(e)}"
    
    def _find_fork_point(self, block: Block) -> Optional[int]:
        """
        Find where a block connects to the existing chain.
        
        Args:
            block: Block to check
        
        Returns:
            Optional[int]: Height of the fork point, or None if not found
        
        WHY: To handle forks, we need to find where the new chain
        diverges from the current chain.
        """
        current = block
        
        # Follow the chain backwards until we find a common block
        while current:
            # Check if this block exists in our chain
            existing = self.get_block(current.hash)
            if existing:
                return current.header.block_height
            
            # Check if we've gone back too far
            if current.header.block_height == 0:
                break
            
            # Get previous block
            prev = self.get_block(current.header.prev_block_hash)
            if not prev:
                break
            current = prev
        
        return None
    
    def _get_chain_from_block(self, block: Block) -> List[Block]:
        """
        Get the full chain starting from a block.
        
        Args:
            block: Block to start from
        
        Returns:
            List[Block]: Chain from genesis to the given block
        """
        chain = []
        current = block
        
        # Follow chain backwards to genesis
        blocks = []
        while current:
            blocks.append(current)
            if current.header.prev_block_hash == "0" * 64:
                break
            current = self.get_block(current.header.prev_block_hash)
            if not current:
                break
        
        # Reverse to get genesis → block order
        return list(reversed(blocks))
    
    # ============================================
    # CHAIN REORGANIZATION
    # ============================================
    
    def _handle_reorganization(
        self, 
        old_chain: List[Block], 
        new_chain: List[Block]
    ) -> Tuple[bool, str]:
        """
        Handle a chain reorganization (fork resolution).
        
        Args:
            old_chain: Blocks being removed (old chain)
            new_chain: Blocks being added (new chain)
        
        Returns:
            Tuple[bool, str]: (success, message)
        
        WHY: When we find a longer fork, we need to:
        1. Rollback the UTXO set to the fork point
        2. Apply the new blocks to the UTXO set
        3. Update the chain state
        
        THIS IS CRITICAL FOR CONSENSUS!
        """
        try:
            print(f"🔄 Chain reorganization starting...")
            print(f"   Removing {len(old_chain)} blocks")
            print(f"   Adding {len(new_chain)} blocks")
            
            # 1. Rollback old chain (remove from UTXO set)
            for block in reversed(old_chain):
                self.utxo_set._rollback_block(block)
                print(f"   Rolled back block {block.header.block_height}")
            
            # 2. Apply new chain to UTXO set
            for block in new_chain:
                if not self.utxo_set.apply_block(block):
                    # Something went wrong - this is a critical error
                    print(f"❌ Failed to apply block {block.header.block_height} during reorg")
                    # Attempt to recover by rolling back
                    for b in reversed(new_chain):
                        self.utxo_set._rollback_block(b)
                    return False, "Reorg failed during apply phase"
                print(f"   Applied block {block.header.block_height}")
            
            # 3. Update chain state
            tip_block = new_chain[-1]
            new_height = tip_block.header.block_height + 1
            
            self.store.put_chain_state('chain_tip', tip_block.hash)
            self.store.put_chain_state('chain_height', new_height)
            
            # 4. Update cache
            self._tip_hash = tip_block.hash
            self._tip_height = new_height
            
            # 5. Update difficulty
            if new_height % settings.DIFFICULTY_ADJUSTMENT_INTERVAL == 0:
                prev_block = self.get_block_by_height(new_height - settings.DIFFICULTY_ADJUSTMENT_INTERVAL - 1)
                if prev_block:
                    new_difficulty = calculate_difficulty(tip_block, prev_block)
                    self.store.put_chain_state('difficulty', new_difficulty)
                    self._difficulty = new_difficulty
            
            print(f"✅ Chain reorganization complete!")
            print(f"   New height: {new_height}")
            print(f"   New tip: {tip_block.hash[:10]}...")
            
            return True, "Chain reorganization successful"
            
        except Exception as e:
            print(f"❌ Error during reorganization: {e}")
            return False, f"Reorg error: {str(e)}"
    
    # ============================================
    # CHAIN VERIFICATION
    # ============================================
    
    def verify_chain(self) -> Tuple[bool, str]:
        """
        Verify the entire blockchain is valid.
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        
        WHY: This is used for node startup and debugging.
        It ensures the chain hasn't been corrupted.
        """
        print("🔍 Verifying entire blockchain...")
        
        height = self.get_height()
        if height == 0:
            return False, "Chain is empty"
        
        # Check each block
        for i in range(height):
            block = self.get_block_by_height(i)
            if not block:
                return False, f"Block {i} not found"
            
            # Verify block
            is_valid, error = self.verify_block_chain(block)
            if not is_valid:
                return False, f"Block {i} invalid: {error}"
            
            if i % 100 == 0:
                print(f"   Verified block {i}/{height}")
        
        print(f"✅ Chain verification complete: {height} blocks valid")
        return True, "Chain is valid"
    
    def verify_block_chain(self, block: Block) -> Tuple[bool, str]:
        """
        Verify a block in the context of the chain.
        
        Args:
            block: Block to verify
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        # 1. Verify block hash matches
        computed_hash = block.compute_hash()
        if computed_hash != block.hash:
            return False, f"Block hash mismatch: computed {computed_hash}, stored {block.hash}"
        
        # 2. Check previous block exists (except genesis)
        if block.header.block_height > 0:
            prev = self.get_block(block.header.prev_block_hash)
            if not prev:
                return False, "Previous block not found"
            if prev.header.block_height != block.header.block_height - 1:
                return False, "Block height mismatch with previous block"
        
        # 3. Verify merkle root
        computed_root = block.compute_merkle_root()
        if computed_root != block.header.merkle_root:
            return False, "Merkle root mismatch"
        
        # 4. Verify PoW
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        return True, "Block is valid"
    
    # ============================================
    # MINING SUPPORT
    # ============================================
    
    def get_next_block_template(self, transactions: List[Transaction]) -> Block:
        """
        Create a template for the next block to be mined.
        
        Args:
            transactions: List of transactions to include
        
        Returns:
            Block: Block template ready for mining
        
        WHY: Miners need a template to know what to mine.
        This includes the current difficulty, previous block hash,
        and a list of transactions.
        """
        # Create new block
        block = Block()
        
        # Set header fields
        block.header.block_height = self.get_height()
        block.header.prev_block_hash = self.get_tip_hash()
        block.header.difficulty_target = self.get_difficulty()
        block.header.timestamp = int(time.time())
        
        # Add transactions
        for tx in transactions:
            block.add_transaction(tx)
        
        # Compute merkle root
        block.header.merkle_root = block.compute_merkle_root()
        
        # Compute block hash
        block.hash = block.compute_hash()
        block.size = block.compute_size()
        block.transaction_count = len(block.transactions)
        
        return block
    
    def submit_mined_block(self, block: Block) -> Tuple[bool, str]:
        """
        Submit a mined block to the chain.
        
        Args:
            block: Mined block to submit
        
        Returns:
            Tuple[bool, str]: (success, message)
        
        WHY: Miners submit their work here.
        This is the bridge between mining and chain management.
        """
        # Verify the block meets difficulty
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        # Add the block to the chain
        return self.add_block(block)
    
    # ============================================
    # STATISTICS
    # ============================================
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the blockchain.
        
        Returns:
            Dict: Chain statistics
        """
        height = self.get_height()
        tip_hash = self.get_tip_hash()
        
        # Get latest block
        latest = self.get_block_by_height(height - 1) if height > 0 else None
        
        # Calculate total UTXOs
        utxo_count = self.utxo_set.get_utxo_count()
        
        # Calculate total supply (from UTXO set)
        # This is approximate without iterating all UTXOs
        total_supply = settings.INITIAL_COIN_SUPPLY
        
        return {
            'height': height,
            'tip_hash': tip_hash,
            'difficulty': self.get_difficulty(),
            'utxo_count': utxo_count,
            'total_supply': total_supply,
            'latest_block_time': latest.header.timestamp if latest else None,
            'latest_block_hash': latest.hash if latest else None,
        }


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_chain_manager(store=None, utxo_set=None) -> ChainManager:
    """
    Factory function to create a Chain Manager.
    
    WHY: Makes it easy to initialize the Chain Manager
    with either default or custom dependencies.
    """
    return ChainManager(store, utxo_set)


# ============================================
# GLOBAL INSTANCE
# ============================================

# Create a global Chain Manager instance
chain_manager = ChainManager()


# ============================================
# TEST FUNCTIONS
# ============================================

def test_chain_manager():
    """
    Quick test to verify Chain Manager is working.
    """
    print("\n🧪 Testing Chain Manager...")
    
    # 1. Check chain state
    height = chain_manager.get_height()
    tip = chain_manager.get_tip_hash()
    print(f"1. Chain height: {height}")
    print(f"   Chain tip: {tip[:10]}..." if tip else "   No tip")
    
    # 2. Get stats
    stats = chain_manager.get_chain_stats()
    print(f"2. Chain stats:")
    print(f"   Difficulty: {stats['difficulty']}")
    print(f"   UTXOs: {stats['utxo_count']}")
    print(f"   Supply: {stats['total_supply']}")
    
    # 3. Create a test block
    print("3. Creating test block template...")
    from blockchain.transaction import create_coinbase_transaction
    
    # Create a coinbase transaction
    coinbase = create_coinbase_transaction("TEST_MINER_ADDRESS", 5000000000)  # 50 ZARU
    
    # Get block template
    template = chain_manager.get_next_block_template([coinbase])
    print(f"   Block template created: Height {template.header.block_height}")
    print(f"   Difficulty: {template.header.difficulty_target}")
    
    print("\n✅ Chain Manager test complete")
    return True


if __name__ == "__main__":
    test_chain_manager()