"""
RocksDB Store Implementation
============================
Production database backend using RocksDB (high performance).
WHY: RocksDB is optimized for blockchain workloads with billions of keys.
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, List, Any

# Import both settings and helper functions
from config import settings, get_data_dir
from .base_store import BaseStore

# Try to import rocksdb (may not be available on Windows)
try:
    import rocksdb
    ROCKSDB_AVAILABLE = True
except ImportError:
    rocksdb = None
    ROCKSDB_AVAILABLE = False


class RocksDBStore(BaseStore):
    """
    RocksDB implementation of BaseStore.
    Uses a key-value database with prefix-based keying for different data types.
    """
    
    def __init__(self):
        """Initialize RocksDB connection"""
        if not ROCKSDB_AVAILABLE:
            raise ImportError(
                "RocksDB not installed. Please install python-rocksdb.\n"
                "On Linux: pip install python-rocksdb\n"
                "On Windows: Use SQLite backend instead (set DB_BACKEND=sqlite)"
            )
        
        # Get database directory using helper function
        self.db_path = get_data_dir() / "rocksdb_data"
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Configure RocksDB options
        self.opts = rocksdb.Options()
        
        # Performance optimizations
        self.opts.create_if_missing = True
        self.opts.max_open_files = 1000
        self.opts.write_buffer_size = 64 * 1024 * 1024  # 64MB
        self.opts.max_write_buffer_number = 3
        self.opts.target_file_size_base = 64 * 1024 * 1024  # 64MB
        
        # Enable compression
        self.opts.compression = rocksdb.CompressionType.snappy_compression
        
        # Bloom filter for fast lookups
        self.opts.filter_policy = rocksdb.BloomFilterPolicy(10)
        
        # Open database
        self.db = rocksdb.DB(str(self.db_path), self.opts, read_only=False)
        
        # Create write batch for performance
        self.batch = rocksdb.WriteBatch()
        self.batch_size = 0
        
        print(f"✅ RocksDB store initialized: {self.db_path}")
    
    def _make_key(self, prefix: str, key: str) -> bytes:
        """
        Create a key with prefix for data organization.
        
        WHY: In key-value stores, we use prefixes to organize data:
        b:block_ -> block data
        u:utxo_ -> UTXO data
        t:tx_ -> transaction data
        c:chain_ -> chain state
        """
        return f"{prefix}:{key}".encode()
    
    def _serialize(self, data: Any) -> str:
        """Serialize Python object to JSON"""
        return json.dumps(data, default=str)
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize JSON to Python object"""
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data)
    
    def _write_batch(self) -> None:
        """Write the current batch to database"""
        if self.batch_size > 0:
            self.db.write(self.batch)
            self.batch = rocksdb.WriteBatch()
            self.batch_size = 0
    
    # ============================================
    # BLOCK STORAGE METHODS
    # ============================================
    
    def put_block(self, block_hash: str, block_data: Dict[str, Any]) -> bool:
        """Store a block in the database"""
        try:
            key = self._make_key('block', block_hash)
            value = self._serialize(block_data)
            
            self.batch.put(key, value.encode())
            self.batch_size += 1
            
            # Also store by height for easy lookup
            height = block_data['header']['block_height']
            height_key = self._make_key('height', str(height))
            self.batch.put(height_key, block_hash.encode())
            self.batch_size += 1
            
            # Auto-write if batch is large
            if self.batch_size >= 100:
                self._write_batch()
            
            return True
        except Exception as e:
            print(f"❌ Error storing block {block_hash}: {e}")
            return False
    
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve a block by hash"""
        try:
            key = self._make_key('block', block_hash)
            value = self.db.get(key)
            if value:
                return self._deserialize(value)
            return None
        except Exception as e:
            print(f"❌ Error retrieving block {block_hash}: {e}")
            return None
    
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        """Retrieve a block by its height"""
        try:
            # Get block hash from height index
            height_key = self._make_key('height', str(height))
            block_hash = self.db.get(height_key)
            if block_hash:
                return self.get_block(block_hash.decode())
            return None
        except Exception as e:
            print(f"❌ Error retrieving block at height {height}: {e}")
            return None
    
    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent block"""
        try:
            height = self.get_chain_height()
            if height == 0:
                return None
            return self.get_block_by_height(height - 1)
        except Exception as e:
            print(f"❌ Error retrieving latest block: {e}")
            return None
    
    def get_chain_height(self) -> int:
        """Get the current chain height"""
        try:
            height_key = self._make_key('chain', 'height')
            value = self.db.get(height_key)
            if value:
                return int(value.decode())
            return 0
        except Exception as e:
            print(f"❌ Error getting chain height: {e}")
            return 0
    
    # ============================================
    # UTXO STORAGE METHODS
    # ============================================
    
    def put_utxo(
        self, 
        tx_id: str, 
        output_index: int, 
        amount: int, 
        address: str,
        block_height: int
    ) -> bool:
        """Store a UTXO"""
        try:
            key = self._make_key('utxo', f"{tx_id}:{output_index}")
            value = self._serialize({
                'tx_id': tx_id,
                'output_index': output_index,
                'amount': amount,
                'address': address,
                'block_height': block_height,
                'is_spent': False
            })
            
            self.batch.put(key, value.encode())
            self.batch_size += 1
            
            # Add to address index
            address_key = self._make_key('addr', f"{address}:{tx_id}:{output_index}")
            self.batch.put(address_key, key)
            self.batch_size += 1
            
            if self.batch_size >= 100:
                self._write_batch()
            
            return True
        except Exception as e:
            print(f"❌ Error storing UTXO {tx_id}:{output_index}: {e}")
            return False
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        """Retrieve a UTXO"""
        try:
            key = self._make_key('utxo', f"{tx_id}:{output_index}")
            value = self.db.get(key)
            if value:
                return self._deserialize(value)
            return None
        except Exception as e:
            print(f"❌ Error retrieving UTXO {tx_id}:{output_index}: {e}")
            return None
    
    def spend_utxo(self, tx_id: str, output_index: int) -> bool:
        """Mark a UTXO as spent"""
        try:
            key = self._make_key('utxo', f"{tx_id}:{output_index}")
            value = self.db.get(key)
            if value:
                data = self._deserialize(value)
                data['is_spent'] = True
                data['spent_at'] = int(time.time())
                
                self.batch.put(key, self._serialize(data).encode())
                self.batch_size += 1
                
                if self.batch_size >= 100:
                    self._write_batch()
                
                return True
            return False
        except Exception as e:
            print(f"❌ Error spending UTXO {tx_id}:{output_index}: {e}")
            return False
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        """Get all unspent UTXOs for an address"""
        try:
            result = []
            prefix = f"addr:{address}:".encode()
            
            # Iterate over all keys for this address
            it = self.db.iteritems()
            it.seek(prefix)
            
            for key, value in it:
                if not key.startswith(prefix):
                    break
                # Get the UTXO key
                utxo_key = value  # value contains the UTXO key
                utxo_data = self.db.get(utxo_key)
                if utxo_data:
                    data = self._deserialize(utxo_data)
                    if not data.get('is_spent', False):
                        result.append({
                            'tx_id': data['tx_id'],
                            'output_index': data['output_index'],
                            'amount': data['amount'],
                            'block_height': data['block_height']
                        })
            
            return result
        except Exception as e:
            print(f"❌ Error getting UTXOs for address {address}: {e}")
            return []
    
    def get_utxo_count(self) -> int:
        """Get total number of unspent UTXOs"""
        try:
            # Count all UTXOs that are not spent
            # This is inefficient in RocksDB - use chain state caching
            count_key = self._make_key('chain', 'utxo_count')
            value = self.db.get(count_key)
            if value:
                return int(value.decode())
            
            # If not cached, count manually (slow - only on first run)
            count = 0
            prefix = "utxo:".encode()
            it = self.db.iteritems()
            it.seek(prefix)
            
            for key, value in it:
                if not key.startswith(prefix):
                    break
                data = self._deserialize(value)
                if not data.get('is_spent', False):
                    count += 1
            
            # Cache the count
            self.put_chain_state('utxo_count', count)
            return count
        except Exception as e:
            print(f"❌ Error getting UTXO count: {e}")
            return 0
    
    # ============================================
    # CHAIN STATE METHODS
    # ============================================
    
    def put_chain_state(self, key: str, value: Any) -> bool:
        """Store chain metadata"""
        try:
            db_key = self._make_key('chain', key)
            self.batch.put(db_key, str(value).encode())
            self.batch_size += 1
            
            if self.batch_size >= 100:
                self._write_batch()
            
            return True
        except Exception as e:
            print(f"❌ Error storing chain state {key}: {e}")
            return False
    
    def get_chain_state(self, key: str) -> Optional[Any]:
        """Retrieve chain metadata"""
        try:
            db_key = self._make_key('chain', key)
            value = self.db.get(db_key)
            if value:
                return self._deserialize(value)
            return None
        except Exception as e:
            print(f"❌ Error retrieving chain state {key}: {e}")
            return None
    
    # ============================================
    # TRANSACTION STORAGE METHODS
    # ============================================
    
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        """Store a transaction"""
        try:
            key = self._make_key('tx', tx_id)
            value = self._serialize(tx_data)
            
            self.batch.put(key, value.encode())
            self.batch_size += 1
            
            if self.batch_size >= 100:
                self._write_batch()
            
            return True
        except Exception as e:
            print(f"❌ Error storing transaction {tx_id}: {e}")
            return False
    
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a transaction by ID"""
        try:
            key = self._make_key('tx', tx_id)
            value = self.db.get(key)
            if value:
                return self._deserialize(value)
            return None
        except Exception as e:
            print(f"❌ Error retrieving transaction {tx_id}: {e}")
            return None
    
    # ============================================
    # MAINTENANCE METHODS
    # ============================================
    
    def close(self) -> None:
        """Close database connection"""
        # Write any pending batch
        self._write_batch()
        print("✅ RocksDB connection closed")
    
    def clear(self) -> bool:
        """
        Clear all data (for testing)
        WARNING: This deletes ALL data!
        """
        try:
            # Close current connection
            self.close()
            
            # Delete database directory
            import shutil
            shutil.rmtree(str(self.db_path))
            
            # Reopen database
            self.db_path.mkdir(parents=True, exist_ok=True)
            self.db = rocksdb.DB(str(self.db_path), self.opts, read_only=False)
            self.batch = rocksdb.WriteBatch()
            self.batch_size = 0
            
            print("✅ RocksDB database cleared")
            return True
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
            return False