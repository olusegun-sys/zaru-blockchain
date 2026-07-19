"""
PostgreSQL Store Implementation
===============================
Production database backend using PostgreSQL.
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
        self.conn = psycopg2.connect(self.db_url)
        self.cur = self.conn.cursor()
    
    def _create_tables(self):
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
            self.cur.execute(
                "INSERT INTO blocks (block_hash, block_height, block_data) VALUES (%s, %s, %s) ON CONFLICT (block_hash) DO UPDATE SET block_data = EXCLUDED.block_data",
                (block_hash, block_data['header']['block_height'], Json(block_data))
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing block: {e}")
            return False
    
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        try:
            self.cur.execute("SELECT block_data FROM blocks WHERE block_hash = %s", (block_hash,))
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving block: {e}")
            return None
    
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        try:
            self.cur.execute("SELECT block_data FROM blocks WHERE block_height = %s", (height,))
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving block: {e}")
            return None
    
    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        try:
            self.cur.execute("SELECT block_data FROM blocks ORDER BY block_height DESC LIMIT 1")
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving latest block: {e}")
            return None
    
    def get_chain_height(self) -> int:
        try:
            self.cur.execute("SELECT COUNT(*) FROM blocks")
            return self.cur.fetchone()[0]
        except Exception as e:
            print(f"❌ Error getting chain height: {e}")
            return 0
    
    def put_utxo(self, tx_id: str, output_index: int, amount: int, address: str, block_height: int) -> bool:
        try:
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
            return True
        except Exception as e:
            print(f"❌ Error storing UTXO: {e}")
            return False
    
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        try:
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
            self.cur.execute("UPDATE utxos SET is_spent = TRUE, spent_at = CURRENT_TIMESTAMP WHERE tx_id = %s AND output_index = %s", (tx_id, output_index))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error spending UTXO: {e}")
            return False
    
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        try:
            self.cur.execute("SELECT tx_id, output_index, amount, block_height FROM utxos WHERE address = %s AND is_spent = FALSE", (address,))
            rows = self.cur.fetchall()
            return [{'tx_id': r[0], 'output_index': r[1], 'amount': r[2], 'block_height': r[3]} for r in rows]
        except Exception as e:
            print(f"❌ Error getting UTXOs: {e}")
            return []
    
    def get_utxo_count(self) -> int:
        try:
            self.cur.execute("SELECT COUNT(*) FROM utxos WHERE is_spent = FALSE")
            return self.cur.fetchone()[0]
        except Exception as e:
            print(f"❌ Error getting UTXO count: {e}")
            return 0
    
    def put_chain_state(self, key: str, value: Any) -> bool:
        try:
            self.cur.execute("INSERT INTO chain_state (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, Json(value)))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing chain state: {e}")
            return False
    
    def get_chain_state(self, key: str) -> Optional[Any]:
        try:
            self.cur.execute("SELECT value FROM chain_state WHERE key = %s", (key,))
            row = self.cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            print(f"❌ Error retrieving chain state: {e}")
            return None
    
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        try:
            self.cur.execute("INSERT INTO transactions (tx_id, block_hash, tx_data) VALUES (%s, %s, %s) ON CONFLICT (tx_id) DO UPDATE SET tx_data = EXCLUDED.tx_data", (tx_id, tx_data.get('block_hash', 'unknown'), Json(tx_data)))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error storing transaction: {e}")
            return False
    
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        try:
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
            return False
