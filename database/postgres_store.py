"""
PostgreSQL Store Implementation
===============================
Production database backend using PostgreSQL.
FIXED: get_chain_state returns clean string without JSON formatting.
FIXED: Proper transaction handling with rollback on error.
"""

import os
import json
from typing import Optional, Dict, List, Any

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:
    psycopg2 = None

from .base_store import BaseStore


class PostgresStore(BaseStore):
    """PostgreSQL implementation of BaseStore."""
    
    def __init__(self):
        """Initialize PostgreSQL connection."""
        if psycopg2 is None:
            raise ImportError("psycopg2 not installed")
        
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL not set")
        
        self.conn = None
        self.cur = None
        self._connect()
        self._create_tables()
        print("✅ PostgreSQL store initialized")
    
    def _connect(self):
        """Connect to PostgreSQL."""
        try:
            if self.conn:
                self.conn.close()
            self.conn = psycopg2.connect(self.db_url)
            self.conn.autocommit = False
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"❌ PostgreSQL connection failed: {e}")
            raise
    
    def _ensure_connection(self):
        """Ensure connection is valid and not in aborted state."""
        try:
            self.cur.execute("SELECT 1")
        except psycopg2.ProgrammingError as e:
            if "current transaction is aborted" in str(e):
                print("⚠️  Transaction aborted, rolling back...")
                self.conn.rollback()
            elif "connection already closed" in str(e):
                print("⚠️  Connection closed, reconnecting...")
                self._connect()
            else:
                raise
        except Exception as e:
            print(f"⚠️  Connection error: {e}, reconnecting...")
            self._connect()
    
    def _create_tables(self):
        """Create tables if they don't exist."""
        # Blocks
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_hash TEXT PRIMARY KEY,
                block_height INTEGER UNIQUE NOT NULL,
                block_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.cur.execute("CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(block_height)")
        
        # UTXOs
        self.cur.execute("""
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
        self.cur.execute("CREATE INDEX IF NOT EXISTS idx_utxos_address ON utxos(address)")
        self.cur.execute("CREATE INDEX IF NOT EXISTS idx_utxos_is_spent ON utxos(is_spent)")
        
        # Chain state
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS chain_state (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    def put_block(self, block_hash: str, block_data: Dict[str, Any]) -> bool:
        try:
            self._ensure_connection()
            self.cur.execute(
                "INSERT INTO blocks (block_hash, block_height, block_data) VALUES (%s, %s, %s) ON CONFLICT (block_hash) DO UPDATE SET block_data = EXCLUDED.block_data",
                (block_hash, block_data['header']['block_height'], Json(block_data))
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing block: {e}")
            self.conn.rollback()
            return False
    
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT block_data FROM blocks WHERE block_hash = %s", (block_hash,))
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving block: {e}")
            return None
    
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT block_data FROM blocks WHERE block_height = %s", (height,))
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving block: {e}")
            return None
    
    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT block_data FROM blocks ORDER BY block_height DESC LIMIT 1")
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving latest block: {e}")
            return None
    
    def get_chain_height(self) -> int:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT COUNT(*) FROM blocks")
            return self.cur.fetchone()[0]
        except Exception as e:
            print(f"❌ Error getting chain height: {e}")
            return 0
    
    def put_utxo(self, tx_id: str, output_index: int, amount: int, address: str, block_height: int) -> bool:
        """Store a UTXO with proper transaction handling."""
        try:
            self._ensure_connection()
            
            self.cur.execute("""
                INSERT INTO utxos (tx_id, output_index, amount, address, block_height, is_spent)
                VALUES (%s, %s, %s, %s, %s, FALSE)
                ON CONFLICT (tx_id, output_index) DO UPDATE SET 
                    amount = EXCLUDED.amount,
                    address = EXCLUDED.address,
                    block_height = EXCLUDED.block_height,
                    is_spent = FALSE,
                    spent_at = NULL
            """, (tx_id, output_index, amount, address, block_height))
            
            self.conn.commit()
            print(f"✅ UTXO stored: {tx_id[:16]}...:{output_index} = {amount} satoshis to {address[:10]}...")
            return True
            
        except Exception as e:
            print(f"❌ Error storing UTXO {tx_id}:{output_index}: {e}")
            self.conn.rollback()
            return False
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT tx_id, output_index, amount, address, block_height, is_spent FROM utxos WHERE tx_id = %s AND output_index = %s", (tx_id, output_index))
            row = self.cur.fetchone()
            if row:
                return {'tx_id': row[0], 'output_index': row[1], 'amount': row[2], 'address': row[3], 'block_height': row[4], 'is_spent': row[5]}
            return None
        except Exception as e:
            print(f"❌ Error retrieving UTXO: {e}")
            return None
    
    def spend_utxo(self, tx_id: str, output_index: int) -> bool:
        try:
            self._ensure_connection()
            self.cur.execute("UPDATE utxos SET is_spent = TRUE, spent_at = CURRENT_TIMESTAMP WHERE tx_id = %s AND output_index = %s", (tx_id, output_index))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error spending UTXO: {e}")
            self.conn.rollback()
            return False
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT tx_id, output_index, amount, block_height FROM utxos WHERE address = %s AND is_spent = FALSE ORDER BY block_height ASC", (address,))
            rows = self.cur.fetchall()
            return [{'tx_id': r[0], 'output_index': r[1], 'amount': r[2], 'block_height': r[3]} for r in rows]
        except Exception as e:
            print(f"❌ Error getting UTXOs: {e}")
            return []
    
    def get_utxo_count(self) -> int:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT COUNT(*) FROM utxos WHERE is_spent = FALSE")
            return self.cur.fetchone()[0]
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
            self._ensure_connection()
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
            
            self.cur.execute(
                "INSERT INTO chain_state (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP",
                (key, Json(value_json))
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing chain state '{key}': {e}")
            self.conn.rollback()
            return False
    
    def get_chain_state(self, key: str) -> Optional[str]:
        """
        Retrieve chain metadata.
        
        FIXED: Returns clean string without JSON formatting/quoting.
        """
        try:
            self._ensure_connection()
            self.cur.execute("SELECT value FROM chain_state WHERE key = %s", (key,))
            row = self.cur.fetchone()
            if row:
                value = row[0]
                
                # Handle JSONB value (could be dict, list, or string)
                if isinstance(value, dict):
                    # If it's a dict with a single string value, extract it
                    if len(value) == 1:
                        for v in value.values():
                            if isinstance(v, str):
                                # Check if it's a quoted string
                                if v.startswith('"') and v.endswith('"'):
                                    return v[1:-1]
                                return v
                    # Otherwise return as JSON string
                    return json.dumps(value)
                elif isinstance(value, list):
                    return json.dumps(value)
                elif isinstance(value, str):
                    # If it's a JSON string with quotes, strip them
                    if value.startswith('"') and value.endswith('"'):
                        return value[1:-1]
                    return value
                else:
                    return str(value)
            return None
        except Exception as e:
            print(f"❌ Error retrieving chain state '{key}': {e}")
            return None
    
    def delete_chain_state(self, key: str) -> bool:
        """Delete a value from the chain_state table."""
        try:
            self._ensure_connection()
            self.cur.execute("DELETE FROM chain_state WHERE key = %s", (key,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error deleting chain state '{key}': {e}")
            self.conn.rollback()
            return False
    
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        try:
            self._ensure_connection()
            self.cur.execute("INSERT INTO transactions (tx_id, block_hash, tx_data) VALUES (%s, %s, %s) ON CONFLICT (tx_id) DO UPDATE SET tx_data = EXCLUDED.tx_data", (tx_id, tx_data.get('block_hash', 'unknown'), Json(tx_data)))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing transaction: {e}")
            self.conn.rollback()
            return False
    
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_connection()
            self.cur.execute("SELECT tx_data FROM transactions WHERE tx_id = %s", (tx_id,))
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving transaction: {e}")
            return None
    
    def close(self):
        if self.conn:
            self.conn.close()
    
    def clear(self):
        try:
            tables = ['blocks', 'transactions', 'utxos', 'chain_state']
            for table in tables:
                self.cur.execute(f"TRUNCATE TABLE {table} CASCADE")
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error clearing database: {e}")
            self.conn.rollback()
            return False