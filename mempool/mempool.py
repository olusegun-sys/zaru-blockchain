"""
ZARU Mempool Module
===================
Manages pending transactions with PostgreSQL persistence.

FIXED: PostgreSQL-backed mempool for shared access across API and Miner services.
FIXED: Transactions persist across service restarts.
FIXED: Both API and Miner can read/write from the same mempool.
FIXED: Proper import of database store.
"""

import time
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from config import settings
from database import store as db_store
from blockchain.transaction import Transaction, TxInput, TxOutput


class Mempool:
    """
    Manages pending transactions with PostgreSQL persistence.
    
    WHY: The API and Miner run as separate processes on Render.
    We need a shared mempool so transactions added by the API
    are visible to the Miner.
    """
    
    def __init__(self, max_size: int = None, expiry_hours: int = None):
        self.max_size = max_size or getattr(settings, 'MEMPOOL_MAX_SIZE', 10000)
        self.expiry_hours = expiry_hours or getattr(settings, 'MEMPOOL_EXPIRY_HOURS', 72)
        self._cache: Dict[str, Dict] = {}  # In-memory cache for performance
        self._utxo_cache: Dict[str, int] = {}  # Track spent UTXOs to prevent double-spends
        self._load_from_database()
        print(f"✅ Mempool initialized: max_size={self.max_size}, expiry={self.expiry_hours}h, persistent={self._get_mempool_count()} pending txs")
    
    # ============================================
    # PERSISTENCE LAYER
    # ============================================
    
    def _get_mempool_count(self) -> int:
        """Get count of pending transactions from database."""
        try:
            txs = db_store.get_chain_state('mempool_transactions')
            if txs:
                return len(json.loads(txs))
            return 0
        except:
            return 0
    
    def _load_from_database(self):
        """Load pending transactions from PostgreSQL into cache."""
        try:
            txs_json = db_store.get_chain_state('mempool_transactions')
            if txs_json:
                txs_data = json.loads(txs_json)
                print(f"📥 Loaded {len(txs_data)} transactions from PostgreSQL")
                self._cache = {}
                self._utxo_cache = {}
                for tx_id, tx_dict in txs_data.items():
                    # Check if transaction has expired
                    if tx_dict.get('timestamp', 0) < time.time() - (self.expiry_hours * 3600):
                        print(f"⏰ Expired transaction removed: {tx_id[:16]}...")
                        continue
                    self._cache[tx_id] = tx_dict
                    # Cache UTXOs being spent
                    for tx_input in tx_dict.get('inputs', []):
                        utxo_key = f"{tx_input['tx_id']}:{tx_input['output_index']}"
                        self._utxo_cache[utxo_key] = tx_dict.get('timestamp', 0)
                print(f"✅ {len(self._cache)} transactions loaded into cache")
            else:
                print(f"📭 No pending transactions in PostgreSQL")
        except Exception as e:
            print(f"⚠️ Failed to load mempool from database: {e}")
    
    def _save_to_database(self):
        """Save all pending transactions to PostgreSQL."""
        try:
            # Clean expired transactions first
            self._remove_expired()
            
            txs_json = json.dumps(self._cache)
            db_store.put_chain_state('mempool_transactions', txs_json)
            db_store.put_chain_state('mempool_size', len(self._cache))
            db_store.put_chain_state('mempool_last_updated', time.time())
        except Exception as e:
            print(f"⚠️ Failed to save mempool to database: {e}")
    
    def _remove_expired(self):
        """Remove expired transactions from cache."""
        now = time.time()
        expired = []
        for tx_id, tx_dict in self._cache.items():
            if tx_dict.get('timestamp', 0) < now - (self.expiry_hours * 3600):
                expired.append(tx_id)
        for tx_id in expired:
            del self._cache[tx_id]
            print(f"⏰ Expired transaction removed: {tx_id[:16]}...")
    
    # ============================================
    # PUBLIC METHODS
    # ============================================
    
    def add_transaction(self, tx: Transaction) -> Tuple[bool, str]:
        """
        Add a transaction to the mempool.
        
        FIXED: Persists to PostgreSQL immediately.
        FIXED: Double-spend detection across API and Miner.
        """
        # 1. Check if already exists
        if tx.tx_id in self._cache:
            return False, f"Transaction already in mempool: {tx.tx_id[:16]}..."
        
        # 2. Check mempool size
        if len(self._cache) >= self.max_size:
            return False, f"Mempool full: {len(self._cache)} / {self.max_size} transactions"
        
        # 3. Check for double-spend (UTXO already spent in mempool)
        for tx_input in tx.inputs:
            utxo_key = f"{tx_input.tx_id}:{tx_input.output_index}"
            if utxo_key in self._utxo_cache:
                return False, f"Double-spend detected: UTXO {utxo_key} already spent in mempool"
        
        # 4. Store transaction in cache
        tx_dict = tx.to_dict()
        tx_dict['timestamp'] = tx.timestamp or int(time.time())
        tx_dict['added_at'] = int(time.time())
        self._cache[tx.tx_id] = tx_dict
        
        # 5. Cache UTXOs being spent
        for tx_input in tx.inputs:
            utxo_key = f"{tx_input.tx_id}:{tx_input.output_index}"
            self._utxo_cache[utxo_key] = tx.timestamp or int(time.time())
        
        # 6. Persist to PostgreSQL immediately
        self._save_to_database()
        
        print(f"✅ Transaction added to mempool: {tx.tx_id[:16]}... (total: {len(self._cache)})")
        return True, "Transaction added to mempool"
    
    def get_transactions(self, limit: int = 100) -> List[Transaction]:
        """
        Get pending transactions from the mempool.
        
        FIXED: Loads from PostgreSQL on every call (ensures miner sees API-added txs).
        """
        # Reload from database to ensure we have the latest
        self._load_from_database()
        
        if not self._cache:
            return []
        
        # Sort by fee (highest first) then by timestamp (oldest first)
        tx_list = list(self._cache.values())
        tx_list.sort(key=lambda x: (-x.get('fee', 0), x.get('timestamp', 0)))
        
        # Limit
        tx_list = tx_list[:limit]
        
        # Convert back to Transaction objects
        transactions = []
        for tx_dict in tx_list:
            try:
                tx = Transaction.from_dict(tx_dict)
                transactions.append(tx)
            except Exception as e:
                print(f"⚠️ Failed to deserialize transaction: {e}")
        
        print(f"📊 get_transactions: returning {len(transactions)} transactions (mempool size: {len(self._cache)})")
        return transactions
    
    def get_transaction(self, tx_id: str) -> Optional[Transaction]:
        """Get a specific transaction by ID."""
        self._load_from_database()
        
        tx_dict = self._cache.get(tx_id)
        if not tx_dict:
            return None
        
        try:
            return Transaction.from_dict(tx_dict)
        except Exception as e:
            print(f"⚠️ Failed to deserialize transaction: {e}")
            return None
    
    def remove_transaction(self, tx_id: str) -> bool:
        """Remove a transaction from the mempool (called when mined)."""
        if tx_id not in self._cache:
            return False
        
        tx_dict = self._cache[tx_id]
        del self._cache[tx_id]
        
        # Remove spent UTXOs from cache
        for tx_input in tx_dict.get('inputs', []):
            utxo_key = f"{tx_input['tx_id']}:{tx_input['output_index']}"
            if utxo_key in self._utxo_cache:
                del self._utxo_cache[utxo_key]
        
        # Persist changes
        self._save_to_database()
        
        print(f"✅ Transaction removed from mempool: {tx_id[:16]}...")
        return True
    
    def remove_transactions(self, tx_ids: List[str]) -> int:
        """Remove multiple transactions from the mempool."""
        removed = 0
        for tx_id in tx_ids:
            if self.remove_transaction(tx_id):
                removed += 1
        return removed
    
    def clear(self) -> None:
        """Clear all pending transactions (for debugging)."""
        self._cache.clear()
        self._utxo_cache.clear()
        self._save_to_database()
        print(f"🧹 Mempool cleared")
    
    def get_mempool_size(self) -> int:
        """Get the number of pending transactions."""
        self._load_from_database()
        return len(self._cache)
    
    def get_state(self) -> Dict[str, Any]:
        """Get mempool state for API responses."""
        self._load_from_database()
        
        total_fees = sum(tx.get('fee', 0) for tx in self._cache.values())
        addresses = set()
        for tx_dict in self._cache.values():
            for output in tx_dict.get('outputs', []):
                addresses.add(output.get('address', ''))
        spent_utxos = len(self._utxo_cache)
        
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'total_fees': total_fees,
            'addresses': len(addresses),
            'spent_utxos': spent_utxos,
            'persistent': True,
        }
    
    def get_pending_balance(self, address: str) -> int:
        """Calculate pending balance for an address."""
        self._load_from_database()
        
        total_pending = 0
        for tx_dict in self._cache.values():
            # Check if this address has pending outputs
            for output in tx_dict.get('outputs', []):
                if output['address'] == address:
                    total_pending += output['amount']
        return total_pending
    
    def _clean_expired(self):
        """Remove expired transactions."""
        self._remove_expired()
        self._save_to_database()


# ============================================
# GLOBAL INSTANCE
# ============================================

mempool = Mempool()


if __name__ == "__main__":
    test_mempool()