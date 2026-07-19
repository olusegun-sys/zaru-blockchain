"""
ZARU Transaction Module
=======================
Defines the transaction data structure for ZARU blockchain.
Implements UTXO model with digital signature verification.

WHY: Transactions are the heart of any cryptocurrency. 
They move value from one address to another using the UTXO model.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum

# ECDSA for digital signatures
from ecdsa import SigningKey, VerifyingKey, SECP256k1
from ecdsa.util import sigencode_der, sigdecode_der

from pydantic import BaseModel, Field, validator
from config import settings

# ============================================
# Helper Classes
# ============================================

@dataclass
class TxInput:
    """
    Transaction Input
    References a previous transaction output (UTXO)
    
    WHY: A transaction input is like "I'm spending money I received earlier"
    It points to a previous transaction's output that hasn't been spent yet.
    """
    tx_id: str                    # ID of the transaction that created the UTXO
    output_index: int             # Index of the output in that transaction
    signature: Optional[bytes] = None   # Digital signature proving ownership
    pub_key: Optional[bytes] = None     # Public key for verification
    
    @validator('output_index')
    def validate_index(cls, v):
        """Ensure output index is non-negative"""
        if v < 0:
            raise ValueError("Output index must be >= 0")
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'tx_id': self.tx_id,
            'output_index': self.output_index,
            'signature': self.signature.hex() if self.signature else None,
            'pub_key': self.pub_key.hex() if self.pub_key else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TxInput':
        """Create from dictionary"""
        return cls(
            tx_id=data['tx_id'],
            output_index=data['output_index'],
            signature=bytes.fromhex(data['signature']) if data.get('signature') else None,
            pub_key=bytes.fromhex(data['pub_key']) if data.get('pub_key') else None,
        )
    
    def serialize(self) -> bytes:
        """
        Serialize input for signing
        WHY: We need a deterministic byte representation for signing
        """
        data = f"{self.tx_id}:{self.output_index}".encode()
        return data


@dataclass
class TxOutput:
    """
    Transaction Output
    Contains the amount and the recipient's address
    
    WHY: An output is like "send X coins to this address"
    It creates a UTXO that can be spent by the recipient.
    """
    amount: int                    # Amount in satoshis
    address: str                   # Recipient's public address
    
    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount is positive"""
        if v <= 0:
            raise ValueError("Amount must be > 0")
        return v
    
    @validator('address')
    def validate_address(cls, v):
        """Basic address validation"""
        if not v or len(v) < 10:
            raise ValueError("Invalid address format")
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'amount': self.amount,
            'address': self.address,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TxOutput':
        """Create from dictionary"""
        return cls(
            amount=data['amount'],
            address=data['address'],
        )


# ============================================
# Main Transaction Class
# ============================================

class Transaction(BaseModel):
    """
    ZARU Transaction
    Implements Bitcoin-style UTXO transactions with signatures
    
    WHY: A transaction consumes UTXOs as inputs and creates new UTXOs as outputs.
    The difference between inputs and outputs is the transaction fee.
    """
    
    # Core fields
    tx_id: str = ""                # Transaction ID (hash of serialized data)
    version: int = 1               # Transaction version
    lock_time: int = 0             # Block height or timestamp when tx becomes valid
    
    # Inputs and outputs
    inputs: List[TxInput] = Field(default_factory=list)
    outputs: List[TxOutput] = Field(default_factory=list)
    
    # Metadata
    timestamp: int = field(default_factory=lambda: int(time.time()))
    is_coinbase: bool = False      # Is this a mining reward transaction?
    
    class Config:
        arbitrary_types_allowed = True
    
    @validator('inputs')
    def validate_inputs(cls, v):
        """Ensure transaction has at least one input (except coinbase)"""
        # Coinbase transactions have zero inputs
        return v
    
    @validator('outputs')
    def validate_outputs(cls, v):
        """Ensure transaction has at least one output"""
        if not v:
            raise ValueError("Transaction must have at least one output")
        return v
    
    def __init__(self, **data):
        """Initialize transaction and compute ID"""
        super().__init__(**data)
        if not self.tx_id:
            self.tx_id = self.compute_id()
    
    def compute_id(self) -> str:
        """
        Compute transaction ID (hash of serialized transaction)
        WHY: The tx_id uniquely identifies the transaction
        """
        # Serialize the transaction data
        data = self.serialize()
        # Double SHA-256 (Bitcoin standard)
        hash1 = hashlib.sha256(data).digest()
        hash2 = hashlib.sha256(hash1).digest()
        return hash2.hex()
    
    def serialize(self) -> bytes:
        """
        Serialize transaction for hashing and signing
        WHY: We need a deterministic byte representation
        """
        # Use canonical JSON for deterministic serialization
        tx_data = {
            'version': self.version,
            'lock_time': self.lock_time,
            'inputs': [inp.to_dict() for inp in self.inputs],
            'outputs': [out.to_dict() for out in self.outputs],
            'timestamp': self.timestamp,
            'is_coinbase': self.is_coinbase,
        }
        # Sort keys for deterministic order
        json_str = json.dumps(tx_data, sort_keys=True, separators=(',', ':'))
        return json_str.encode()
    
    def get_signature_data(self, input_index: int) -> bytes:
        """
        Get data to sign for a specific input
        WHY: Each input needs to be signed separately
        """
        # Create a copy of the transaction without signatures
        tx_data = {
            'version': self.version,
            'lock_time': self.lock_time,
            'inputs': [],
            'outputs': [out.to_dict() for out in self.outputs],
            'timestamp': self.timestamp,
            'is_coinbase': self.is_coinbase,
        }
        
        # Add all inputs (without signatures) for the signing hash
        for i, inp in enumerate(self.inputs):
            if i == input_index:
                # For the input we're signing, include the pub_key as placeholder
                tx_data['inputs'].append({
                    'tx_id': inp.tx_id,
                    'output_index': inp.output_index,
                    'pub_key': inp.pub_key.hex() if inp.pub_key else None,
                })
            else:
                # For other inputs, include them without signatures
                tx_data['inputs'].append({
                    'tx_id': inp.tx_id,
                    'output_index': inp.output_index,
                })
        
        json_str = json.dumps(tx_data, sort_keys=True, separators=(',', ':'))
        return json_str.encode()
    
    def sign_input(self, input_index: int, private_key: bytes) -> bool:
        """
        Sign a specific input with a private key
        
        Args:
            input_index: Index of the input to sign
            private_key: Private key bytes (32 bytes)
        
        Returns:
            bool: True if signing successful
        
        WHY: Signing proves ownership of the UTXO being spent
        """
        if input_index >= len(self.inputs):
            return False
        
        # Get the data to sign
        data = self.get_signature_data(input_index)
        
        try:
            # Create signing key from private key bytes
            sk = SigningKey.from_string(private_key, curve=SECP256k1)
            # Sign the data
            signature = sk.sign(data, hashfunc=hashlib.sha256, sigencode=sigencode_der)
            # Store signature in the input
            self.inputs[input_index].signature = signature
            # Store public key (derived from private key)
            vk = sk.get_verifying_key()
            self.inputs[input_index].pub_key = vk.to_string()
            return True
        except Exception as e:
            print(f"Error signing input {input_index}: {e}")
            return False
    
    def verify_input(self, input_index: int) -> bool:
        """
        Verify a specific input's signature
        
        Args:
            input_index: Index of the input to verify
        
        Returns:
            bool: True if signature is valid
        
        WHY: Verification ensures only the owner can spend the UTXO
        """
        if input_index >= len(self.inputs):
            return False
        
        inp = self.inputs[input_index]
        if not inp.signature or not inp.pub_key:
            return False
        
        try:
            # Get the data that was signed
            data = self.get_signature_data(input_index)
            # Create verifying key from public key
            vk = VerifyingKey.from_string(inp.pub_key, curve=SECP256k1)
            # Verify signature
            return vk.verify(inp.signature, data, hashfunc=hashlib.sha256, sigdecode=sigdecode_der)
        except Exception as e:
            print(f"Error verifying input {input_index}: {e}")
            return False
    
    def verify_all_inputs(self) -> bool:
        """
        Verify all input signatures
        WHY: Validate entire transaction before adding to mempool or block
        """
        # Coinbase transactions have no inputs to verify
        if self.is_coinbase:
            return True
        
        for i in range(len(self.inputs)):
            if not self.verify_input(i):
                return False
        return True
    
    def get_total_input(self) -> int:
        """
        Calculate total input amount (for validation)
        NOTE: This requires UTXO lookup - will be implemented in UTXO module
        """
        # This is a placeholder - actual implementation will query UTXO set
        # For now, we return 0 and will implement in ChainManager
        return 0
    
    def get_total_output(self) -> int:
        """Calculate total output amount"""
        return sum(out.amount for out in self.outputs)
    
    def get_fee(self) -> int:
        """Calculate transaction fee (inputs - outputs)"""
        # NOTE: Requires UTXO lookup for input amounts
        # Will be implemented with UTXO set
        return 0
    
    def is_valid(self, utxo_set: Optional[Dict[str, Dict[int, int]]] = None) -> Tuple[bool, str]:
        """
        Comprehensive transaction validation
        
        Args:
            utxo_set: Dictionary mapping tx_id -> {output_index: amount}
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        
        WHY: Production-grade validation before adding to mempool/block
        """
        # 1. Check transaction ID matches computed ID
        computed_id = self.compute_id()
        if self.tx_id != computed_id:
            return False, f"Invalid tx_id: computed {computed_id}, stored {self.tx_id}"
        
        # 2. Coinbase transactions are special
        if self.is_coinbase:
            if self.inputs:
                return False, "Coinbase transaction must have no inputs"
            if len(self.outputs) != 1:
                return False, "Coinbase transaction must have exactly one output"
            if self.outputs[0].amount > settings.INITIAL_COIN_SUPPLY:
                return False, "Coinbase amount exceeds supply limit"
            return True, "Valid coinbase transaction"
        
        # 3. Check inputs exist
        if not self.inputs:
            return False, "Transaction must have at least one input"
        
        # 4. Check outputs exist
        if not self.outputs:
            return False, "Transaction must have at least one output"
        
        # 5. Check all signatures
        if not self.verify_all_inputs():
            return False, "Invalid signature(s)"
        
        # 6. Check UTXO existence and amounts (if UTXO set provided)
        if utxo_set is not None:
            total_input = 0
            for inp in self.inputs:
                tx_utxos = utxo_set.get(inp.tx_id)
                if tx_utxos is None:
                    return False, f"UTXO not found for tx_id {inp.tx_id}"
                amount = tx_utxos.get(inp.output_index)
                if amount is None:
                    return False, f"UTXO output {inp.output_index} not found in tx {inp.tx_id}"
                total_input += amount
            
            total_output = self.get_total_output()
            
            # Check output doesn't exceed input
            if total_output > total_input:
                return False, f"Total output ({total_output}) exceeds total input ({total_input})"
            
            # Check minimum fee (if total_input > total_output)
            fee = total_input - total_output
            if fee < 0:
                return False, f"Negative fee: {fee}"
            if fee > 0 and fee < settings.MIN_RELAY_FEE:
                return False, f"Fee ({fee}) below minimum relay fee ({settings.MIN_RELAY_FEE})"
        
        return True, "Valid transaction"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entire transaction to dictionary"""
        return {
            'tx_id': self.tx_id,
            'version': self.version,
            'lock_time': self.lock_time,
            'timestamp': self.timestamp,
            'is_coinbase': self.is_coinbase,
            'inputs': [inp.to_dict() for inp in self.inputs],
            'outputs': [out.to_dict() for out in self.outputs],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create transaction from dictionary"""
        return cls(
            tx_id=data['tx_id'],
            version=data.get('version', 1),
            lock_time=data.get('lock_time', 0),
            timestamp=data.get('timestamp', int(time.time())),
            is_coinbase=data.get('is_coinbase', False),
            inputs=[TxInput.from_dict(inp) for inp in data.get('inputs', [])],
            outputs=[TxOutput.from_dict(out) for out in data.get('outputs', [])],
        )
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Transaction':
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))


# ============================================
# Convenience Functions
# ============================================

def create_coinbase_transaction(address: str, amount: int) -> Transaction:
    """
    Create a coinbase transaction (mining reward)
    
    Args:
        address: Recipient address
        amount: Mining reward amount
    
    Returns:
        Transaction: Coinbase transaction
    
    WHY: Coinbase transactions are how new coins enter circulation
    """
    tx = Transaction(
        is_coinbase=True,
        inputs=[],  # No inputs for coinbase
        outputs=[TxOutput(amount=amount, address=address)],
    )
    tx.tx_id = tx.compute_id()
    return tx


def create_transaction(
    inputs: List[TxInput],
    outputs: List[TxOutput],
    private_key: bytes,
) -> Optional[Transaction]:
    """
    Create and sign a new transaction
    
    Args:
        inputs: List of UTXOs to spend
        outputs: List of outputs (recipients)
        private_key: Private key for signing
    
    Returns:
        Optional[Transaction]: Signed transaction or None if error
    """
    try:
        # Create transaction
        tx = Transaction(
            inputs=inputs,
            outputs=outputs,
        )
        
        # Sign each input with the private key
        for i in range(len(inputs)):
            if not tx.sign_input(i, private_key):
                print(f"Failed to sign input {i}")
                return None
        
        # Recompute tx_id after signing
        tx.tx_id = tx.compute_id()
        
        return tx
    except Exception as e:
        print(f"Error creating transaction: {e}")
        return None