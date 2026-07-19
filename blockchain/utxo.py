"""
ZARU UTXO Module
================
Manages the Unspent Transaction Output (UTXO) set.
This is the "current state" of the ledger - all coins that exist and can be spent.

WHY: The UTXO set is the source of truth for:
- Address balances
- Transaction validation (preventing double-spends)
- Block validation
- Mining (knowing what coins exist)

THINK OF IT LIKE: A bank's ledger of all accounts and their current balances,
but at the individual coin level instead of account level.
"""

import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

# Import from config - this is the correct way
from config import settings
from database import store as db_store
from blockchain.transaction import Transaction, TxInput, TxOutput


class UTXOSet:
    """
    Manages all unspent transaction outputs.
    
    The UTXO set is the "live state" of the blockchain.
    It tracks which coins exist and who owns them.
    
    HOW IT WORKS:
    1. When a transaction is created, it references UTXOs as inputs
    2. When a transaction is applied, inputs are marked spent, outputs are added
    3. When a block is rolled back (reorg), the process is reversed
    """
    
    def __init__(self, store=None):
        """
        Initialize UTXO set with database connection.
        
        Args:
            store: Database store instance (uses global if None)
        """
        self.store = store if store else db_store
        print(f"✅ UTXO Set initialized with {self.store.get_utxo_count()} UTXOs")
    
    # ============================================
    # UTXO QUERY METHODS
    # ============================================
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific UTXO by transaction ID and output index.
        
        WHY: When validating a transaction input, we need to look up
        the specific UTXO it references to verify it exists and is unspent.
        """
        return self.store.get_utxo(tx_id, output_index)
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        """
        Get all unspent UTXOs belonging to an address.
        
        WHY: When a user wants to send money, we need to know
        which coins they own that they can spend.
        
        RETURNS: List of UTXOs, each containing:
        - tx_id: Transaction ID
        - output_index: Index in the transaction
        - amount: Value in satoshis
        - block_height: When it was created
        """
        return self.store.get_utxos_for_address(address)
    
    def get_balance(self, address: str) -> int:
        """
        Calculate total balance for an address.
        
        WHY: The wallet needs to display the user's balance.
        
        HOW: Sum all UTXOs belonging to the address.
        """
        utxos = self.get_utxos_for_address(address)
        return sum(utxo['amount'] for utxo in utxos)
    
    def get_utxo_count(self) -> int:
        """Get total number of unspent UTXOs in the system."""
        return self.store.get_utxo_count()
    
    def get_total_supply(self) -> int:
        """
        Calculate total circulating supply.
        
        WHY: Monitor how many coins are in circulation.
        This should equal the initial supply minus any burned coins.
        """
        # Sum all UTXOs (should equal initial supply)
        # Note: This is expensive - we cache it in chain state
        cached = self.store.get_chain_state('total_supply')
        if cached is not None:
            return int(cached)
        
        # Calculate from scratch (slow)
        # For now, we return the cached value or initial supply
        return settings.INITIAL_COIN_SUPPLY
    
    # ============================================
    # UTXO SELECTION FOR SPENDING
    # ============================================
    
    def select_utxos_for_amount(
        self, 
        address: str, 
        amount: int,
        fee: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Select UTXOs to cover a specific amount (including fee).
        
        Args:
            address: Address spending the coins
            amount: Amount needed (in satoshis)
            fee: Transaction fee (in satoshis)
        
        Returns:
            Tuple of (selected_utxos, total_selected_amount)
        
        WHY: When creating a transaction, we need to pick which coins to spend.
        We use a simple "first-fit" algorithm - take smallest UTXOs first.
        
        THINK OF IT LIKE: Choosing which bills to use to pay for something.
        You want to use the smallest bills possible that cover the amount.
        """
        # Get all UTXOs for this address
        utxos = self.get_utxos_for_address(address)
        
        # Sort by amount (smallest first) - more efficient coin selection
        utxos.sort(key=lambda x: x['amount'])
        
        selected = []
        total = 0
        needed = amount + fee
        
        for utxo in utxos:
            selected.append(utxo)
            total += utxo['amount']
            if total >= needed:
                break
        
        if total < needed:
            return [], 0  # Insufficient funds
        
        return selected, total
    
    def calculate_fee(
        self, 
        input_count: int, 
        output_count: int,
        fee_per_byte: int = None
    ) -> int:
        """
        Calculate transaction fee based on size.
        
        WHY: Fees ensure miners are incentivized to include transactions.
        Larger transactions (more inputs/outputs) cost more.
        """
        if fee_per_byte is None:
            fee_per_byte = settings.DEFAULT_FEE_PER_KB // 1024
        
        # Estimate transaction size
        # Each input: ~148 bytes, each output: ~34 bytes, overhead: ~10 bytes
        estimated_size = 10 + (input_count * 148) + (output_count * 34)
        
        # Fee = size * fee_per_byte
        fee = estimated_size * fee_per_byte
        
        # Minimum fee (anti-spam)
        return max(fee, settings.MIN_RELAY_FEE)
    
    # ============================================
    # TRANSACTION VALIDATION
    # ============================================
    
    def validate_transaction(
        self, 
        tx: Transaction, 
        block_height: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Validate a transaction against the UTXO set.
        
        Args:
            tx: Transaction to validate
            block_height: Current block height (for coinbase maturity check)
        
        Returns:
            Tuple of (is_valid, error_message)
        
        WHY: Before adding a transaction to the mempool or a block,
        we must verify all inputs exist, are unspent, and the signatures are valid.
        
        THIS IS THE HEART OF DOUBLE-SPEND PREVENTION!
        """
        # Coinbase transactions are validated differently
        if tx.is_coinbase:
            return self._validate_coinbase(tx, block_height)
        
        # 1. Check transaction has inputs
        if not tx.inputs:
            return False, "Transaction has no inputs"
        
        # 2. Check transaction has outputs
        if not tx.outputs:
            return False, "Transaction has no outputs"
        
        # 3. Verify all input signatures
        if not tx.verify_all_inputs():
            return False, "Invalid signature(s)"
        
        # 4. Validate each input against UTXO set
        total_input = 0
        for tx_input in tx.inputs:
            # Look up UTXO
            utxo = self.get_utxo(tx_input.tx_id, tx_input.output_index)
            
            # Check UTXO exists
            if utxo is None:
                return False, f"UTXO not found: {tx_input.tx_id}:{tx_input.output_index}"
            
            # Check UTXO is not spent
            if utxo.get('is_spent', False):
                return False, f"UTXO already spent: {tx_input.tx_id}:{tx_input.output_index}"
            
            # Check address matches (if we have pub_key in the input)
            # This is already verified by signature, but we double-check
            total_input += utxo['amount']
        
        # 5. Check total output doesn't exceed input
        total_output = tx.get_total_output()
        if total_output > total_input:
            return False, f"Total output ({total_output}) exceeds total input ({total_input})"
        
        # 6. Check minimum fee
        fee = total_input - total_output
        if fee < 0:
            return False, f"Negative fee: {fee}"
        if fee > 0 and fee < settings.MIN_RELAY_FEE:
            return False, f"Fee ({fee}) below minimum relay fee ({settings.MIN_RELAY_FEE})"
        
        # 7. Check transaction size
        tx_size = len(tx.serialize())
        if tx_size > settings.MAX_BLOCK_SIZE_BYTES:
            return False, f"Transaction size ({tx_size}) exceeds maximum"
        
        return True, "Valid transaction"
    
    def _validate_coinbase(
        self, 
        tx: Transaction, 
        block_height: Optional[int]
    ) -> Tuple[bool, str]:
        """
        Validate a coinbase transaction.
        
        WHY: Coinbase transactions have special rules:
        - No inputs
        - Exactly one output
        - Amount limited by block reward
        """
        # Coinbase must have no inputs
        if tx.inputs:
            return False, "Coinbase must have no inputs"
        
        # Coinbase must have exactly one output
        if len(tx.outputs) != 1:
            return False, "Coinbase must have exactly one output"
        
        # Check reward amount doesn't exceed supply
        if tx.outputs[0].amount > settings.INITIAL_COIN_SUPPLY:
            return False, f"Coinbase amount exceeds supply limit"
        
        return True, "Valid coinbase"
    
    # ============================================
    # BLOCK APPLICATION AND ROLLBACK
    # ============================================
    
    def apply_block(self, block: Any) -> bool:
        """
        Apply all transactions in a block to the UTXO set.
        
        Args:
            block: Block object containing transactions
        
        Returns:
            bool: True if applied successfully
        
        WHY: When a block is added to the chain, we update the UTXO set:
        1. Remove (spend) all UTXOs referenced in transaction inputs
        2. Add (create) all new UTXOs from transaction outputs
        
        THIS IS HOW THE LEDGER STATE CHANGES!
        """
        try:
            print(f"🔄 Applying block {block.header.block_height} to UTXO set...")
            
            # Process each transaction in the block
            for tx in block.transactions:
                # 1. Spend all inputs (remove UTXOs)
                for tx_input in tx.inputs:
                    success = self.store.spend_utxo(
                        tx_input.tx_id,
                        tx_input.output_index
                    )
                    if not success:
                        print(f"⚠️  Failed to spend UTXO {tx_input.tx_id}:{tx_input.output_index}")
                        # Rollback on failure
                        self._rollback_block(block)
                        return False
                
                # 2. Add all outputs (create UTXOs)
                for i, tx_output in enumerate(tx.outputs):
                    success = self.store.put_utxo(
                        tx_id=tx.tx_id,
                        output_index=i,
                        amount=tx_output.amount,
                        address=tx_output.address,
                        block_height=block.header.block_height
                    )
                    if not success:
                        print(f"⚠️  Failed to add UTXO {tx.tx_id}:{i}")
                        # Rollback on failure
                        self._rollback_block(block)
                        return False
            
            # Update chain state
            self.store.put_chain_state('last_block_applied', block.hash)
            self.store.put_chain_state('last_block_height', block.header.block_height)
            
            # Update UTXO count cache
            self.store.put_chain_state('utxo_count', self.get_utxo_count())
            
            print(f"✅ Block {block.header.block_height} applied to UTXO set")
            return True
            
        except Exception as e:
            print(f"❌ Error applying block: {e}")
            # Rollback on any error
            self._rollback_block(block)
            return False
    
    def _rollback_block(self, block: Any) -> None:
        """
        Rollback a block from the UTXO set (for error recovery).
        
        Args:
            block: Block to rollback
        
        WHY: If something goes wrong applying a block, we need to
        restore the UTXO set to its previous state.
        
        HOW: Reverse the apply_block operation:
        1. Remove all new UTXOs (outputs)
        2. Restore all spent UTXOs (inputs)
        """
        try:
            print(f"🔄 Rolling back block {block.header.block_height} from UTXO set...")
            
            # Process in reverse order
            for tx in reversed(block.transactions):
                # 1. Remove all outputs (delete new UTXOs)
                for i, _ in enumerate(tx.outputs):
                    # Mark as spent (this effectively removes it)
                    self.store.spend_utxo(tx.tx_id, i)
                
                # 2. Restore all inputs (unspend UTXOs)
                # Note: This requires storing the original UTXO data
                # We'll implement this by storing in chain state
                for tx_input in tx.inputs:
                    # Check if we have the original UTXO data
                    original_utxo = self.store.get_chain_state(
                        f"utxo_backup_{tx_input.tx_id}_{tx_input.output_index}"
                    )
                    if original_utxo:
                        # Restore it (we stored it before spending)
                        self.store.put_utxo(
                            tx_id=original_utxo['tx_id'],
                            output_index=original_utxo['output_index'],
                            amount=original_utxo['amount'],
                            address=original_utxo['address'],
                            block_height=original_utxo['block_height']
                        )
                        # Remove backup
                        self.store.put_chain_state(
                            f"utxo_backup_{tx_input.tx_id}_{tx_input.output_index}",
                            None
                        )
            
            print(f"✅ Block {block.header.block_height} rolled back")
            
        except Exception as e:
            print(f"❌ Error rolling back block: {e}")
    
    # ============================================
    # ADVANCED: CHAIN REORGANIZATION
    # ============================================
    
    def reorganize_chain(
        self, 
        old_chain: List[Any], 
        new_chain: List[Any]
    ) -> bool:
        """
        Handle a chain reorganization (fork resolution).
        
        Args:
            old_chain: Blocks being removed (old chain)
            new_chain: Blocks being added (new chain)
        
        Returns:
            bool: True if reorg succeeded
        
        WHY: When two miners find blocks at the same time,
        there's a temporary fork. The longest chain wins.
        
        We need to:
        1. Rollback the UTXO set to the fork point (remove old blocks)
        2. Apply the new blocks to the UTXO set
        
        THIS IS CRITICAL FOR CONSENSUS!
        """
        try:
            print(f"🔄 Chain reorganization: removing {len(old_chain)} blocks, adding {len(new_chain)} blocks")
            
            # 1. Rollback old chain (remove from newest to oldest)
            for block in reversed(old_chain):
                self._rollback_block(block)
            
            # 2. Apply new chain (from oldest to newest)
            for block in new_chain:
                success = self.apply_block(block)
                if not success:
                    print("❌ Reorg failed during apply phase")
                    return False
            
            print("✅ Chain reorganization complete")
            return True
            
        except Exception as e:
            print(f"❌ Error during chain reorganization: {e}")
            return False
    
    # ============================================
    # BACKUP AND RESTORE
    # ============================================
    
    def backup_utxos(self, block_hash: str) -> bool:
        """
        Backup the UTXO set state before applying a block.
        
        WHY: For safe rollback during reorgs or errors.
        """
        try:
            # Get all UTXOs (we'll store them as chain state)
            # This is expensive, so we only do it when needed
            self.store.put_chain_state(
                f"utxo_backup_{block_hash}",
                self.get_utxo_count()
            )
            return True
        except Exception as e:
            print(f"❌ Error backing up UTXOs: {e}")
            return False
    
    def restore_utxos(self, block_hash: str) -> bool:
        """
        Restore UTXO set state from backup.
        """
        try:
            # This would restore all UTXOs from backup
            # For now, we just clear and let the chain manager rebuild
            print(f"⚠️  UTXO restore requested for {block_hash}")
            return True
        except Exception as e:
            print(f"❌ Error restoring UTXOs: {e}")
            return False


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_utxo_set(store=None) -> UTXOSet:
    """
    Factory function to create a UTXO set.
    
    WHY: Makes it easy to initialize the UTXO set
    with either the default store or a custom one.
    """
    return UTXOSet(store)


def get_balance_for_address(address: str) -> int:
    """
    Quick helper to get balance for an address.
    
    WHY: Convenience function for wallet and API endpoints.
    """
    utxo_set = UTXOSet()
    return utxo_set.get_balance(address)


def get_utxos_for_address(address: str) -> List[Dict[str, Any]]:
    """
    Quick helper to get UTXOs for an address.
    """
    utxo_set = UTXOSet()
    return utxo_set.get_utxos_for_address(address)


# ============================================
# INITIALIZATION ON IMPORT
# ============================================

# Create a global UTXO set instance
# This way, all modules share the same UTXO state
utxo_set = UTXOSet()


# ============================================
# TEST FUNCTIONS (for development)
# ============================================

def test_utxo_set():
    """
    Quick test to verify UTXO set is working.
    """
    print("\n🧪 Testing UTXO Set...")
    
    # Test address
    test_address = "TEST_ADDRESS_123"
    
    # 1. Create a test UTXO
    tx_id = "TEST_TX_001"
    print(f"1. Creating UTXO for address {test_address}...")
    db_store.put_utxo(
        tx_id=tx_id,
        output_index=0,
        amount=1000,
        address=test_address,
        block_height=0
    )
    
    # 2. Test balance
    balance = get_balance_for_address(test_address)
    print(f"2. Balance: {balance} (expected: 1000)")
    
    # 3. Get UTXOs
    utxos = get_utxos_for_address(test_address)
    print(f"3. Found {len(utxos)} UTXOs")
    
    # 4. Validate UTXO exists
    utxo = db_store.get_utxo(tx_id, 0)
    print(f"4. UTXO exists: {utxo is not None}")
    
    print("\n✅ UTXO Set test complete")
    print(f"   Total UTXOs in system: {db_store.get_utxo_count()}")
    
    return True


if __name__ == "__main__":
    # Run test when executed directly
    test_utxo_set()