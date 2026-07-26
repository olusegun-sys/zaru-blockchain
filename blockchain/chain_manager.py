"""
ZARU Chain Manager Module
=========================
Manages the blockchain - adding blocks, handling forks, and maintaining chain state.

FIXED: Added duplicate block check to prevent miner loop.
FIXED: Type-safe height comparison (int vs int).
"""

import time
from typing import Optional, Dict, List, Tuple, Any

from config import settings
from blockchain.block import Block, BlockHeader, create_genesis_block, calculate_difficulty
from blockchain.transaction import Transaction
from blockchain.utxo import UTXOSet
from database import store as db_store


class ChainManager:
    """
    Manages the blockchain - the authoritative source of chain state.
    """
    
    def __init__(self, store=None, utxo_set=None, mempool=None):
        self.store = store if store else db_store
        self.utxo_set = utxo_set if utxo_set else UTXOSet(self.store)
        self.mempool = mempool  # Optional: for removing confirmed transactions
        
        self._tip_hash = None
        self._tip_height = None
        self._difficulty = None
        
        self._initialize_chain()
        
        print(f"✅ Chain Manager initialized: Height {self.get_height()}, Tip: {self.get_tip_hash()[:10] if self.get_tip_hash() else 'None'}...")
    
    # ============================================
    # INITIALIZATION
    # ============================================
    
    def _initialize_chain(self) -> None:
        height = self.store.get_chain_height()
        
        if height == 0:
            print("⛓️  No blockchain found. Creating genesis block...")
            self._create_genesis_chain()
        else:
            print(f"⛓️  Loading existing blockchain (height: {height})...")
            self._load_chain_state()
    
    def _create_genesis_chain(self) -> None:
        genesis = create_genesis_block()
        self.utxo_set.apply_block(genesis)
        self.store.put_block(genesis.hash, genesis.to_dict())
        self.store.put_chain_state('chain_tip', genesis.hash)
        self.store.put_chain_state('chain_height', genesis.header.block_height + 1)
        self.store.put_chain_state('difficulty', genesis.header.difficulty_target)
        
        self._tip_hash = genesis.hash
        self._tip_height = genesis.header.block_height + 1
        self._difficulty = genesis.header.difficulty_target
        
        print(f"✅ Genesis block created: {genesis.hash[:10]}...")
        print(f"   Initial supply: {settings.INITIAL_COIN_SUPPLY} ZARU")
    
    def _load_chain_state(self) -> None:
        self._tip_hash = self.store.get_chain_state('chain_tip')
        self._tip_height = self.store.get_chain_state('chain_height')
        self._difficulty = self.store.get_chain_state('difficulty')
        
        if self._tip_hash is None or self._tip_height is None:
            latest = self.store.get_latest_block()
            if latest:
                self._tip_hash = latest['hash']
                self._tip_height = latest['header']['block_height'] + 1
                self._difficulty = latest['header']['difficulty_target']
    
    # ============================================
    # CHAIN QUERY METHODS
    # ============================================
    
    def get_tip_hash(self) -> Optional[str]:
        if self._tip_hash is None:
            self._tip_hash = self.store.get_chain_state('chain_tip')
        return self._tip_hash
    
    def get_height(self) -> int:
        if self._tip_height is None:
            self._tip_height = self.store.get_chain_state('chain_height')
            if self._tip_height is None:
                self._tip_height = self.store.get_chain_height()
        # Ensure we return an int
        return int(self._tip_height) if self._tip_height else 0
    
    def get_difficulty(self) -> int:
        if self._difficulty is None:
            self._difficulty = self.store.get_chain_state('difficulty')
            if self._difficulty is None:
                self._difficulty = settings.INITIAL_DIFFICULTY
        return int(self._difficulty)
    
    def get_block(self, block_hash: str) -> Optional[Block]:
        data = self.store.get_block(block_hash)
        if data:
            return Block.from_dict(data)
        return None
    
    def get_block_by_height(self, height: int) -> Optional[Block]:
        data = self.store.get_block_by_height(int(height))
        if data:
            return Block.from_dict(data)
        return None
    
    def get_blocks(self, start_height: int, end_height: int) -> List[Block]:
        blocks = []
        for height in range(int(start_height), int(end_height) + 1):
            block = self.get_block_by_height(height)
            if block:
                blocks.append(block)
        return blocks
    
    def get_best_chain(self) -> List[Block]:
        height = self.get_height()
        blocks = []
        for i in range(height):
            block = self.get_block_by_height(i)
            if block:
                blocks.append(block)
        return blocks
    
    # ============================================
    # BLOCK VALIDATION - FIXED TYPE-SAFE
    # ============================================
    
    def validate_block(self, block: Block) -> Tuple[bool, str]:
        """Validate a block before adding it to the chain."""
        if block is None:
            return False, "Block is None"
        
        if not block.hash or len(block.hash) != 64:
            return False, f"Invalid block hash: {block.hash}"
        
        # FIXED: Type-safe height comparison
        expected_height = int(self.get_height())
        block_height = int(block.header.block_height)
        
        if block_height != expected_height:
            return False, f"Invalid block height: expected {expected_height}, got {block_height}"
        
        tip_hash = self.get_tip_hash()
        if block.header.prev_block_hash != tip_hash:
            return False, f"Previous block hash mismatch: expected {tip_hash}, got {block.header.prev_block_hash}"
        
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        computed_root = block.compute_merkle_root()
        if computed_root != block.header.merkle_root:
            return False, "Merkle root mismatch"
        
        if block.size > settings.MAX_BLOCK_SIZE_BYTES:
            return False, f"Block size {block.size} exceeds limit {settings.MAX_BLOCK_SIZE_BYTES}"
        
        for i, tx in enumerate(block.transactions):
            is_valid, error = self.utxo_set.validate_transaction(tx, block.header.block_height)
            if not is_valid:
                return False, f"Transaction {i} invalid: {error}"
        
        if block.transactions and not block.transactions[0].is_coinbase:
            return False, "First transaction must be coinbase"
        
        # Validate coinbase reward using MAX_COINBASE_REWARD
        if block.transactions and block.transactions[0].is_coinbase:
            coinbase = block.transactions[0]
            MAX_COINBASE_REWARD = getattr(settings, 'MAX_COINBASE_REWARD', 5_000_000_000)
            if coinbase.outputs[0].amount > MAX_COINBASE_REWARD:
                return False, f"Coinbase reward ({coinbase.outputs[0].amount}) exceeds max reward ({MAX_COINBASE_REWARD})"
            print(f"✅ Coinbase reward validated: {coinbase.outputs[0].amount} satoshis")
        
        return True, "Block is valid"
    
    # ============================================
    # BLOCK ADDITION - FIXED DUPLICATE CHECK
    # ============================================
    
    def add_block(self, block: Block) -> Tuple[bool, str]:
        """Add a block to the blockchain."""
        try:
            # FIXED: Early duplicate check before validation
            block_height = int(block.header.block_height)
            existing = self.get_block_by_height(block_height)
            if existing:
                print(f"ℹ️  Block {block_height} already exists, skipping")
                return True, "Block already exists"
            
            is_valid, error = self.validate_block(block)
            if not is_valid:
                return False, f"Block validation failed: {error}"
            
            tip_hash = self.get_tip_hash()
            if block.header.prev_block_hash == tip_hash:
                return self._add_to_best_chain(block)
            
            fork_point = self._find_fork_point(block)
            if fork_point is None:
                return False, "Block does not connect to any known chain"
            
            fork_blocks = self._get_chain_from_block(block)
            current_blocks = self.get_blocks(fork_point, self.get_height() - 1)
            
            if len(fork_blocks) <= len(current_blocks):
                return False, f"Fork is not longer than current chain ({len(fork_blocks)} <= {len(current_blocks)})"
            
            return self._handle_reorganization(current_blocks, fork_blocks)
            
        except Exception as e:
            print(f"❌ Error adding block: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Error: {str(e)}"
    
    def _add_to_best_chain(self, block: Block) -> Tuple[bool, str]:
        """
        Add a block to the best chain.
        
        FIXED: Added duplicate block check to prevent miner loop.
        """
        try:
            block_height = int(block.header.block_height)
            
            # Check if this block already exists at this height
            existing = self.get_block_by_height(block_height)
            if existing:
                # Block already exists at this height
                print(f"ℹ️  Block {block_height} already exists, skipping")
                return True, "Block already exists"
            
            # Apply block to UTXO set
            if not self.utxo_set.apply_block(block):
                return False, "Failed to apply block to UTXO set"
            
            # Store block in database
            if not self.store.put_block(block.hash, block.to_dict()):
                return False, "Failed to store block in database"
            
            # Update chain state
            new_height = self.get_height() + 1
            self.store.put_chain_state('chain_tip', block.hash)
            self.store.put_chain_state('chain_height', new_height)
            
            # Update difficulty (if needed)
            if new_height % settings.DIFFICULTY_ADJUSTMENT_INTERVAL == 0:
                prev_block = self.get_block_by_height(new_height - settings.DIFFICULTY_ADJUSTMENT_INTERVAL - 1)
                if prev_block:
                    new_difficulty = calculate_difficulty(block, prev_block)
                    self.store.put_chain_state('difficulty', new_difficulty)
                    self._difficulty = new_difficulty
            
            # Update cache
            self._tip_hash = block.hash
            self._tip_height = new_height
            
            # Remove confirmed transactions from mempool
            if self.mempool:
                self.mempool.confirm_block(block)
            
            print(f"✅ Block {block_height} added to best chain")
            print(f"   Hash: {block.hash[:10]}...")
            print(f"   Tx: {len(block.transactions)}")
            print(f"   New height: {new_height}")
            
            return True, "Block added to best chain"
            
        except Exception as e:
            print(f"❌ Error adding block to best chain: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Error: {str(e)}"
    
    def _find_fork_point(self, block: Block) -> Optional[int]:
        current = block
        
        while current:
            existing = self.get_block(current.hash)
            if existing:
                return current.header.block_height
            
            if current.header.block_height == 0:
                break
            
            prev = self.get_block(current.header.prev_block_hash)
            if not prev:
                break
            current = prev
        
        return None
    
    def _get_chain_from_block(self, block: Block) -> List[Block]:
        blocks = []
        current = block
        
        while current:
            blocks.append(current)
            if current.header.prev_block_hash == "0" * 64:
                break
            current = self.get_block(current.header.prev_block_hash)
            if not current:
                break
        
        return list(reversed(blocks))
    
    # ============================================
    # CHAIN REORGANIZATION
    # ============================================
    
    def _handle_reorganization(
        self, 
        old_chain: List[Block], 
        new_chain: List[Block]
    ) -> Tuple[bool, str]:
        try:
            print(f"🔄 Chain reorganization starting...")
            print(f"   Removing {len(old_chain)} blocks")
            print(f"   Adding {len(new_chain)} blocks")
            
            for block in reversed(old_chain):
                self.utxo_set._rollback_block(block)
                print(f"   Rolled back block {block.header.block_height}")
            
            for block in new_chain:
                if not self.utxo_set.apply_block(block):
                    print(f"❌ Failed to apply block {block.header.block_height} during reorg")
                    for b in reversed(new_chain):
                        self.utxo_set._rollback_block(b)
                    return False, "Reorg failed during apply phase"
                print(f"   Applied block {block.header.block_height}")
            
            tip_block = new_chain[-1]
            new_height = tip_block.header.block_height + 1
            
            self.store.put_chain_state('chain_tip', tip_block.hash)
            self.store.put_chain_state('chain_height', new_height)
            
            self._tip_hash = tip_block.hash
            self._tip_height = new_height
            
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
        print("🔍 Verifying entire blockchain...")
        
        height = self.get_height()
        if height == 0:
            return False, "Chain is empty"
        
        for i in range(height):
            block = self.get_block_by_height(i)
            if not block:
                return False, f"Block {i} not found"
            
            is_valid, error = self.verify_block_chain(block)
            if not is_valid:
                return False, f"Block {i} invalid: {error}"
            
            if i % 100 == 0:
                print(f"   Verified block {i}/{height}")
        
        print(f"✅ Chain verification complete: {height} blocks valid")
        return True, "Chain is valid"
    
    def verify_block_chain(self, block: Block) -> Tuple[bool, str]:
        computed_hash = block.compute_hash()
        if computed_hash != block.hash:
            return False, f"Block hash mismatch: computed {computed_hash}, stored {block.hash}"
        
        if block.header.block_height > 0:
            prev = self.get_block(block.header.prev_block_hash)
            if not prev:
                return False, "Previous block not found"
            if prev.header.block_height != block.header.block_height - 1:
                return False, "Block height mismatch with previous block"
        
        computed_root = block.compute_merkle_root()
        if computed_root != block.header.merkle_root:
            return False, "Merkle root mismatch"
        
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        return True, "Block is valid"
    
    # ============================================
    # MINING SUPPORT
    # ============================================
    
    def get_next_block_template(self, transactions: List[Transaction]) -> Block:
        block = Block()
        block.header.block_height = self.get_height()
        block.header.prev_block_hash = self.get_tip_hash()
        block.header.difficulty_target = self.get_difficulty()
        block.header.timestamp = int(time.time())
        
        for tx in transactions:
            block.add_transaction(tx)
        
        block.header.merkle_root = block.compute_merkle_root()
        block.hash = block.compute_hash()
        block.size = block.compute_size()
        block.transaction_count = len(block.transactions)
        
        return block
    
    def submit_mined_block(self, block: Block) -> Tuple[bool, str]:
        if not block.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        return self.add_block(block)
    
    # ============================================
    # STATISTICS
    # ============================================
    
    def get_chain_stats(self) -> Dict[str, Any]:
        height = self.get_height()
        tip_hash = self.get_tip_hash()
        latest = self.get_block_by_height(height - 1) if height > 0 else None
        utxo_count = self.utxo_set.get_utxo_count()
        
        return {
            'height': height,
            'tip_hash': tip_hash,
            'difficulty': self.get_difficulty(),
            'utxo_count': utxo_count,
            'total_supply': settings.INITIAL_COIN_SUPPLY,
            'latest_block_time': latest.header.timestamp if latest else None,
            'latest_block_hash': latest.hash if latest else None,
        }


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_chain_manager(store=None, utxo_set=None) -> ChainManager:
    return ChainManager(store, utxo_set)


# ============================================
# GLOBAL INSTANCE
# ============================================

chain_manager = ChainManager()


if __name__ == "__main__":
    test_chain_manager()