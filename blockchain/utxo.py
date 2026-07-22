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

FIXED: Coinbase validation uses MAX_COINBASE_REWARD from config.
"""

import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from config import settings
from database import store as db_store
from blockchain.transaction import Transaction, TxInput, TxOutput


class UTXOSet:
    """
    Manages all unspent transaction outputs.
    
    The UTXO set is the "live state" of the blockchain.
    It tracks which coins exist and who owns them.
    """
    
    def __init__(self, store=None):
        self.store = store if store else db_store
        print(f"✅ UTXO Set initialized with {self.store.get_utxo_count()} UTXOs")
    
    # ============================================
    # UTXO QUERY METHODS
    # ============================================
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        return self.store.get_utxo(tx_id, output_index)
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        return self.store.get_utxos_for_address(address)
    
    def get_balance(self, address: str) -> int:
        utxos = self.get_utxos_for_address(address)
        return sum(utxo['amount'] for utxo in utxos)
    
    def get_utxo_count(self) -> int:
        return self.store.get_utxo_count()
    
    def get_total_supply(self) -> int:
        cached = self.store.get_chain_state('total_supply')
        if cached is not None:
            return int(cached)
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
        utxos = self.get_utxos_for_address(address)
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
            return [], 0
        
        return selected, total
    
    def calculate_fee(
        self, 
        input_count: int, 
        output_count: int,
        fee_per_byte: int = None
    ) -> int:
        if fee_per_byte is None:
            fee_per_byte = settings.DEFAULT_FEE_PER_KB // 1024
        
        estimated_size = 10 + (input_count * 148) + (output_count * 34)
        fee = estimated_size * fee_per_byte
        return max(fee, settings.MIN_RELAY_FEE)
    
    # ============================================
    # TRANSACTION VALIDATION
    # ============================================
    
    def validate_transaction(
        self, 
        tx: Transaction, 
        block_height: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Validate a transaction against the UTXO set."""
        if tx.is_coinbase:
            return self._validate_coinbase(tx, block_height)
        
        if not tx.inputs:
            return False, "Transaction has no inputs"
        
        if not tx.outputs:
            return False, "Transaction has no outputs"
        
        if not tx.verify_all_inputs():
            return False, "Invalid signature(s)"
        
        total_input = 0
        for tx_input in tx.inputs:
            utxo = self.get_utxo(tx_input.tx_id, tx_input.output_index)
            
            if utxo is None:
                return False, f"UTXO not found: {tx_input.tx_id}:{tx_input.output_index}"
            
            if utxo.get('is_spent', False):
                return False, f"UTXO already spent: {tx_input.tx_id}:{tx_input.output_index}"
            
            total_input += utxo['amount']
        
        total_output = tx.get_total_output()
        if total_output > total_input:
            return False, f"Total output ({total_output}) exceeds total input ({total_input})"
        
        fee = total_input - total_output
        if fee < 0:
            return False, f"Negative fee: {fee}"
        if fee > 0 and fee < settings.MIN_RELAY_FEE:
            return False, f"Fee ({fee}) below minimum relay fee ({settings.MIN_RELAY_FEE})"
        
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
        
        FIXED: Uses MAX_COINBASE_REWARD instead of INITIAL_COIN_SUPPLY.
        """
        if tx.inputs:
            return False, "Coinbase must have no inputs"
        
        if len(tx.outputs) != 1:
            return False, "Coinbase must have exactly one output"
        
        # FIXED: Check against MAX_COINBASE_REWARD, not total supply
        MAX_COINBASE_REWARD = getattr(settings, 'MAX_COINBASE_REWARD', 5_000_000_000)
        if tx.outputs[0].amount > MAX_COINBASE_REWARD:
            return False, f"Coinbase amount ({tx.outputs[0].amount}) exceeds max reward ({MAX_COINBASE_REWARD})"
        
        print(f"✅ Coinbase validated: {tx.outputs[0].amount} satoshis to {tx.outputs[0].address[:10]}...")
        return True, "Valid coinbase"
    
    # ============================================
    # BLOCK APPLICATION AND ROLLBACK
    # ============================================
    
    def apply_block(self, block: Any) -> bool:
        """Apply all transactions in a block to the UTXO set."""
        try:
            print(f"🔄 Applying block {block.header.block_height} to UTXO set...")
            print(f"   Transactions in block: {len(block.transactions)}")
            
            for tx in block.transactions:
                print(f"   Processing tx: {tx.tx_id[:16]}... (coinbase: {tx.is_coinbase})")
                
                # 1. Spend all inputs
                for tx_input in tx.inputs:
                    success = self.store.spend_utxo(
                        tx_input.tx_id,
                        tx_input.output_index
                    )
                    if not success:
                        print(f"⚠️ Failed to spend UTXO {tx_input.tx_id}:{tx_input.output_index}")
                        self._rollback_block(block)
                        return False
                
                # 2. Add all outputs
                for i, tx_output in enumerate(tx.outputs):
                    print(f"      Adding output {i}: {tx_output.amount} satoshis to {tx_output.address[:10]}...")
                    success = self.store.put_utxo(
                        tx_id=tx.tx_id,
                        output_index=i,
                        amount=tx_output.amount,
                        address=tx_output.address,
                        block_height=block.header.block_height
                    )
                    if not success:
                        print(f"⚠️ Failed to add UTXO {tx.tx_id}:{i}")
                        self._rollback_block(block)
                        return False
            
            self.store.put_chain_state('last_block_applied', block.hash)
            self.store.put_chain_state('last_block_height', block.header.block_height)
            self.store.put_chain_state('utxo_count', self.get_utxo_count())
            
            print(f"✅ Block {block.header.block_height} applied to UTXO set")
            return True
            
        except Exception as e:
            print(f"❌ Error applying block: {e}")
            self._rollback_block(block)
            return False
    
    def _rollback_block(self, block: Any) -> None:
        """Rollback a block from the UTXO set."""
        try:
            print(f"🔄 Rolling back block {block.header.block_height} from UTXO set...")
            
            for tx in reversed(block.transactions):
                for i, _ in enumerate(tx.outputs):
                    self.store.spend_utxo(tx.tx_id, i)
                
                for tx_input in tx.inputs:
                    original_utxo = self.store.get_chain_state(
                        f"utxo_backup_{tx_input.tx_id}_{tx_input.output_index}"
                    )
                    if original_utxo:
                        self.store.put_utxo(
                            tx_id=original_utxo['tx_id'],
                            output_index=original_utxo['output_index'],
                            amount=original_utxo['amount'],
                            address=original_utxo['address'],
                            block_height=original_utxo['block_height']
                        )
                        self.store.put_chain_state(
                            f"utxo_backup_{tx_input.tx_id}_{tx_input.output_index}",
                            None
                        )
            
            print(f"✅ Block {block.header.block_height} rolled back")
            
        except Exception as e:
            print(f"❌ Error rolling back block: {e}")
    
    # ============================================
    # CHAIN REORGANIZATION
    # ============================================
    
    def reorganize_chain(
        self, 
        old_chain: List[Any], 
        new_chain: List[Any]
    ) -> bool:
        try:
            print(f"🔄 Chain reorganization: removing {len(old_chain)} blocks, adding {len(new_chain)} blocks")
            
            for block in reversed(old_chain):
                self._rollback_block(block)
            
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
        try:
            self.store.put_chain_state(
                f"utxo_backup_{block_hash}",
                self.get_utxo_count()
            )
            return True
        except Exception as e:
            print(f"❌ Error backing up UTXOs: {e}")
            return False
    
    def restore_utxos(self, block_hash: str) -> bool:
        try:
            print(f"⚠️ UTXO restore requested for {block_hash}")
            return True
        except Exception as e:
            print(f"❌ Error restoring UTXOs: {e}")
            return False


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def create_utxo_set(store=None) -> UTXOSet:
    return UTXOSet(store)


def get_balance_for_address(address: str) -> int:
    utxo_set = UTXOSet()
    return utxo_set.get_balance(address)


def get_utxos_for_address(address: str) -> List[Dict[str, Any]]:
    utxo_set = UTXOSet()
    return utxo_set.get_utxos_for_address(address)


# ============================================
# GLOBAL INSTANCE
# ============================================

utxo_set = UTXOSet()


if __name__ == "__main__":
    test_utxo_set()