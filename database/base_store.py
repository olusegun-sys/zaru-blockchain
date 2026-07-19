"""
Base Store Abstract Class
=========================
Defines the contract that ALL database backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any


class BaseStore(ABC):
    """Abstract interface for ZARU database storage."""
    
    # Block storage
    @abstractmethod
    def put_block(self, block_hash: str, block_data: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    def get_block(self, block_hash: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def get_block_by_height(self, height: int) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def get_chain_height(self) -> int:
        pass
    
    # UTXO storage
    @abstractmethod
    def put_utxo(self, tx_id: str, output_index: int, amount: int, address: str, block_height: int) -> bool:
        pass
    
    @abstractmethod
    def get_utxo(self, tx_id: str, output_index: int) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def spend_utxo(self, tx_id: str, output_index: int) -> bool:
        pass
    
    @abstractmethod
    def get_utxos_for_address(self, address: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def get_utxo_count(self) -> int:
        pass
    
    # Chain state
    @abstractmethod
    def put_chain_state(self, key: str, value: Any) -> bool:
        pass
    
    @abstractmethod
    def get_chain_state(self, key: str) -> Optional[Any]:
        pass
    
    # Transaction storage
    @abstractmethod
    def put_transaction(self, tx_id: str, tx_data: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    # Maintenance
    @abstractmethod
    def close(self) -> None:
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        pass