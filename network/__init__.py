"""
ZARU Network Package
====================
Peer-to-peer networking for block and transaction propagation.

WHY: The network layer allows nodes to communicate.
It propagates transactions, blocks, and maintains the network state.
"""

from .protocol import Message, MessageType, serialize_message, deserialize_message
from .peer import Peer, PeerStatus
from .node import Node, node

__all__ = [
    'Message',
    'MessageType',
    'serialize_message',
    'deserialize_message',
    'Peer',
    'PeerStatus',
    'Node',
    'node',
]