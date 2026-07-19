"""
ZARU Mempool Module
===================
Manages pending transactions waiting to be included in blocks.

WHY: The mempool is the "waiting room" for transactions.
When a user sends a transaction, it goes to the mempool first.
Miners then pick transactions from the mempool to include in blocks.

THINK OF IT LIKE: A restaurant kitchen's order queue.
Customers place orders (transactions), they wait in the queue (mempool),
and the chef (miner) picks orders to cook (mine into blocks).

HOW IT WORKS:
1. Transactions are added to the mempool
2. Each transaction is validated against the UTXO set
3. Transactions are ordered by fee (highest fee first)
4. Miners take transactions from the mempool
5. Old transactions expire and are removed
"""

import time
import heapq
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config import settings
from blockchain.transaction import Transaction
from blockchain.utxo import UTXOSet
from database import store as db_store


@dataclass
class MempoolEntry:
    """
    An entry in the mempool.
    
    WHY: We need to track additional metadata for each transaction:
    - When it was added (for expiry)
    - Fee per byte (for ordering)
    - Size (for block inclusion)
    
    SORTING: We sort by fee_per_byte (highest first) so miners
    pick the most profitable transactions first.
    """
    fee_per_byte: float = field(compare=False)  # Higher = better (for heapq)
    timestamp: float = field(compare=False)
    transaction: Transaction = field(compare=False)
    size: int = field(compare=False)
    fee: int = field(compare=False)
    tx_id: str = field(compare=False)
    
    # For heapq, we want highest fee_per_byte first (max-heap behavior)
    # We implement __lt__ to reverse the order for heapq's min-heap
    def __lt__(self, other):
        # heapq is a min-heap, so we return True if this has HIGHER fee
        # This makes the heap give us the highest fee items first
        return self.fee_per_byte > other.fee_per_byte


class Mempool:
    """
    Manages pending transactions.
    
    The mempool is a priority queue of transactions ordered by fee.
    It also handles:
    - Transaction validation (against UTXO set)
    - Expiry (removing old transactions)
    - Double-spend detection
    - Replacement (higher fee transactions replacing lower fee ones)
    """
    
    def __init__(self, utxo_set=None, store=None, max_size: int = None):
        """
        Initialize the mempool.
        
        Args:
            utxo_set: UTXO set instance (creates new if None)
            store: Database store instance (uses global if None)
            max_size: Maximum number of transactions (from config if None)
        """
        self.store = store if store else db_store
        self.utxo_set = utxo_set if utxo_set else UTXOSet(self.store)
        self.max_size = max_size if max_size is not None else settings.MEMPOOL_MAX_SIZE
        self.expiry_hours = settings.MEMPOOL_EXPIRY_HOURS
        
        # Storage
        self.transactions: Dict[str, MempoolEntry] = {}  # tx_id -> entry
        self.heap: List[MempoolEntry] = []  # Priority queue by fee
        self.by_address: Dict[str, List[str]] = {}  # address -> [tx_ids]
        self.spent_utxos: Dict[str, str] = {}  # "tx_id:index" -> spending_tx_id
        
        # Statistics
        self.total_added = 0
        self.total_removed = 0
        self.total_expired = 0
        self.total_replaced = 0
        
        print(f"✅ Mempool initialized: max_size={self.max_size}, expiry={self.expiry_hours}h")
    
    # ============================================
    # TRANSACTION ADDITION
    # ============================================
    
    def add_transaction(self, transaction: Transaction) -> Tuple[bool, str]:
        """
        Add a transaction to the mempool.
        
        Args:
            transaction: Transaction to add
        
        Returns:
            Tuple[bool, str]: (success, message)
        
        HOW IT WORKS:
        1. Check if transaction already exists
        2. Validate transaction against UTXO set
        3. Check for double-spends
        4. Check mempool size
        5. Add transaction to mempool
        
        WHY: This is the main entry point for adding transactions.
        It handles all validation and conflict detection.
        """
        # 1. Check if already in mempool
        if transaction.tx_id in self.transactions:
            # Check if this is a replacement (higher fee)
            existing = self.transactions[transaction.tx_id]
            new_fee = self._calculate_fee(transaction)
            if new_fee > existing.fee:
                # Replace with higher fee transaction
                return self._replace_transaction(transaction)
            return False, f"Transaction {transaction.tx_id[:8]}... already in mempool"
        
        # 2. Validate transaction against UTXO set
        is_valid, error = self.utxo_set.validate_transaction(transaction)
        if not is_valid:
            return False, f"Transaction invalid: {error}"
        
        # 3. Check for double-spends in mempool
        for tx_input in transaction.inputs:
            key = f"{tx_input.tx_id}:{tx_input.output_index}"
            if key in self.spent_utxos:
                existing_tx = self.spent_utxos[key]
                return False, f"Double-spend detected: UTXO {key} already spent by {existing_tx[:8]}..."
        
        # 4. Check mempool size
        if len(self.transactions) >= self.max_size:
            # Try to remove expired transactions first
            expired = self._remove_expired()
            if len(self.transactions) >= self.max_size:
                return False, f"Mempool full ({self.max_size} transactions)"
        
        # 5. Calculate transaction metrics
        size = len(transaction.serialize())
        fee = self._calculate_fee(transaction)
        fee_per_byte = fee / size if size > 0 else 0
        
        # 6. Create mempool entry
        entry = MempoolEntry(
            fee_per_byte=fee_per_byte,
            timestamp=time.time(),
            transaction=transaction,
            size=size,
            fee=fee,
            tx_id=transaction.tx_id
        )
        
        # 7. Add to mempool
        self.transactions[transaction.tx_id] = entry
        heapq.heappush(self.heap, entry)
        
        # 8. Track UTXO spending
        for tx_input in transaction.inputs:
            key = f"{tx_input.tx_id}:{tx_input.output_index}"
            self.spent_utxos[key] = transaction.tx_id
        
        # 9. Track by address (for balance calculations)
        for tx_output in transaction.outputs:
            if tx_output.address not in self.by_address:
                self.by_address[tx_output.address] = []
            self.by_address[tx_output.address].append(transaction.tx_id)
        
        self.total_added += 1
        
        print(f"✅ Transaction {transaction.tx_id[:8]}... added to mempool")
        print(f"   Fee: {fee} satoshis, Size: {size} bytes, Fee/byte: {fee_per_byte:.2f}")
        
        return True, "Transaction added to mempool"
    
    def _calculate_fee(self, transaction: Transaction) -> int:
        """
        Calculate transaction fee.
        
        WHY: Fee = total_input - total_output.
        This requires looking up the UTXO amounts.
        """
        # Calculate total input
        total_input = 0
        for tx_input in transaction.inputs:
            utxo = self.utxo_set.get_utxo(tx_input.tx_id, tx_input.output_index)
            if utxo:
                total_input += utxo.get('amount', 0)
        
        # Calculate total output
        total_output = transaction.get_total_output()
        
        return total_input - total_output
    
    def _replace_transaction(self, transaction: Transaction) -> Tuple[bool, str]:
        """
        Replace an existing transaction with a higher fee version.
        
        WHY: Users can bump fees by sending a new transaction
        with the same inputs but higher fee.
        """
        old_entry = self.transactions[transaction.tx_id]
        old_fee = old_entry.fee
        new_fee = self._calculate_fee(transaction)
        
        if new_fee <= old_fee:
            return False, f"New fee ({new_fee}) not higher than existing ({old_fee})"
        
        # Remove old transaction
        self._remove_transaction(transaction.tx_id)
        
        # Add new transaction
        return self.add_transaction(transaction)
    
    # ============================================
    # TRANSACTION REMOVAL
    # ============================================
    
    def remove_transaction(self, tx_id: str) -> bool:
        """
        Remove a transaction from the mempool.
        
        Args:
            tx_id: Transaction ID to remove
        
        Returns:
            bool: True if removed
        
        WHY: Transactions are removed when:
        - They are mined into a block
        - They expire
        - They are replaced by a higher fee transaction
        """
        if tx_id not in self.transactions:
            return False
        
        return self._remove_transaction(tx_id)
    
    def _remove_transaction(self, tx_id: str) -> bool:
        """
        Internal method to remove a transaction.
        
        WHY: We need to clean up all references:
        - Remove from transactions dict
        - Remove from heap (lazy removal)
        - Remove UTXO spending tracking
        - Remove address tracking
        """
        if tx_id not in self.transactions:
            return False
        
        entry = self.transactions[tx_id]
        transaction = entry.transaction
        
        # Remove UTXO spending tracking
        for tx_input in transaction.inputs:
            key = f"{tx_input.tx_id}:{tx_input.output_index}"
            if key in self.spent_utxos and self.spent_utxos[key] == tx_id:
                del self.spent_utxos[key]
        
        # Remove address tracking
        for tx_output in transaction.outputs:
            if tx_output.address in self.by_address:
                if tx_id in self.by_address[tx_output.address]:
                    self.by_address[tx_output.address].remove(tx_id)
                    if not self.by_address[tx_output.address]:
                        del self.by_address[tx_output.address]
        
        # Remove from transactions dict
        del self.transactions[tx_id]
        
        # Note: Heap entry remains but will be ignored (lazy removal)
        self.total_removed += 1
        
        return True
    
    def remove_transactions(self, tx_ids: List[str]) -> int:
        """
        Remove multiple transactions from the mempool.
        
        Args:
            tx_ids: List of transaction IDs to remove
        
        Returns:
            int: Number of transactions removed
        
        WHY: Used when a block is mined - we remove all transactions
        that were included in the block.
        """
        removed = 0
        for tx_id in tx_ids:
            if self._remove_transaction(tx_id):
                removed += 1
        return removed
    
    # ============================================
    # TRANSACTION RETRIEVAL
    # ============================================
    
    def get_transaction(self, tx_id: str) -> Optional[Transaction]:
        """Get a transaction from the mempool by ID."""
        entry = self.transactions.get(tx_id)
        return entry.transaction if entry else None
    
    def get_transactions(self, count: Optional[int] = None) -> List[Transaction]:
        """
        Get transactions from the mempool, ordered by fee.
        
        Args:
            count: Maximum number of transactions to return
        
        Returns:
            List[Transaction]: Transactions ordered by fee (highest first)
        
        WHY: Miners call this to get transactions for their block.
        """
        # Clean the heap (remove stale entries)
        self._clean_heap()
        
        # Get top transactions
        result = []
        for entry in self.heap[:count if count else len(self.heap)]:
            if entry.tx_id in self.transactions:
                result.append(entry.transaction)
        
        return result
    
    def get_transactions_for_block(
        self, 
        max_size: int = None,
        max_count: int = None
    ) -> List[Transaction]:
        """
        Get transactions for inclusion in a block.
        
        Args:
            max_size: Maximum block size in bytes
            max_count: Maximum number of transactions
        
        Returns:
            List[Transaction]: Transactions to include in block
        
        WHY: Miners use this to build a block.
        It selects the most profitable transactions that fit in the block.
        """
        if max_size is None:
            max_size = settings.MAX_BLOCK_SIZE_BYTES
        
        # Clean the heap
        self._clean_heap()
        
        # Calculate coinbase size (approx)
        coinbase_size = 100  # Approximate coinbase transaction size
        
        # Reserve space for coinbase
        remaining_size = max_size - coinbase_size
        
        selected = []
        total_size = 0
        total_fee = 0
        
        for entry in self.heap:
            if entry.tx_id not in self.transactions:
                continue
            
            # Check size limit
            if total_size + entry.size > remaining_size:
                continue
            
            # Check count limit
            if max_count and len(selected) >= max_count:
                break
            
            # Add transaction
            selected.append(entry.transaction)
            total_size += entry.size
            total_fee += entry.fee
        
        print(f"📦 Selected {len(selected)} transactions for block")
        print(f"   Total size: {total_size} bytes, Total fee: {total_fee} satoshis")
        
        return selected
    
    def get_mempool_size(self) -> int:
        """Get the number of transactions in the mempool."""
        self._clean_heap()
        return len(self.transactions)
    
    def get_total_fees(self) -> int:
        """Get the total fees of all transactions in the mempool."""
        self._clean_heap()
        return sum(entry.fee for entry in self.transactions.values())
    
    # ============================================
    # MEMPOOL MAINTENANCE
    # ============================================
    
    def _clean_heap(self) -> None:
        """
        Clean the heap by removing stale entries.
        
        WHY: We use lazy removal (entries stay in heap after removal).
        This function removes entries that are no longer in the mempool.
        """
        while self.heap:
            entry = self.heap[0]
            if entry.tx_id not in self.transactions:
                heapq.heappop(self.heap)
            else:
                break
    
    def _remove_expired(self) -> int:
        """
        Remove expired transactions from the mempool.
        
        Returns:
            int: Number of transactions removed
        
        WHY: Transactions that have been waiting too long
        should be removed to prevent mempool bloat.
        """
        now = time.time()
        expired = []
        expiry_seconds = self.expiry_hours * 3600
        
        for tx_id, entry in self.transactions.items():
            if now - entry.timestamp > expiry_seconds:
                expired.append(tx_id)
        
        removed = 0
        for tx_id in expired:
            if self._remove_transaction(tx_id):
                removed += 1
                self.total_expired += 1
        
        if removed > 0:
            print(f"🗑️  Removed {removed} expired transactions from mempool")
        
        return removed
    
    def cleanup(self) -> int:
        """
        Clean up the mempool (remove expired and invalid transactions).
        
        Returns:
            int: Number of transactions removed
        
        WHY: Called periodically to maintain mempool health.
        """
        removed = 0
        
        # 1. Remove expired
        removed += self._remove_expired()
        
        # 2. Remove invalid (transactions that are no longer valid)
        invalid = []
        for tx_id, entry in self.transactions.items():
            is_valid, _ = self.utxo_set.validate_transaction(entry.transaction)
            if not is_valid:
                invalid.append(tx_id)
        
        for tx_id in invalid:
            if self._remove_transaction(tx_id):
                removed += 1
        
        if invalid:
            print(f"🗑️  Removed {len(invalid)} invalid transactions from mempool")
        
        # 3. Clean heap
        self._clean_heap()
        
        return removed
    
    # ============================================
    # ADDRESS QUERIES
    # ============================================
    
    def get_transactions_for_address(self, address: str) -> List[Transaction]:
        """
        Get all mempool transactions for an address.
        
        Args:
            address: Address to query
        
        Returns:
            List[Transaction]: Transactions involving the address
        """
        result = []
        if address in self.by_address:
            for tx_id in self.by_address[address]:
                if tx_id in self.transactions:
                    result.append(self.transactions[tx_id].transaction)
        return result
    
    def get_pending_balance(self, address: str) -> int:
        """
        Get the pending balance for an address (in mempool).
        
        Args:
            address: Address to query
        
        Returns:
            int: Total amount in pending transactions
        
        WHY: When showing a wallet balance, we include
        both confirmed UTXOs and pending transactions.
        """
        total = 0
        for tx in self.get_transactions_for_address(address):
            for tx_output in tx.outputs:
                if tx_output.address == address:
                    total += tx_output.amount
        return total
    
    # ============================================
    # MEMPOOL STATE
    # ============================================
    
    def clear(self) -> None:
        """Clear all transactions from the mempool."""
        self.transactions.clear()
        self.heap.clear()
        self.by_address.clear()
        self.spent_utxos.clear()
        print("🗑️  Mempool cleared")
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get the current mempool state.
        
        Returns:
            Dict: Mempool statistics
        """
        self._clean_heap()
        
        return {
            'size': len(self.transactions),
            'max_size': self.max_size,
            'total_added': self.total_added,
            'total_removed': self.total_removed,
            'total_expired': self.total_expired,
            'total_replaced': self.total_replaced,
            'total_fees': self.get_total_fees(),
            'addresses': len(self.by_address),
            'spent_utxos': len(self.spent_utxos),
        }
    
    def get_transaction_ids(self) -> List[str]:
        """Get all transaction IDs in the mempool."""
        return list(self.transactions.keys())
    
    def contains_transaction(self, tx_id: str) -> bool:
        """Check if a transaction is in the mempool."""
        return tx_id in self.transactions
    
    # ============================================
    # BLOCK MINING INTEGRATION
    # ============================================
    
    def prepare_for_mining(self, block_size: int = None) -> List[Transaction]:
        """
        Prepare transactions for mining.
        
        Args:
            block_size: Maximum block size in bytes
        
        Returns:
            List[Transaction]: Transactions selected for mining
        
        WHY: Miners call this to get transactions for their block.
        It selects the most profitable transactions that fit.
        """
        # Clean up first
        self.cleanup()
        
        # Get transactions for block
        transactions = self.get_transactions_for_block(block_size)
        
        return transactions
    
    def confirm_block(self, block: Any) -> int:
        """
        Confirm that a block has been mined.
        
        Args:
            block: The block that was mined
        
        Returns:
            int: Number of transactions removed from mempool
        
        WHY: After a block is mined, we remove all its transactions
        from the mempool because they are now confirmed.
        """
        tx_ids = [tx.tx_id for tx in block.transactions if not tx.is_coinbase]
        return self.remove_transactions(tx_ids)
    
    def reject_block(self, block: Any) -> None:
        """
        Reject a block (during reorganization).
        
        Args:
            block: The block being rejected
        
        WHY: During a chain reorganization, transactions from
        rejected blocks may need to go back into the mempool.
        """
        # During a reorg, blocks are removed from the chain
        # Their transactions should go back to the mempool
        for tx in block.transactions:
            if not tx.is_coinbase:
                # Check if transaction is still valid
                is_valid, _ = self.utxo_set.validate_transaction(tx)
                if is_valid:
                    self.add_transaction(tx)
                    print(f"🔄 Re-added transaction {tx.tx_id[:8]}... to mempool (reorg)")


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_mempool(utxo_set=None, store=None, max_size: int = None) -> Mempool:
    """
    Factory function to create a Mempool.
    
    WHY: Makes it easy to initialize the Mempool
    with either default or custom dependencies.
    """
    return Mempool(utxo_set, store, max_size)


# ============================================
# GLOBAL INSTANCE
# ============================================

# Create a global Mempool instance
mempool = Mempool()


# ============================================
# TEST FUNCTIONS
# ============================================

def test_mempool():
    """
    Quick test to verify Mempool is working.
    """
    print("\n🧪 Testing Mempool...")
    
    from blockchain.transaction import Transaction, TxInput, TxOutput
    
    # 1. Create a test UTXO first
    test_address = "TEST_MEMPOOL_ADDRESS"
    from database import store
    store.put_utxo(
        tx_id="MEMPOOL_TEST_TX",
        output_index=0,
        amount=10000,
        address=test_address,
        block_height=0
    )
    
    # 2. Create a test transaction
    tx = Transaction(
        inputs=[TxInput(tx_id="MEMPOOL_TEST_TX", output_index=0)],
        outputs=[TxOutput(amount=5000, address="RECIPIENT_001")],
        is_coinbase=False
    )
    tx.tx_id = tx.compute_id()
    
    # 3. Add to mempool
    mempool.clear()  # Start fresh
    success, message = mempool.add_transaction(tx)
    print(f"1. Add transaction: {success} - {message}")
    
    # 4. Get mempool size
    size = mempool.get_mempool_size()
    print(f"2. Mempool size: {size}")
    
    # 5. Get transactions
    txs = mempool.get_transactions(10)
    print(f"3. Retrieved transactions: {len(txs)}")
    
    # 6. Get state
    state = mempool.get_state()
    print(f"4. Mempool state:")
    for key, value in state.items():
        print(f"   {key}: {value}")
    
    # 7. Remove transaction
    removed = mempool.remove_transaction(tx.tx_id)
    print(f"5. Remove transaction: {removed}")
    
    print("\n✅ Mempool test complete")
    return True


if __name__ == "__main__":
    test_mempool()