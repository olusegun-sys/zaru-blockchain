"""
ZARU Block Module
=================
Defines the block structure for ZARU blockchain.
Implements proof of work with difficulty adjustment.

WHY: Blocks are the containers that hold transactions and link them 
together in a chain using cryptographic hashes.

FIXED: Robust prev_block_hash validation handling quoted strings.
"""

import hashlib
import json
import time
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from pydantic import BaseModel, Field, validator

from blockchain.transaction import Transaction, TxInput, TxOutput
from config import settings


# ============================================
# Block Header
# ============================================

class BlockHeader(BaseModel):
    """
    Block Header
    Contains metadata about the block (not the transactions)
    
    WHY: The header is what gets hashed for proof of work.
    It's small and fixed-size, making PoW efficient.
    """
    
    version: int = 1                                    # Block version
    prev_block_hash: str = ""                           # Previous block's hash
    merkle_root: str = ""                               # Root hash of all transactions
    timestamp: int = field(default_factory=lambda: int(time.time()))  # Block creation time
    difficulty_target: int = settings.INITIAL_DIFFICULTY  # Target for PoW
    nonce: int = 0                                      # Proof of work counter
    block_height: int = 0                               # Position in blockchain
    
    @validator('prev_block_hash')
    def validate_prev_hash(cls, v):
        """
        Validate previous block hash format.
        
        FIXED: Handles quoted strings, extra characters, and extracts hash.
        """
        if not v:
            return ""
        
        # Clean the string
        if isinstance(v, str):
            # Strip quotes first
            v = v.strip('"').strip()
            
            # If it's still not 64 chars, try harder
            if len(v) != 64:
                # Try to find a 64-character hex string within
                match = re.search(r'[a-fA-F0-9]{64}', v)
                if match:
                    return match.group(0)
                
                # If it has extra characters, try to clean
                v = ''.join(c for c in v if c in '0123456789abcdefABCDEF')
                if len(v) == 64:
                    return v
                
                raise ValueError(f"Invalid previous block hash: '{v}' (length: {len(v)})")
            
            return v
        
        return str(v)
    
    @validator('difficulty_target')
    def validate_difficulty(cls, v):
        """Ensure difficulty target is positive."""
        if v <= 0:
            raise ValueError("Difficulty target must be positive")
        return v
    
    @validator('block_height')
    def validate_height(cls, v):
        """Ensure block height is non-negative."""
        if v < 0:
            raise ValueError("Block height must be non-negative")
        return int(v)
    
    def compute_hash(self) -> str:
        """
        Compute the block header hash (for PoW)
        
        WHY: Double SHA-256 is Bitcoin's standard - it's proven secure.
        The hash must be below the difficulty target for the block to be valid.
        """
        # Serialize header data deterministically
        header_data = {
            'version': self.version,
            'prev_block_hash': self.prev_block_hash,
            'merkle_root': self.merkle_root,
            'timestamp': self.timestamp,
            'difficulty_target': self.difficulty_target,
            'nonce': self.nonce,
            'block_height': self.block_height,
        }
        
        # Sort keys for deterministic JSON
        json_str = json.dumps(header_data, sort_keys=True, separators=(',', ':'))
        data_bytes = json_str.encode()
        
        # Double SHA-256 (Bitcoin standard)
        hash1 = hashlib.sha256(data_bytes).digest()
        hash2 = hashlib.sha256(hash1).digest()
        return hash2.hex()
    
    def is_valid_pow(self) -> bool:
        """
        Check if block hash meets difficulty target
        
        WHY: The hash must be less than the target for the block to be valid.
        Lower target = harder to find valid block.
        """
        block_hash = self.compute_hash()
        # Convert to integer for comparison
        hash_int = int(block_hash, 16)
        return hash_int < self.difficulty_target
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert header to dictionary"""
        return {
            'version': self.version,
            'prev_block_hash': self.prev_block_hash,
            'merkle_root': self.merkle_root,
            'timestamp': self.timestamp,
            'difficulty_target': self.difficulty_target,
            'nonce': self.nonce,
            'block_height': self.block_height,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BlockHeader':
        """Create header from dictionary"""
        # Clean prev_block_hash if present
        prev_hash = data.get('prev_block_hash', '')
        if isinstance(prev_hash, str):
            prev_hash = prev_hash.strip('"').strip()
            # Try to extract 64-char hash if needed
            if len(prev_hash) != 64:
                match = re.search(r'[a-fA-F0-9]{64}', prev_hash)
                if match:
                    prev_hash = match.group(0)
        
        return cls(
            version=data.get('version', 1),
            prev_block_hash=prev_hash,
            merkle_root=data.get('merkle_root', ''),
            timestamp=data.get('timestamp', int(time.time())),
            difficulty_target=data.get('difficulty_target', settings.INITIAL_DIFFICULTY),
            nonce=data.get('nonce', 0),
            block_height=int(data.get('block_height', 0)),
        )


# ============================================
# Main Block Class
# ============================================

class Block(BaseModel):
    """
    ZARU Block
    Contains transactions and links to previous block
    
    WHY: A block is like a page in a ledger. Each block references
    the previous one, creating an immutable chain.
    """
    
    # Block header
    header: BlockHeader = Field(default_factory=BlockHeader)
    
    # Transactions (the actual data)
    transactions: List[Transaction] = Field(default_factory=list)
    
    # Metadata
    hash: str = ""                  # Computed block hash (cached)
    size: int = 0                   # Block size in bytes
    transaction_count: int = 0      # Number of transactions
    
    class Config:
        arbitrary_types_allowed = True
    
    @validator('transactions')
    def validate_transactions(cls, v):
        """Validate transaction list"""
        if v is None:
            return []
        return v
    
    def __init__(self, **data):
        """Initialize block and compute hash"""
        super().__init__(**data)
        # Ensure header exists
        if 'header' not in data or data.get('header') is None:
            self.header = BlockHeader()
        
        # Compute merkle root if transactions exist
        if self.transactions:
            self.header.merkle_root = self.compute_merkle_root()
        
        # Compute block hash if not set
        if not self.hash:
            self.hash = self.compute_hash()
            self.size = self.compute_size()
            self.transaction_count = len(self.transactions)
    
    def compute_merkle_root(self) -> str:
        """
        Compute Merkle root of all transactions
        
        WHY: The Merkle root provides a compact way to verify 
        all transactions are included in the block. It's the "hash of hashes."
        
        A Merkle tree works like a tournament bracket:
        - Hash each transaction
        - Pair them up and hash the pairs
        - Continue until you get one final hash (the root)
        """
        if not self.transactions:
            return hashlib.sha256(b'').hexdigest()
        
        # Get transaction hashes
        tx_hashes = []
        for tx in self.transactions:
            # Use transaction ID
            tx_hash = bytes.fromhex(tx.tx_id)
            tx_hashes.append(tx_hash)
        
        # Build Merkle tree (level by level)
        while len(tx_hashes) > 1:
            # If odd number, duplicate the last one
            if len(tx_hashes) % 2 == 1:
                tx_hashes.append(tx_hashes[-1])
            
            # Hash pairs
            new_level = []
            for i in range(0, len(tx_hashes), 2):
                # Concatenate pair and hash
                combined = tx_hashes[i] + tx_hashes[i+1]
                hash1 = hashlib.sha256(combined).digest()
                hash2 = hashlib.sha256(hash1).digest()  # Double SHA-256
                new_level.append(hash2)
            
            tx_hashes = new_level
        
        # Return the root (as hex string)
        return tx_hashes[0].hex()
    
    def compute_hash(self) -> str:
        """Compute block hash from header"""
        return self.header.compute_hash()
    
    def compute_size(self) -> int:
        """Compute block size in bytes"""
        # Serialize block to JSON and count bytes
        json_str = json.dumps(self.to_dict(), separators=(',', ':'))
        return len(json_str.encode())
    
    def mine_block(self, target: Optional[int] = None) -> bool:
        """
        Mine the block (find a valid nonce)
        
        Args:
            target: Optional custom difficulty target
        
        Returns:
            bool: True if block mined successfully
        
        WHY: Mining is the "work" in proof of work.
        We try different nonce values until we find one that produces
        a hash below the difficulty target.
        """
        if target is None:
            target = self.header.difficulty_target
        
        print(f"⛏️  Mining block {self.header.block_height}...")
        print(f"   Target: {target}")
        
        # Start mining
        start_time = time.time()
        attempts = 0
        
        while True:
            # Try current nonce
            self.header.nonce = attempts
            block_hash = self.compute_hash()
            
            # Check if hash meets target
            hash_int = int(block_hash, 16)
            if hash_int < target:
                # Found a valid nonce!
                self.hash = block_hash
                elapsed = time.time() - start_time
                print(f"✅ Block mined in {elapsed:.2f}s after {attempts:,} attempts")
                print(f"   Nonce: {attempts}")
                print(f"   Block hash: {block_hash}")
                
                # Update size and transaction count
                self.size = self.compute_size()
                self.transaction_count = len(self.transactions)
                return True
            
            attempts += 1
            
            # Safety check - prevent infinite mining
            if attempts > 10_000_000:  # 10 million attempts
                print("⚠️  Mining stopped: too many attempts")
                return False
    
    def verify_block(self, previous_block_hash: str) -> Tuple[bool, str]:
        """
        Verify the entire block is valid
        
        Args:
            previous_block_hash: Hash of the previous block
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        
        WHY: Comprehensive validation before adding to chain
        """
        # 1. Check header is valid
        if not self.header.is_valid_pow():
            return False, "Block does not meet difficulty target"
        
        # 2. Check previous block hash matches
        if self.header.prev_block_hash != previous_block_hash:
            return False, f"Previous block hash mismatch: expected {previous_block_hash}, got {self.header.prev_block_hash}"
        
        # 3. Verify merkle root
        computed_root = self.compute_merkle_root()
        if computed_root != self.header.merkle_root:
            return False, f"Merkle root mismatch: computed {computed_root}, stored {self.header.merkle_root}"
        
        # 4. Check block size limit
        if self.size > settings.MAX_BLOCK_SIZE_BYTES:
            return False, f"Block size {self.size} exceeds limit {settings.MAX_BLOCK_SIZE_BYTES}"
        
        # 5. Verify all transactions
        for i, tx in enumerate(self.transactions):
            is_valid, error = tx.is_valid()
            if not is_valid:
                return False, f"Transaction {i} invalid: {error}"
        
        # 6. Check coinbase transaction is first (if it exists)
        coinbase_found = False
        for i, tx in enumerate(self.transactions):
            if tx.is_coinbase:
                if i != 0:
                    return False, "Coinbase transaction must be first in block"
                coinbase_found = True
                break
        
        # 7. Verify total output of coinbase (if present)
        if coinbase_found:
            coinbase = self.transactions[0]
            if coinbase.outputs[0].amount > settings.INITIAL_COIN_SUPPLY:
                return False, "Coinbase reward exceeds supply limit"
        
        # 8. Check timestamp is reasonable (not too far in future/past)
        now = int(time.time())
        if self.header.timestamp > now + 7200:  # 2 hours in future
            return False, f"Block timestamp {self.header.timestamp} is too far in future"
        if self.header.timestamp < now - 7200:  # 2 hours in past
            return False, f"Block timestamp {self.header.timestamp} is too far in past"
        
        return True, "Block is valid"
    
    def add_transaction(self, transaction: Transaction) -> bool:
        """
        Add a transaction to the block
        
        Args:
            transaction: Transaction to add
        
        Returns:
            bool: True if added successfully
        
        WHY: Add transactions one by one, updating the block metadata.
        """
        # Validate transaction
        is_valid, error = transaction.is_valid()
        if not is_valid:
            print(f"❌ Cannot add transaction: {error}")
            return False
        
        # Coinbase transactions are special
        if transaction.is_coinbase:
            # Check we don't already have a coinbase
            for tx in self.transactions:
                if tx.is_coinbase:
                    print("❌ Block already has a coinbase transaction")
                    return False
        
        # Add transaction
        self.transactions.append(transaction)
        
        # Update merkle root
        self.header.merkle_root = self.compute_merkle_root()
        
        # Update block size
        self.size = self.compute_size()
        self.transaction_count = len(self.transactions)
        
        # Update block hash (will change because merkle root changed)
        self.hash = self.compute_hash()
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entire block to dictionary"""
        return {
            'header': self.header.to_dict(),
            'transactions': [tx.to_dict() for tx in self.transactions],
            'hash': self.hash,
            'size': self.size,
            'transaction_count': self.transaction_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Block':
        """Create block from dictionary"""
        # Create header
        header = BlockHeader.from_dict(data.get('header', {}))
        
        # Create transactions
        transactions = []
        for tx_data in data.get('transactions', []):
            tx = Transaction.from_dict(tx_data)
            transactions.append(tx)
        
        # Create block
        block = cls(
            header=header,
            transactions=transactions,
        )
        block.hash = data.get('hash', block.compute_hash())
        block.size = data.get('size', block.compute_size())
        block.transaction_count = data.get('transaction_count', len(transactions))
        
        return block
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Block':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    def __str__(self) -> str:
        """Human-readable representation"""
        return f"Block #{self.header.block_height} | Hash: {self.hash[:10]}... | Tx: {len(self.transactions)} | Size: {self.size} bytes"


# ============================================
# Genesis Block Generator
# ============================================

def create_genesis_block() -> Block:
    """
    Create the genesis block (first block in the blockchain)
    
    WHY: The genesis block is hardcoded and marks the start of the chain.
    It contains the initial coin distribution.
    """
    # Create coinbase transaction for genesis
    # This creates the initial coins
    coinbase = Transaction(
        is_coinbase=True,
        inputs=[],  # No inputs for coinbase
        outputs=[
            TxOutput(
                amount=settings.INITIAL_COIN_SUPPLY,
                address="ZARU_GENESIS_ADDRESS_00000000000000000000000000000000"
            )
        ],
        timestamp=1231006505,  # Bitcoin's genesis timestamp (for nostalgia)
    )
    coinbase.tx_id = coinbase.compute_id()
    
    # Create block header
    header = BlockHeader(
        version=1,
        prev_block_hash="0" * 64,  # Zero hash - no previous block
        timestamp=1231006505,
        difficulty_target=settings.INITIAL_DIFFICULTY,
        nonce=0,
        block_height=0,
    )
    
    # Create block
    block = Block(
        header=header,
        transactions=[coinbase],
    )
    
    # Compute merkle root
    block.header.merkle_root = block.compute_merkle_root()
    
    # Mine the genesis block (with lower difficulty for speed)
    # Note: In production, genesis block should be pre-mined
    block.mine_block()
    
    return block


# ============================================
# Block Validation Utilities
# ============================================

def calculate_difficulty(last_block: Block, previous_block: Block) -> int:
    """
    Calculate new difficulty based on previous blocks
    
    WHY: Difficulty adjusts to ensure blocks are found approximately 
    every 10 minutes, regardless of network hash rate.
    
    The algorithm:
    1. Check if we've mined enough blocks for adjustment
    2. Compare actual time to target time
    3. Adjust difficulty up or down
    """
    # Only adjust every DIFFICULTY_ADJUSTMENT_INTERVAL blocks
    if last_block.header.block_height % settings.DIFFICULTY_ADJUSTMENT_INTERVAL != 0:
        return last_block.header.difficulty_target
    
    # Calculate time taken for the adjustment period
    time_taken = last_block.header.timestamp - previous_block.header.timestamp
    
    # Target time for the period
    target_time = settings.DIFFICULTY_ADJUSTMENT_INTERVAL * settings.BLOCK_TIME_SECONDS
    
    # Prevent extreme difficulty changes (4x max adjustment)
    if time_taken > target_time * 4:
        time_taken = target_time * 4
    elif time_taken < target_time // 4:
        time_taken = target_time // 4
    
    # Calculate new difficulty
    new_difficulty = int(last_block.header.difficulty_target * (time_taken / target_time))
    
    # Ensure difficulty stays within reasonable bounds
    if new_difficulty < 1:
        new_difficulty = 1
    if new_difficulty > settings.MAX_TARGET:
        new_difficulty = settings.MAX_TARGET
    
    return new_difficulty