"""
SQLite Store Implementation
===========================
Development database backend using SQLite (built into Python).
WHY: SQLite works on Windows, macOS, and Linux without compilation.
It's perfect for development and testing.

ADDED: Debug logging for UTXO queries to troubleshoot balance issues.
FIXED: get_chain_state returns JSON string (not deserialized object).
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import time

# Import both settings and helper functions
from config import settings, get_database_path
from .base_store import BaseStore


class SQLiteStore(BaseStore):
    """
    SQLite implementation of BaseStore.
    Uses a single SQLite database file with multiple tables.
    """
    
    def __init__(self):
        """
        Initialize SQLite database connection.
        Creates database file and tables if they don't exist.
        """
        # Get database path from config helper function
        self.db_path = get_database_path()
        
        # Create data directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database (creates file if not exists)
        self.connection = None
        self.cursor = None
        
        # Initialize database
        self._connect()
        self._create_tables()
        
        print(f"✅ SQLite store initialized: {self.db_path}")
    
    def _connect(self) -> None:
        """
        Connect to SQLite database with performance optimizations.
        
        WHY: SQLite needs specific pragmas for blockchain workloads:
        - WAL mode: better concurrency
        - NORMAL synchronous: good balance of speed and safety
        """
        self.connection = sqlite3.connect(
            str(self.db_path),
            timeout=30,  # Wait up to 30 seconds if database is locked
            check_same_thread=False,  # Allow multi-threaded access
        )
        
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")
        
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode = WAL")
        
        # Use NORMAL synchronous for better performance
        self.connection.execute("PRAGMA synchronous = NORMAL")
        
        # Increase cache size
        self.connection.execute("PRAGMA cache_size = -10000")  # 10MB cache
        
        self.cursor = self.connection.cursor()
    
    def _create_tables(self) -> None:
        """
        Create all necessary tables if they don't exist.
        
        WHY: Tables are created once when the database is first initialized.
        We use IF NOT EXISTS so it's safe to run multiple times.
        """
        # Blocks table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_hash TEXT PRIMARY KEY,
                block_height INTEGER UNIQUE NOT NULL,
                block_data TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(block_height)")
        
        # Transactions table (for indexing)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                block_hash TEXT NOT NULL,
                tx_data TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (block_hash) REFERENCES blocks(block_hash)
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_block ON transactions(block_hash)")
        
        # UTXO table (spendable outputs)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS utxos (
                tx_id TEXT NOT NULL,
                output_index INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                address TEXT NOT NULL,
                block_height INTEGER NOT NULL,
                is_spent INTEGER DEFAULT 0,
                spent_at INTEGER NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (tx_id, output_index)
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_utxos_address ON utxos(address)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_utxos_is_spent ON utxos(is_spent)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_utxos_height ON utxos(block_height)")
        
        # Chain state table (metadata)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS chain_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        
        self.connection.commit()
    
    def _serialize(self, data: Any) -> str:
        """Serialize Python object to JSON for storage"""
        return json.dumps(data, default=str)
    
    def _deserialize(self, data: str) -> Any:
        """Deserialize JSON string to Python object"""
        return json.loads(data)
    
    # ============================================
    # BLOCK STORAGE METHODS
    # ============================================
    
    def put_block(self, block_hash: str, block_data: Dict[str, Any]) -> bool:
        """Store a block in the database"""
        try:
            height = block_data['header']['block_height']
            
            self.cursor.execute("""
                INSERT OR REPLACE INTO blocks (block_hash, block_height, block_data, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                block_hash,
                height,
                self._serialize(block_data),
                int(time.time())
            ))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing block {block_hash}: {e}")
            return False
    
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve a block by hash"""
        try:
            self.cursor.execute("SELECT block_data FROM blocks WHERE block_hash = ?", (block_hash,))
            row = self.cursor.fetchone()
            if row:
                return self._deserialize(row[0])
            return None
        except Exception as e:
            print(f"❌ Error retrieving block {block_hash}: {e}")
            return None
    
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        """Retrieve a block by its height"""
        try:
            self.cursor.execute("SELECT block_data FROM blocks WHERE block_height = ?", (height,))
            row = self.cursor.fetchone()
            if row:
                return self._deserialize(row[0])
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
        """Get the current chain height (number of blocks)"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM blocks")
            count = self.cursor.fetchone()[0]
            return count
        except Exception as e:
            print(f"❌ Error getting chain height: {e}")
            return 0
    
    # ============================================
    # UTXO STORAGE METHODS - WITH DEBUG LOGGING
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
            self.cursor.execute("""
                INSERT OR REPLACE INTO utxos (tx_id, output_index, amount, address, block_height, is_spent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tx_id,
                output_index,
                amount,
                address,
                block_height,
                0,  # is_spent = False
                int(time.time())
            ))
            
            self.connection.commit()
            print(f"✅ UTXO stored: {tx_id[:16]}...:{output_index} = {amount} satoshis to {address[:10]}...")
            return True
        except Exception as e:
            print(f"❌ Error storing UTXO {tx_id}:{output_index}: {e}")
            return False
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        """Retrieve a UTXO"""
        try:
            self.cursor.execute("""
                SELECT tx_id, output_index, amount, address, block_height, is_spent
                FROM utxos 
                WHERE tx_id = ? AND output_index = ?
            """, (tx_id, output_index))
            
            row = self.cursor.fetchone()
            if row:
                return {
                    'tx_id': row[0],
                    'output_index': row[1],
                    'amount': row[2],
                    'address': row[3],
                    'block_height': row[4],
                    'is_spent': bool(row[5])
                }
            return None
        except Exception as e:
            print(f"❌ Error retrieving UTXO {tx_id}:{output_index}: {e}")
            return None
    
    def spend_utxo(self, tx_id: str, output_index: int) -> bool:
        """Mark a UTXO as spent"""
        try:
            self.cursor.execute("""
                UPDATE utxos 
                SET is_spent = 1, spent_at = ?
                WHERE tx_id = ? AND output_index = ?
            """, (int(time.time()), tx_id, output_index))
            
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            print(f"❌ Error spending UTXO {tx_id}:{output_index}: {e}")
            return False
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        """Get all unspent UTXOs for an address - WITH DEBUG LOGGING"""
        try:
            print(f"🔍 SQLite: Querying UTXOs for address: {address[:10]}...")
            self.cursor.execute("""
                SELECT tx_id, output_index, amount, block_height, is_spent
                FROM utxos 
                WHERE address = ? AND is_spent = 0
                ORDER BY block_height ASC
            """, (address,))
            
            rows = self.cursor.fetchall()
            print(f"🔍 SQLite: Found {len(rows)} UTXOs for {address[:10]}...")
            
            result = []
            for row in rows:
                utxo_data = {
                    'tx_id': row[0],
                    'output_index': row[1],
                    'amount': row[2],
                    'block_height': row[3]
                }
                result.append(utxo_data)
                print(f"   UTXO: {row[0][:16]}... idx:{row[1]} amt:{row[2]} at height:{row[3]}")
            return result
        except Exception as e:
            print(f"❌ Error getting UTXOs for address {address}: {e}")
            return []
    
    def get_utxo_count(self) -> int:
        """Get total number of unspent UTXOs"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM utxos WHERE is_spent = 0")
            count = self.cursor.fetchone()[0]
            return count
        except Exception as e:
            print(f"❌ Error getting UTXO count: {e}")
            return 0
    
    # ============================================
    # CHAIN STATE METHODS - FIXED
    # ============================================
    
    def put_chain_state(self, key: str, value: Any) -> bool:
        """
        Store chain metadata.
        
        FIXED: Always store as JSON string for consistency.
        """
        try:
            # Always serialize to JSON string for consistency
            if isinstance(value, (dict, list)):
                value_json = json.dumps(value)
            elif isinstance(value, str):
                # If it's already a string, keep it as is (but it might be JSON)
                try:
                    json.loads(value)
                    value_json = value  # It's valid JSON string
                except:
                    value_json = json.dumps(value)  # It's a plain string
            else:
                value_json = json.dumps(value)
            
            self.cursor.execute("""
                INSERT OR REPLACE INTO chain_state (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value_json, int(time.time())))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing chain state '{key}': {e}")
            return False
    
    def get_chain_state(self, key: str) -> Optional[str]:
        """
        Retrieve chain metadata.
        
        FIXED: Returns JSON string (not deserialized object) for consistency.
        """
        try:
            self.cursor.execute("SELECT value FROM chain_state WHERE key = ?", (key,))
            row = self.cursor.fetchone()
            if row:
                # Return the JSON string directly (not deserialized)
                return row[0]
            return None
        except Exception as e:
            print(f"❌ Error retrieving chain state '{key}': {e}")
            return None
    
    # ============================================
    # TRANSACTION STORAGE METHODS
    # ============================================
    
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        """Store a transaction"""
        try:
            block_hash = tx_data.get('block_hash', 'unknown')
            
            self.cursor.execute("""
                INSERT OR REPLACE INTO transactions (tx_id, block_hash, tx_data, created_at)
                VALUES (?, ?, ?, ?)
            """, (tx_id, block_hash, self._serialize(tx_data), int(time.time())))
            
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing transaction {tx_id}: {e}")
            return False
    
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a transaction by ID"""
        try:
            self.cursor.execute("SELECT tx_data FROM transactions WHERE tx_id = ?", (tx_id,))
            row = self.cursor.fetchone()
            if row:
                return self._deserialize(row[0])
            return None
        except Exception as e:
            print(f"❌ Error retrieving transaction {tx_id}: {e}")
            return None
    
    # ============================================
    # MAINTENANCE METHODS
    # ============================================
    
    def close(self) -> None:
        """Close database connection"""
        if self.connection:
            self.connection.close()
            print("✅ SQLite connection closed")
    
    def clear(self) -> bool:
        """
        Clear all data (for testing)
        WARNING: This deletes ALL data!
        """
        try:
            # Drop all tables
            tables = ['blocks', 'transactions', 'utxos', 'chain_state']
            for table in tables:
                self.cursor.execute(f"DROP TABLE IF EXISTS {table}")
            
            # Recreate tables
            self._create_tables()
            self.connection.commit()
            
            print("✅ Database cleared")
            return True
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
            return False