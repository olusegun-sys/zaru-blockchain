"""
PostgreSQL Store Implementation
===============================
Production database backend using PostgreSQL.

WHY: PostgreSQL is more robust than SQLite for production.
It handles concurrent connections better and has better performance.
"""

import os
import json
import time
from typing import Optional, Dict, List, Any
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import Json
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("⚠️  psycopg2 not installed. PostgreSQL not available.")

from .base_store import BaseStore
from config import settings


class PostgresStore(BaseStore):
    """PostgreSQL implementation of BaseStore."""
    
    def __init__(self):
        """Initialize PostgreSQL connection."""
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")
        
        # Get database URL from environment
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        # Connect to database
        self.connection = None
        self.cursor = None
        self._connect()
        self._create_tables()
        
        print(f"✅ PostgreSQL store initialized")
    
    def _connect(self):
        """Connect to PostgreSQL database."""
        self.connection = psycopg2.connect(self.db_url)
        self.cursor = self.connection.cursor()
    
    def _create_tables(self):
        """Create tables if they don't exist."""
        # Blocks table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_hash TEXT PRIMARY KEY,
                block_height INTEGER UNIQUE NOT NULL,
                block_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(block_height)")
        
        # Transactions table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                block_hash TEXT REFERENCES blocks(block_hash),
                tx_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_block ON transactions(block_hash)")
        
        # UTXOs table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS utxos (
                tx_id TEXT,
                output_index INTEGER,
                amount BIGINT NOT NULL,
                address TEXT NOT NULL,
                block_height INTEGER NOT NULL,
                is_spent BOOLEAN DEFAULT FALSE,
                spent_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tx_id, output_index)
            )
        """)
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_utxos_address ON utxos(address)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_utxos_is_spent ON utxos(is_spent)")
        
        # Chain state table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS chain_state (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.connection.commit()
    
    def put_block(self, block_hash: str, block_data: Dict[str, Any]) -> bool:
        """Store a block."""
        try:
            self.cursor.execute(
                "INSERT INTO blocks (block_hash, block_height, block_data) VALUES (%s, %s, %s) ON CONFLICT (block_hash) DO UPDATE SET block_data = EXCLUDED.block_data",
                (block_hash, block_data['header']['block_height'], Json(block_data))
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing block: {e}")
            return False
    
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve a block."""
        try:
            self.cursor.execute("SELECT block_data FROM blocks WHERE block_hash = %s", (block_hash,))
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"❌ Error retrieving block: {e}")
            return None
    
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        """Retrieve a block by height."""
        try:
            self.cursor.execute("SELECT block_data FROM blocks WHERE block_height = %s", (height,))
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"❌ Error retrieving block: {e}")
            return None
    
    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent block."""
        try:
            self.cursor.execute("SELECT block_data FROM blocks ORDER BY block_height DESC LIMIT 1")
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"❌ Error retrieving latest block: {e}")
            return None
    
    def get_chain_height(self) -> int:
        """Get chain height."""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM blocks")
            count = self.cursor.fetchone()[0]
            return count
        except Exception as e:
            print(f"❌ Error getting chain height: {e}")
            return 0
    
    def put_utxo(self, tx_id: str, output_index: int, amount: int, address: str, block_height: int) -> bool:
        """Store a UTXO."""
        try:
            self.cursor.execute("""
                INSERT INTO utxos (tx_id, output_index, amount, address, block_height)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tx_id, output_index) DO UPDATE SET 
                    amount = EXCLUDED.amount,
                    address = EXCLUDED.address,
                    block_height = EXCLUDED.block_height,
                    is_spent = FALSE,
                    spent_at = NULL
            """, (tx_id, output_index, amount, address, block_height))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing UTXO: {e}")
            return False
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        """Retrieve a UTXO."""
        try:
            self.cursor.execute("SELECT tx_id, output_index, amount, address, block_height, is_spent FROM utxos WHERE tx_id = %s AND output_index = %s", (tx_id, output_index))
            row = self.cursor.fetchone()
            if row:
                return {
                    'tx_id': row[0],
                    'output_index': row[1],
                    'amount': row[2],
                    'address': row[3],
                    'block_height': row[4],
                    'is_spent': row[5]
                }
            return None
        except Exception as e:
            print(f"❌ Error retrieving UTXO: {e}")
            return None
    
    def spend_utxo(self, tx_id: str, output_index: int) -> bool:
        """Mark a UTXO as spent."""
        try:
            self.cursor.execute("UPDATE utxos SET is_spent = TRUE, spent_at = CURRENT_TIMESTAMP WHERE tx_id = %s AND output_index = %s", (tx_id, output_index))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error spending UTXO: {e}")
            return False
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        """Get UTXOs for an address."""
        try:
            self.cursor.execute("SELECT tx_id, output_index, amount, block_height FROM utxos WHERE address = %s AND is_spent = FALSE ORDER BY block_height", (address,))
            rows = self.cursor.fetchall()
            return [{
                'tx_id': row[0],
                'output_index': row[1],
                'amount': row[2],
                'block_height': row[3]
            } for row in rows]
        except Exception as e:
            print(f"❌ Error getting UTXOs: {e}")
            return []
    
    def get_utxo_count(self) -> int:
        """Get total number of UTXOs."""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM utxos WHERE is_spent = FALSE")
            count = self.cursor.fetchone()[0]
            return count
        except Exception as e:
            print(f"❌ Error getting UTXO count: {e}")
            return 0
    
    def put_chain_state(self, key: str, value: Any) -> bool:
        """Store chain state."""
        try:
            self.cursor.execute(
                "INSERT INTO chain_state (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP",
                (key, Json(value))
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing chain state: {e}")
            return False
    
    def get_chain_state(self, key: str) -> Optional[Any]:
        """Retrieve chain state."""
        try:
            self.cursor.execute("SELECT value FROM chain_state WHERE key = %s", (key,))
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"❌ Error retrieving chain state: {e}")
            return None
    
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        """Store a transaction."""
        try:
            self.cursor.execute(
                "INSERT INTO transactions (tx_id, block_hash, tx_data) VALUES (%s, %s, %s) ON CONFLICT (tx_id) DO UPDATE SET tx_data = EXCLUDED.tx_data",
                (tx_id, tx_data.get('block_hash', 'unknown'), Json(tx_data))
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing transaction: {e}")
            return False
    
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a transaction."""
        try:
            self.cursor.execute("SELECT tx_data FROM transactions WHERE tx_id = %s", (tx_id,))
            row = self.cursor.fetchone()
            if row:
                return row[0]
            return None
        except Exception as e:
            print(f"❌ Error retrieving transaction: {e}")
            return None
    
    def close(self) -> None:
        """Close the connection."""
        if self.connection:
            self.connection.close()
            print("✅ PostgreSQL connection closed")
    
    def clear(self) -> bool:
        """Clear all data."""
        try:
            tables = ['blocks', 'transactions', 'utxos', 'chain_state']
            for table in tables:
                self.cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
            return False