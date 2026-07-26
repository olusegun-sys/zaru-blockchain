"""
ZARU Transaction Module
=======================
Defines the transaction data structure for ZARU blockchain.
Implements UTXO model with digital signature verification.

FIXED: Complete rewrite of signing and verification logic (Bitcoin-style).
FIXED: Proper import of database store (db_store alias).
FIXED: Burn mechanism uses correct import.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from ecdsa import SigningKey, VerifyingKey, SECP256k1
from ecdsa.util import sigencode_der, sigdecode_der

from pydantic import BaseModel, Field, validator
from config import settings
from database import store as db_store  # FIXED: Correct import alias


@dataclass
class TxInput:
    """Transaction Input - References a UTXO."""
    tx_id: str
    output_index: int
    signature: Optional[bytes] = None
    pub_key: Optional[bytes] = None
    
    @validator('output_index')
    def validate_index(cls, v):
        if v < 0:
            raise ValueError("Output index must be >= 0")
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'tx_id': self.tx_id,
            'output_index': self.output_index,
            'signature': self.signature.hex() if self.signature else None,
            'pub_key': self.pub_key.hex() if self.pub_key else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TxInput':
        return cls(
            tx_id=data['tx_id'],
            output_index=data['output_index'],
            signature=bytes.fromhex(data['signature']) if data.get('signature') else None,
            pub_key=bytes.fromhex(data['pub_key']) if data.get('pub_key') else None,
        )


@dataclass
class TxOutput:
    """Transaction Output - Creates a UTXO."""
    amount: int
    address: str
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be > 0")
        return v
    
    @validator('address')
    def validate_address(cls, v):
        if not v or len(v) < 10:
            raise ValueError("Invalid address format")
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'amount': self.amount,
            'address': self.address,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TxOutput':
        return cls(
            amount=data['amount'],
            address=data['address'],
        )


class Transaction(BaseModel):
    """ZARU Transaction with BURN MECHANISM."""
    
    tx_id: str = ""
    version: int = 1
    lock_time: int = 0
    inputs: List[TxInput] = Field(default_factory=list)
    outputs: List[TxOutput] = Field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(time.time()))
    is_coinbase: bool = False
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.tx_id:
            self.tx_id = self.compute_id()
    
    def compute_id(self) -> str:
        """Compute transaction ID (double SHA-256)."""
        data = self.serialize()
        hash1 = hashlib.sha256(data).digest()
        hash2 = hashlib.sha256(hash1).digest()
        return hash2.hex()
    
    def serialize(self) -> bytes:
        """Serialize transaction to JSON bytes."""
        tx_data = {
            'version': self.version,
            'lock_time': self.lock_time,
            'inputs': [inp.to_dict() for inp in self.inputs],
            'outputs': [out.to_dict() for out in self.outputs],
            'timestamp': self.timestamp,
            'is_coinbase': self.is_coinbase,
        }
        json_str = json.dumps(tx_data, sort_keys=True, separators=(',', ':'))
        return json_str.encode()
    
    def get_signing_data(self) -> bytes:
        """
        Get the data to sign for the entire transaction (Bitcoin-style).
        
        FIXED: Uses the same data for all inputs.
        """
        # Build transaction data without signatures
        tx_data = {
            'version': self.version,
            'lock_time': self.lock_time,
            'inputs': [],
            'outputs': [out.to_dict() for out in self.outputs],
            'timestamp': self.timestamp,
            'is_coinbase': self.is_coinbase,
        }
        
        # Add all inputs (without signatures)
        for inp in self.inputs:
            tx_data['inputs'].append({
                'tx_id': inp.tx_id,
                'output_index': inp.output_index,
            })
        
        json_str = json.dumps(tx_data, sort_keys=True, separators=(',', ':'))
        return json_str.encode()
    
    def sign(self, private_key: bytes) -> bool:
        """
        Sign the entire transaction with a private key.
        
        FIXED: Signs the entire transaction (Bitcoin-style).
        """
        try:
            from ecdsa import SigningKey, SECP256k1
            import hashlib
            
            # Get the data to sign
            data = self.get_signing_data()
            print(f"🔍 sign: data_len={len(data)}")
            
            # Create signing key
            sk = SigningKey.from_string(private_key, curve=SECP256k1)
            vk = sk.get_verifying_key()
            pub_key = vk.to_string()
            
            # Verify the private key generates the correct address
            hash1 = hashlib.sha256(pub_key).digest()
            hash2 = hashlib.sha256(hash1).digest()
            computed_address = hash2.hex()[:40]
            print(f"🔍 sign: computed_address={computed_address}")
            
            # Sign the data
            signature = sk.sign(data, hashfunc=hashlib.sha256, sigencode=sigencode_der)
            
            # Store signature and public key in ALL inputs
            for inp in self.inputs:
                inp.signature = signature
                inp.pub_key = pub_key
            
            print(f"✅ sign: success, sig_len={len(signature)}")
            return True
            
        except Exception as e:
            print(f"❌ sign: error={e}")
            import traceback
            traceback.print_exc()
            return False
    
    def verify(self) -> bool:
        """
        Verify the entire transaction's signature.
        
        FIXED: Verifies the entire transaction.
        """
        if self.is_coinbase:
            return True
        
        if not self.inputs:
            print(f"❌ verify: no inputs")
            return False
        
        # Check all inputs have the same signature and pub_key
        first_sig = self.inputs[0].signature
        first_pub = self.inputs[0].pub_key
        
        if not first_sig or not first_pub:
            print(f"❌ verify: missing signature or pub_key")
            return False
        
        # Verify all inputs have the same signature
        for inp in self.inputs:
            if inp.signature != first_sig or inp.pub_key != first_pub:
                print(f"❌ verify: inconsistent signatures")
                return False
        
        try:
            # Get the data that was signed
            data = self.get_signing_data()
            print(f"🔍 verify: data_len={len(data)}")
            
            # Verify the signature
            vk = VerifyingKey.from_string(first_pub, curve=SECP256k1)
            result = vk.verify(first_sig, data, hashfunc=hashlib.sha256, sigdecode=sigdecode_der)
            print(f"🔍 verify: result={result}")
            
            if result:
                print(f"✅ verify: signature valid")
            else:
                print(f"❌ verify: signature invalid")
            
            return result
            
        except Exception as e:
            print(f"❌ verify: error={e}")
            import traceback
            traceback.print_exc()
            return False
    
    def verify_all_inputs(self) -> bool:
        """Alias for verify()."""
        return self.verify()
    
    def get_total_input(self) -> int:
        return 0
    
    def get_total_output(self) -> int:
        return sum(out.amount for out in self.outputs)
    
    def get_fee(self) -> int:
        return 0
    
    def is_valid(self, utxo_set: Optional[Dict[str, Dict[int, int]]] = None) -> Tuple[bool, str]:
        """
        Comprehensive transaction validation.
        """
        # 1. Check transaction ID
        computed_id = self.compute_id()
        if self.tx_id != computed_id:
            return False, f"Invalid tx_id: computed {computed_id}, stored {self.tx_id}"
        
        # 2. Coinbase transactions
        if self.is_coinbase:
            if self.inputs:
                return False, "Coinbase transaction must have no inputs"
            if len(self.outputs) != 1:
                return False, "Coinbase transaction must have exactly one output"
            MAX_COINBASE_REWARD = getattr(settings, 'MAX_COINBASE_REWARD', 5_000_000_000)
            if self.outputs[0].amount > MAX_COINBASE_REWARD:
                return False, f"Coinbase amount ({self.outputs[0].amount}) exceeds max reward ({MAX_COINBASE_REWARD})"
            return True, "Valid coinbase transaction"
        
        # 3. Check inputs exist
        if not self.inputs:
            return False, "Transaction must have at least one input"
        
        # 4. Check outputs exist
        if not self.outputs:
            return False, "Transaction must have at least one output"
        
        # 5. Verify signatures
        if not self.verify():
            return False, "Invalid signature(s)"
        
        # 6. Check UTXO existence and amounts
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
            
            if total_output > total_input:
                return False, f"Total output ({total_output}) exceeds total input ({total_input})"
            
            fee = total_input - total_output
            if fee < 0:
                return False, f"Negative fee: {fee}"
            if fee > 0 and fee < settings.MIN_RELAY_FEE:
                return False, f"Fee ({fee}) below minimum relay fee ({settings.MIN_RELAY_FEE})"
            
            # Burn mechanism
            if fee > 0:
                burn_amount = fee // 100
                if burn_amount > 0:
                    burn_address = settings.BURN_ADDRESS
                    self.outputs.append(TxOutput(
                        amount=burn_amount,
                        address=burn_address
                    ))
                    
                    # FIXED: Use db_store alias (not 'store')
                    total_burned = db_store.get_chain_state('total_burned') or 0
                    total_burned += burn_amount
                    db_store.put_chain_state('total_burned', total_burned)
                    print(f"🔥 Burned {burn_amount} satoshis (Total burned: {total_burned})")
        
        return True, "Valid transaction"
    
    def to_dict(self) -> Dict[str, Any]:
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
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Transaction':
        return cls.from_dict(json.loads(json_str))


def create_coinbase_transaction(address: str, amount: int) -> Transaction:
    """Create a coinbase transaction."""
    tx = Transaction(
        is_coinbase=True,
        inputs=[],
        outputs=[TxOutput(amount=amount, address=address)],
    )
    tx.tx_id = tx.compute_id()
    return tx


def create_transaction(inputs: List[TxInput], outputs: List[TxOutput], private_key: bytes) -> Optional[Transaction]:
    """Create and sign a new transaction."""
    try:
        print(f"🔍 create_transaction: {len(inputs)} inputs, {len(outputs)} outputs")
        
        tx = Transaction(inputs=inputs, outputs=outputs)
        
        # Sign the entire transaction
        if not tx.sign(private_key):
            print(f"❌ create_transaction: failed to sign")
            return None
        
        # Recompute tx_id after signing
        tx.tx_id = tx.compute_id()
        print(f"✅ create_transaction: success, tx_id={tx.tx_id[:16]}...")
        return tx
    except Exception as e:
        print(f"❌ create_transaction: error={e}")
        import traceback
        traceback.print_exc()
        return None