"""
Base Store Abstract Class
=========================
Defines the contract that ALL database backends must implement.
WHY: This ensures we can swap SQLite and RocksDB without changing
the rest of the codebase. It's like having a standard power outlet
that works with any appliance.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path


class BaseStore(ABC):
    """
    Abstract interface for ZARU database storage.
    
    All database backends (SQLite, RocksDB) must implement these methods.
    This ensures the blockchain code works with any storage backend.
    """
    
    # ============================================
    # BLOCK STORAGE
    # ============================================
    
    @abstractmethod
    def put_block(self, block_hash: str, block_data: Dict[str, Any]) -> bool:
        """
        Store a block by its hash
        
        Args:
            block_hash: SHA-256 hash of the block (64 hex chars)
            block_data: Complete block data as dictionary
        
        Returns:
            bool: True if stored successfully
        
        WHY: We store blocks by their hash for fast retrieval.
        Hash is the unique identifier for each block.
        """
        pass
    
    @abstractmethod
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a block by hash
        
        Args:
            block_hash: SHA-256 hash of the block
        
        Returns:
            Optional[Dict]: Block data or None if not found
        
        WHY: Used for chain validation, fork resolution,
        and block propagation across the network.
        """
        pass
    
    @abstractmethod
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a block by its height in the chain
        
        Args:
            height: Block number (0 = genesis)
        
        Returns:
            Optional[Dict]: Block data or None if not found
        
        WHY: We need to access blocks by height for chain traversal.
        """
        pass
    
    @abstractmethod
    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent block in the chain
        
        Returns:
            Optional[Dict]: Latest block or None if chain is empty
        
        WHY: The chain tip is needed for mining and validation.
        """
        pass
    
    @abstractmethod
    def get_chain_height(self) -> int:
        """
        Get the current chain height (number of blocks)
        
        Returns:
            int: Chain height (0 = empty chain)
        
        WHY: Used for difficulty adjustment and chain stats.
        """
        pass
    
    # ============================================
    # UTXO STORAGE (Unspent Transaction Outputs)
    # ============================================
    
    @abstractmethod
    def put_utxo(
        self, 
        tx_id: str, 
        output_index: int, 
        amount: int, 
        address: str,
        block_height: int
    ) -> bool:
        """
        Store a UTXO (unspent transaction output)
        
        Args:
            tx_id: Transaction ID that created this output
            output_index: Index of the output in the transaction
            amount: Value in satoshis
            address: Recipient's public address
            block_height: Block where this UTXO was created
        
        Returns:
            bool: True if stored successfully
        
        WHY: UTXOs are the "coins" in our system.
        Each UTXO represents spendable coins at a specific address.
        """
        pass
    
    @abstractmethod
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a UTXO
        
        Args:
            tx_id: Transaction ID
            output_index: Output index in the transaction
        
        Returns:
            Optional[Dict]: UTXO data or None if not found
        
        WHY: Used to verify that a transaction input references
        a valid, unspent output.
        """
        pass
    
    @abstractmethod
    def spend_utxo(self, tx_id: str, output_index: int) -> bool:
        """
        Mark a UTXO as spent
        
        Args:
            tx_id: Transaction ID
            output_index: Output index in the transaction
        
        Returns:
            bool: True if marked as spent successfully
        
        WHY: When a transaction spends a UTXO, we mark it as spent
        so it can't be used again (prevents double-spending).
        """
        pass
    
    @abstractmethod
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        """
        Get all UTXOs belonging to an address
        
        Args:
            address: Public address
        
        Returns:
            List[Dict]: List of UTXOs (each with tx_id, output_index, amount)
        
        WHY: For wallet balance calculation and transaction creation.
        We need to know what coins a user can spend.
        """
        pass
    
    @abstractmethod
    def get_utxo_count(self) -> int:
        """
        Get total number of UTXOs in the system
        
        Returns:
            int: Number of UTXOs
        
        WHY: Used for statistics and monitoring.
        """
        pass
    
    # ============================================
    # CHAIN STATE
    # ============================================
    
    @abstractmethod
    def put_chain_state(self, key: str, value: Any) -> bool:
        """
        Store chain metadata
        
        Args:
            key: Metadata key (e.g., 'chain_tip', 'difficulty')
            value: Metadata value (can be string, int, dict)
        
        Returns:
            bool: True if stored successfully
        
        WHY: We need to store mutable chain state:
        - Current chain tip hash
        - Current difficulty
        - Last reorg time
        """
        pass
    
    @abstractmethod
    def get_chain_state(self, key: str) -> Optional[Any]:
        """
        Retrieve chain metadata
        
        Args:
            key: Metadata key
        
        Returns:
            Optional[Any]: Metadata value or None if not found
        
        WHY: Retrieve the chain state when the node restarts.
        """
        pass
    
    # ============================================
    # TRANSACTION STORAGE
    # ============================================
    
    @abstractmethod
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        """
        Store a transaction (for indexing)
        
        Args:
            tx_id: Transaction ID
            tx_data: Complete transaction data
        
        Returns:
            bool: True if stored successfully
        
        WHY: To quickly look up transaction history
        without scanning all blocks.
        """
        pass
    
    @abstractmethod
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a transaction by ID
        
        Args:
            tx_id: Transaction ID
        
        Returns:
            Optional[Dict]: Transaction data or None if not found
        
        WHY: Used for wallet history and block explorer.
        """
        pass
    
    # ============================================
    # MAINTENANCE
    # ============================================
    
    @abstractmethod
    def close(self) -> None:
        """Close database connection and clean up resources"""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """
        Clear all data (for testing)
        
        Returns:
            bool: True if cleared successfully
        
        WHY: Used in test environments to reset state.
        """
        pass