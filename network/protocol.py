"""
ZARU Network Protocol Module
============================
Defines the message format and protocol for P2P communication.

WHY: All nodes need to speak the same language to communicate.
This module defines that language - the message format and types.

HOW IT WORKS:
1. Messages are serialized to JSON for transmission
2. Each message has a type and payload
3. Nodes listen for messages and respond accordingly
"""

import json
import time
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, field  # ✅ FIXED: Added 'field' import


class MessageType(Enum):
    """
    Types of messages exchanged between nodes.
    
    WHY: Different message types require different handling.
    """
    # Handshake messages
    VERSION = "version"          # Initial handshake
    VERACK = "verack"            # Acknowledge version
    GET_ADDR = "getaddr"         # Request peer addresses
    ADDR = "addr"                # Send peer addresses
    
    # Transaction messages
    TX = "tx"                    # Transaction broadcast
    GET_TX = "gettx"             # Request specific transaction
    
    # Block messages
    BLOCK = "block"              # Block broadcast
    GET_BLOCK = "getblock"       # Request specific block
    GET_HEADERS = "getheaders"   # Request block headers
    HEADERS = "headers"          # Send block headers
    
    # Chain messages
    GET_BLOCKS = "getblocks"     # Request blocks for sync
    INV = "inv"                  # Inventory (list of objects)
    GET_DATA = "getdata"         # Request data for inventory items
    
    # Status messages
    PING = "ping"                # Check if peer is alive
    PONG = "pong"                # Response to ping
    REJECT = "reject"            # Reject a message
    NOT_FOUND = "notfound"       # Requested object not found


@dataclass
class Message:
    """
    Network message structure.
    
    WHY: All messages follow this structure for consistent parsing.
    """
    type: MessageType            # Message type
    payload: Dict[str, Any]      # Message data
    timestamp: float = field(default_factory=time.time)  # When message was sent
    magic: str = "ZARU"          # Magic bytes for identification
    
    def to_json(self) -> str:
        """Serialize message to JSON."""
        return json.dumps({
            'magic': self.magic,
            'type': self.type.value,
            'timestamp': self.timestamp,
            'payload': self.payload
        })
    
    @classmethod
    def from_json(cls, data: str) -> 'Message':
        """Deserialize message from JSON."""
        obj = json.loads(data)
        return cls(
            magic=obj['magic'],
            type=MessageType(obj['type']),
            timestamp=obj['timestamp'],
            payload=obj['payload']
        )


def serialize_message(message: Message) -> str:
    """Alias for Message.to_json()."""
    return message.to_json()


def deserialize_message(data: str) -> Message:
    """Alias for Message.from_json()."""
    return Message.from_json(data)


# ============================================
# MESSAGE PAYLOAD HELPERS
# ============================================

def create_version_message(
    version: int,
    height: int,
    user_agent: str,
    addr_from: str,
    addr_to: str,
    nonce: int
) -> Message:
    """Create a VERSION handshake message."""
    return Message(
        type=MessageType.VERSION,
        payload={
            'version': version,
            'height': height,
            'user_agent': user_agent,
            'addr_from': addr_from,
            'addr_to': addr_to,
            'nonce': nonce,
        }
    )


def create_verack_message() -> Message:
    """Create a VERACK handshake message."""
    return Message(
        type=MessageType.VERACK,
        payload={}
    )


def create_ping_message(nonce: int) -> Message:
    """Create a PING message."""
    return Message(
        type=MessageType.PING,
        payload={'nonce': nonce}
    )


def create_pong_message(nonce: int) -> Message:
    """Create a PONG message."""
    return Message(
        type=MessageType.PONG,
        payload={'nonce': nonce}
    )


def create_tx_message(tx_data: Dict[str, Any]) -> Message:
    """Create a TX (transaction) message."""
    return Message(
        type=MessageType.TX,
        payload={'transaction': tx_data}
    )


def create_block_message(block_data: Dict[str, Any]) -> Message:
    """Create a BLOCK message."""
    return Message(
        type=MessageType.BLOCK,
        payload={'block': block_data}
    )


def create_get_block_message(block_hash: str) -> Message:
    """Create a GET_BLOCK request message."""
    return Message(
        type=MessageType.GET_BLOCK,
        payload={'block_hash': block_hash}
    )


def create_get_headers_message(
    start_height: int,
    count: int = 2000
) -> Message:
    """Create a GET_HEADERS request message."""
    return Message(
        type=MessageType.GET_HEADERS,
        payload={
            'start_height': start_height,
            'count': count
        }
    )


def create_headers_message(headers: list) -> Message:
    """Create a HEADERS response message."""
    return Message(
        type=MessageType.HEADERS,
        payload={'headers': headers}
    )


def create_get_blocks_message(
    start_height: int,
    count: int = 500
) -> Message:
    """Create a GET_BLOCKS request message."""
    return Message(
        type=MessageType.GET_BLOCKS,
        payload={
            'start_height': start_height,
            'count': count
        }
    )


def create_inv_message(objects: list) -> Message:
    """Create an INV (inventory) message."""
    return Message(
        type=MessageType.INV,
        payload={'objects': objects}
    )


def create_get_data_message(requests: list) -> Message:
    """Create a GET_DATA request message."""
    return Message(
        type=MessageType.GET_DATA,
        payload={'requests': requests}
    )


def create_addr_message(addresses: list) -> Message:
    """Create an ADDR (addresses) message."""
    return Message(
        type=MessageType.ADDR,
        payload={'addresses': addresses}
    )


def create_get_addr_message() -> Message:
    """Create a GET_ADDR message."""
    return Message(
        type=MessageType.GET_ADDR,
        payload={}
    )


def create_reject_message(
    message_type: str,
    reason: str,
    code: int = 1
) -> Message:
    """Create a REJECT message."""
    return Message(
        type=MessageType.REJECT,
        payload={
            'message_type': message_type,
            'reason': reason,
            'code': code
        }
    )


# ============================================
# TEST FUNCTIONS
# ============================================

def test_protocol():
    """Test the protocol module."""
    print("\n🧪 Testing Protocol...")
    
    # Create a message
    msg = create_version_message(
        version=1,
        height=0,
        user_agent="ZARU-test",
        addr_from="127.0.0.1:8333",
        addr_to="127.0.0.1:8334",
        nonce=12345
    )
    print(f"1. Created message: {msg.type.value}")
    
    # Serialize
    serialized = serialize_message(msg)
    print(f"2. Serialized: {serialized[:50]}...")
    
    # Deserialize
    deserialized = deserialize_message(serialized)
    print(f"3. Deserialized: {deserialized.type.value}")
    
    # Check equality
    assert msg.type == deserialized.type
    assert msg.payload == deserialized.payload
    print("4. Serialization/deserialization works!")
    
    print("\n✅ Protocol test complete")
    return True


if __name__ == "__main__":
    test_protocol()