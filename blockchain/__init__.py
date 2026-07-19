"""
ZARU Blockchain Package
=======================
Core blockchain data structures and logic.

WHY: This package contains the heart of ZARU - the blockchain.
It handles transactions, blocks, UTXO management, and chain validation.
"""

from .transaction import Transaction, TxInput, TxOutput
from .block import Block, BlockHeader, create_genesis_block
from .utxo import UTXOSet, get_balance_for_address, get_utxos_for_address, utxo_set
from .chain_manager import ChainManager, chain_manager

__all__ = [
    'Transaction',
    'TxInput',
    'TxOutput',
    'Block',
    'BlockHeader',
    'create_genesis_block',
    'UTXOSet',
    'get_balance_for_address',
    'get_utxos_for_address',
    'utxo_set',
    'ChainManager',
    'chain_manager',
]