"""
ZARU Transaction Module
=======================
Defines the transaction data structure for ZARU blockchain.
Implements UTXO model with digital signature verification.

BURN MECHANISM: Every transaction burns 1% of fees to create scarcity.
FIXED: Added debug logging to sign_input for troubleshooting.
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


@dataclass
class TxInput:
    """
    Transaction Input
    References a previous transaction output (UTXO)
    """
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
    
    def serialize(self) -> bytes:
        return f"{self.tx_id}:{self.output_index}".encode()


@dataclass
class TxOutput:
    """
    Transaction Output
    Contains the amount and the recipient's address
    """
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
    """
    ZARU Transaction with BURN MECHANISM.
    """
    
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
        data = self.serialize()
        hash1 = hashlib.sha256(data).digest()
        hash2 = hashlib.sha256(hash1).digest()
        return hash2.hex()
    
    def serialize(self) -> bytes:
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
    
    def get_signature_data(self, input_index: int) -> bytes:
        tx_data = {
            'version': self.version,
            'lock_time': self.lock_time,
            'inputs': [],
            'outputs': [out.to_dict() for out in self.outputs],
            'timestamp': self.timestamp,
            'is_coinbase': self.is_coinbase,
        }
        
        for i, inp in enumerate(self.inputs):
            if i == input_index:
                tx_data['inputs'].append({
                    'tx_id': inp.tx_id,
                    'output_index': inp.output_index,
                    'pub_key': inp.pub_key.hex() if inp.pub_key else None,
                })
            else:
                tx_data['inputs'].append({
                    'tx_id': inp.tx_id,
                    'output_index': inp.output_index,
                })
        
        json_str = json.dumps(tx_data, sort_keys=True, separators=(',', ':'))
        return json_str.encode()
    
    def sign_input(self, input_index: int, private_key: bytes) -> bool:
        """
        Sign a specific input with a private key.
        
        FIXED: Added debug logging to troubleshoot signature issues.
        """
        if input_index >= len(self.inputs):
            return False
        
        data = self.get_signature_data(input_index)
        
        try:
            sk = SigningKey.from_string(private_key, curve=SECP256k1)
            vk = sk.get_verifying_key()
            pub_key = vk.to_string()
            
            # DEBUG: Verify the private key generates the correct address
            import hashlib
            hash1 = hashlib.sha256(pub_key).digest()
            hash2 = hashlib.sha256(hash1).digest()
            computed_address = hash2.hex()[:40]
            
            print(f"🔍 Signing input {input_index}")
            print(f"   Data length: {len(data)} bytes")
            print(f"   Computed address: {computed_address}")
            
            # Sign the data
            signature = sk.sign(data, hashfunc=hashlib.sha256, sigencode=sigencode_der)
            
            # Store signature and public key
            self.inputs[input_index].signature = signature
            self.inputs[input_index].pub_key = pub_key
            
            print(f"✅ Signature created successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error signing input {input_index}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def verify_input(self, input_index: int) -> bool:
        if input_index >= len(self.inputs):
            return False
        
        inp = self.inputs[input_index]
        if not inp.signature or not inp.pub_key:
            return False
        
        try:
            data = self.get_signature_data(input_index)
            vk = VerifyingKey.from_string(inp.pub_key, curve=SECP256k1)
            return vk.verify(inp.signature, data, hashfunc=hashlib.sha256, sigdecode=sigdecode_der)
        except Exception as e:
            print(f"Error verifying input {input_index}: {e}")
            return False
    
    def verify_all_inputs(self) -> bool:
        if self.is_coinbase:
            return True
        
        for i in range(len(self.inputs)):
            if not self.verify_input(i):
                return False
        return True
    
    def get_total_input(self) -> int:
        return 0
    
    def get_total_output(self) -> int:
        return sum(out.amount for out in self.outputs)
    
    def get_fee(self) -> int:
        return 0
    
    def is_valid(self, utxo_set: Optional[Dict[str, Dict[int, int]]] = None) -> Tuple[bool, str]:
        """
        Comprehensive transaction validation with BURN MECHANISM.
        
        FIXED: Coinbase validation uses MAX_COINBASE_REWARD from settings.
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
            # FIXED: Check against MAX_COINBASE_REWARD, not total supply
            MAX_COINBASE_REWARD = getattr(settings, 'MAX_COINBASE_REWARD', 5_000_000_000)
            if self.outputs[0].amount > MAX_COINBASE_REWARD:
                return False, f"Coinbase amount ({self.outputs[0].amount}) exceeds max reward ({MAX_COINBASE_REWARD})"
            print(f"✅ Coinbase validated: {self.outputs[0].amount} satoshis to {self.outputs[0].address[:10]}...")
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
            
            # ============================================
            # 🔥 BURN MECHANISM 🔥
            # ============================================
            if fee > 0:
                burn_amount = fee // 100  # 1% burn
                if burn_amount > 0:
                    burn_address = settings.BURN_ADDRESS
                    self.outputs.append(TxOutput(
                        amount=burn_amount,
                        address=burn_address
                    ))
                    
                    from database import store
                    total_burned = store.get_chain_state('total_burned') or 0
                    total_burned += burn_amount
                    store.put_chain_state('total_burned', total_burned)
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
    """Create a coinbase transaction (mining reward)"""
    tx = Transaction(
        is_coinbase=True,
        inputs=[],
        outputs=[TxOutput(amount=amount, address=address)],
    )
    tx.tx_id = tx.compute_id()
    return tx


def create_transaction(inputs: List[TxInput], outputs: List[TxOutput], private_key: bytes) -> Optional[Transaction]:
    """Create and sign a new transaction"""
    try:
        tx = Transaction(inputs=inputs, outputs=outputs)
        
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
        import traceback
        traceback.print_exc()
        return None