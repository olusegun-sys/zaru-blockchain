"""
ZARU Node Module
================
Main node class that manages P2P networking.

WHY: The node is the "face" of the network layer.
It handles peer connections, message routing, and network synchronization.

HOW IT WORKS:
1. Node starts and listens for incoming connections
2. Peers connect and perform handshake
3. Messages are routed to the appropriate handlers
4. Blocks and transactions are propagated
5. Node syncs with peers on startup
"""

import socket
import threading
import time
import random
from typing import Optional, List, Dict, Any, Set, Callable
from pathlib import Path

from config import settings
from network.protocol import (
    Message, MessageType,
    create_version_message, create_verack_message,
    create_ping_message, create_get_blocks_message,
    create_get_headers_message, create_tx_message,
    create_block_message, create_addr_message,
    create_get_addr_message, create_inv_message,
    create_get_data_message
)
from network.peer import Peer, PeerStatus


class Node:
    """
    Main node for P2P networking.
    
    Manages:
    - Listening for incoming connections
    - Peer connections
    - Message propagation
    - Chain synchronization
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        on_block: Optional[Callable] = None,
        on_tx: Optional[Callable] = None,
        on_peer: Optional[Callable] = None
    ):
        """
        Initialize the node.
        
        Args:
            host: Host to bind to (from config if None)
            port: Port to bind to (from config if None)
            on_block: Callback for incoming blocks
            on_tx: Callback for incoming transactions
            on_peer: Callback for peer events
        """
        self.host = host if host else settings.NODE_HOST
        self.port = port if port else settings.NODE_PORT
        self.on_block = on_block
        self.on_tx = on_tx
        self.on_peer = on_peer
        
        # Node identification
        self.nonce = random.randint(0, 2**32 - 1)
        self.user_agent = f"ZARU-node/{time.time():.0f}"
        self.version = 1
        
        # Peers
        self.peers: Dict[str, Peer] = {}
        self.bootstrap_peers: List[str] = settings.BOOTSTRAP_NODES
        self.max_peers = settings.MAX_PEERS
        
        # Server
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.server_thread: Optional[threading.Thread] = None
        
        # Chain state (will be set by chain manager)
        self.chain_height = 0
        self.chain_tip = ""
        
        # Stats
        self.total_messages_received = 0
        self.total_messages_sent = 0
        
        print(f"✅ Node initialized: {self.host}:{self.port}")
        print(f"   User Agent: {self.user_agent}")
    
    # ============================================
    # SERVER MANAGEMENT
    # ============================================
    
    def start(self) -> None:
        """Start the node server."""
        if self.running:
            print("⚠️  Node already running")
            return
        
        try:
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(128)
            self.server_socket.settimeout(1)
            
            self.running = True
            
            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            
            print(f"🚀 Node listening on {self.host}:{self.port}")
            
            # Connect to bootstrap peers
            self._connect_bootstrap_peers()
            
        except Exception as e:
            print(f"❌ Failed to start node: {e}")
    
    def stop(self) -> None:
        """Stop the node server."""
        self.running = False
        
        # Disconnect all peers
        for peer in list(self.peers.values()):
            peer.disconnect()
        self.peers.clear()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        print("🛑 Node stopped")
    
    def _server_loop(self) -> None:
        """Main server loop for accepting connections."""
        while self.running:
            try:
                # Accept connection
                client_socket, addr = self.server_socket.accept()
                
                # Check if we have room
                if len(self.peers) >= self.max_peers:
                    client_socket.close()
                    continue
                
                # Create peer
                address = addr[0]
                port = addr[1]
                peer = Peer(
                    address=address,
                    port=port,
                    on_message=self._handle_message,
                    on_disconnect=self._handle_disconnect
                )
                
                # Set socket
                peer.socket = client_socket
                peer.status = PeerStatus.CONNECTED
                peer.info.connected_at = time.time()
                peer.running = True
                
                # Start receive thread
                peer.receive_thread = threading.Thread(
                    target=peer._receive_loop,
                    daemon=True
                )
                peer.receive_thread.start()
                
                # Add to peers
                self.peers[peer_key(address, port)] = peer
                
                print(f"📥 Incoming connection from {address}:{port}")
                
                # Send handshake
                self._send_handshake(peer)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"❌ Server error: {e}")
    
    # ============================================
    # PEER CONNECTION
    # ============================================
    
    def connect_to_peer(self, address: str, port: int) -> Optional[Peer]:
        """
        Connect to a peer.
        
        Args:
            address: Peer address
            port: Peer port
        
        Returns:
            Optional[Peer]: Connected peer or None
        """
        # Check if already connected
        key = peer_key(address, port)
        if key in self.peers:
            return self.peers[key]
        
        # Check max peers
        if len(self.peers) >= self.max_peers:
            return None
        
        # Create peer
        peer = Peer(
            address=address,
            port=port,
            on_message=self._handle_message,
            on_disconnect=self._handle_disconnect
        )
        
        # Connect
        if not peer.connect():
            return None
        
        # Add to peers
        self.peers[key] = peer
        
        # Send handshake
        self._send_handshake(peer)
        
        return peer
    
    def _connect_bootstrap_peers(self) -> None:
        """Connect to bootstrap peers."""
        for addr in self.bootstrap_peers:
            try:
                address, port = addr.split(":")
                port = int(port)
                
                # Don't connect to self
                if address == self.host and port == self.port:
                    continue
                
                print(f"🔗 Connecting to bootstrap peer: {address}:{port}")
                self.connect_to_peer(address, port)
                
                # Small delay between connections
                time.sleep(0.5)
                
            except Exception as e:
                print(f"⚠️  Failed to connect to bootstrap peer {addr}: {e}")
    
    def _send_handshake(self, peer: Peer) -> bool:
        """
        Send handshake to a peer.
        
        Args:
            peer: Peer to send handshake to
        
        Returns:
            bool: True if handshake sent
        """
        # Get chain height
        height = self.chain_height
        
        # Send version
        version_msg = create_version_message(
            version=self.version,
            height=height,
            user_agent=self.user_agent,
            addr_from=f"{self.host}:{self.port}",
            addr_to=f"{peer.address}:{peer.port}",
            nonce=self.nonce
        )
        
        if peer.send_message(version_msg):
            peer.status = PeerStatus.HANDSHAKE_SENT
            return True
        
        return False
    
    def _handle_disconnect(self, peer: Peer) -> None:
        """
        Handle peer disconnection.
        
        Args:
            peer: Disconnected peer
        """
        key = peer_key(peer.address, peer.port)
        if key in self.peers:
            del self.peers[key]
            print(f"📤 Peer disconnected: {peer.address}:{peer.port}")
    
    # ============================================
    # MESSAGE HANDLING
    # ============================================
    
    def _handle_message(self, peer: Peer, message: Message) -> None:
        """
        Handle incoming message from a peer.
        
        Args:
            peer: Peer that sent the message
            message: Incoming message
        """
        self.total_messages_received += 1
        
        # Update peer info
        peer.info.last_seen = time.time()
        
        # Route message by type
        handlers = {
            MessageType.VERSION: self._handle_version,
            MessageType.VERACK: self._handle_verack,
            MessageType.PING: self._handle_ping,
            MessageType.PONG: self._handle_pong,
            MessageType.TX: self._handle_tx,
            MessageType.BLOCK: self._handle_block,
            MessageType.GET_BLOCK: self._handle_get_block,
            MessageType.GET_BLOCKS: self._handle_get_blocks,
            MessageType.GET_HEADERS: self._handle_get_headers,
            MessageType.GET_ADDR: self._handle_get_addr,
            MessageType.ADDR: self._handle_addr,
            MessageType.INV: self._handle_inv,
            MessageType.GET_DATA: self._handle_get_data,
            MessageType.REJECT: self._handle_reject,
        }
        
        handler = handlers.get(message.type)
        if handler:
            handler(peer, message)
        else:
            print(f"⚠️  Unknown message type: {message.type} from {peer}")
    
    def _handle_version(self, peer: Peer, msg: Message) -> None:
        """Handle VERSION message."""
        # Update peer info
        peer.info.version = msg.payload.get('version', 0)
        peer.info.user_agent = msg.payload.get('user_agent', '')
        peer.info.height = msg.payload.get('height', 0)
        
        # Send verack
        verack = create_verack_message()
        peer.send_message(verack)
        
        # If we initiated the connection, we already sent version
        # If they initiated, we need to send our version
        if peer.status == PeerStatus.CONNECTED:
            self._send_handshake(peer)
        
        peer.status = PeerStatus.READY
        
        print(f"✅ Handshake complete with {peer.address}:{peer.port}")
        print(f"   Version: {peer.info.version}, Height: {peer.info.height}")
        
        # Check if peer is ahead of us
        if peer.info.height > self.chain_height:
            print(f"📥 Peer is ahead ({peer.info.height} > {self.chain_height})")
            self._sync_with_peer(peer)
    
    def _handle_verack(self, peer: Peer, msg: Message) -> None:
        """Handle VERACK message."""
        if peer.status == PeerStatus.HANDSHAKE_SENT:
            peer.status = PeerStatus.READY
            print(f"✅ Handshake complete with {peer.address}:{peer.port}")
            
            # Check if peer is ahead of us
            if peer.info.height > self.chain_height:
                self._sync_with_peer(peer)
    
    def _handle_ping(self, peer: Peer, msg: Message) -> None:
        """Handle PING message."""
        from network.protocol import create_pong_message
        pong = create_pong_message(msg.payload.get('nonce', 0))
        peer.send_message(pong)
    
    def _handle_pong(self, peer: Peer, msg: Message) -> None:
        """Handle PONG message."""
        peer.info.last_pong = time.time()
    
    def _handle_tx(self, peer: Peer, msg: Message) -> None:
        """Handle TX (transaction) message."""
        tx_data = msg.payload.get('transaction')
        if tx_data and self.on_tx:
            self.on_tx(tx_data)
            print(f"📨 Received transaction from {peer.address}:{peer.port}")
            self._broadcast_message(msg, exclude=peer)
    
    def _handle_block(self, peer: Peer, msg: Message) -> None:
        """Handle BLOCK message."""
        block_data = msg.payload.get('block')
        if block_data and self.on_block:
            self.on_block(block_data)
            print(f"📦 Received block from {peer.address}:{peer.port}")
            self._broadcast_message(msg, exclude=peer)
    
    def _handle_get_block(self, peer: Peer, msg: Message) -> None:
        """Handle GET_BLOCK message."""
        block_hash = msg.payload.get('block_hash')
        # TODO: Fetch block from database and send
        pass
    
    def _handle_get_blocks(self, peer: Peer, msg: Message) -> None:
        """Handle GET_BLOCKS message."""
        start_height = msg.payload.get('start_height', 0)
        count = msg.payload.get('count', 500)
        # TODO: Send blocks from start_height to start_height + count
        pass
    
    def _handle_get_headers(self, peer: Peer, msg: Message) -> None:
        """Handle GET_HEADERS message."""
        start_height = msg.payload.get('start_height', 0)
        count = msg.payload.get('count', 2000)
        # TODO: Send headers
        pass
    
    def _handle_get_addr(self, peer: Peer, msg: Message) -> None:
        """Handle GET_ADDR message."""
        # Send known addresses
        addresses = []
        for p in list(self.peers.values())[:100]:
            addresses.append({
                'address': p.address,
                'port': p.port,
                'timestamp': int(p.info.connected_at)
            })
        
        addr_msg = create_addr_message(addresses)
        peer.send_message(addr_msg)
    
    def _handle_addr(self, peer: Peer, msg: Message) -> None:
        """Handle ADDR message."""
        addresses = msg.payload.get('addresses', [])
        
        for addr_info in addresses:
            address = addr_info.get('address')
            port = addr_info.get('port')
            
            if address and port:
                # Don't connect to self
                if address == self.host and port == self.port:
                    continue
                
                # Connect to new peer
                self.connect_to_peer(address, port)
    
    def _handle_inv(self, peer: Peer, msg: Message) -> None:
        """Handle INV (inventory) message."""
        objects = msg.payload.get('objects', [])
        
        # Request unknown objects
        requests = []
        for obj in objects:
            # TODO: Check if we have this object
            if obj.get('type') == 'block':
                # Don't request blocks we already have
                pass
            elif obj.get('type') == 'tx':
                # Don't request transactions we already have
                pass
        
        if requests:
            get_data = create_get_data_message(requests)
            peer.send_message(get_data)
    
    def _handle_get_data(self, peer: Peer, msg: Message) -> None:
        """Handle GET_DATA message."""
        requests = msg.payload.get('requests', [])
        
        for req in requests:
            obj_type = req.get('type')
            obj_hash = req.get('hash')
            
            if obj_type == 'block':
                # TODO: Send block
                pass
            elif obj_type == 'tx':
                # TODO: Send transaction
                pass
    
    def _handle_reject(self, peer: Peer, msg: Message) -> None:
        """Handle REJECT message."""
        reason = msg.payload.get('reason', 'Unknown')
        message_type = msg.payload.get('message_type', 'Unknown')
        print(f"⚠️  Rejected by {peer.address}: {message_type} - {reason}")
    
    # ============================================
    # CHAIN SYNCHRONIZATION
    # ============================================
    
    def _sync_with_peer(self, peer: Peer) -> None:
        """
        Synchronize chain with a peer.
        
        Args:
            peer: Peer to sync with
        """
        print(f"🔄 Syncing with {peer.address}:{peer.port}")
        
        # Send get_blocks
        get_blocks = create_get_blocks_message(
            start_height=self.chain_height,
            count=500
        )
        peer.send_message(get_blocks)
    
    def update_chain_state(self, height: int, tip_hash: str) -> None:
        """
        Update chain state for the node.
        
        Args:
            height: Current chain height
            tip_hash: Current chain tip hash
        """
        self.chain_height = height
        self.chain_tip = tip_hash
    
    # ============================================
    # MESSAGE BROADCASTING
    # ============================================
    
    def broadcast_message(self, message: Message) -> int:
        """
        Broadcast a message to all connected peers.
        
        Args:
            message: Message to broadcast
        
        Returns:
            int: Number of peers sent to
        """
        return self._broadcast_message(message, exclude=None)
    
    def _broadcast_message(self, message: Message, exclude: Optional[Peer] = None) -> int:
        """
        Broadcast a message to all connected peers except one.
        
        Args:
            message: Message to broadcast
            exclude: Peer to exclude
        
        Returns:
            int: Number of peers sent to
        """
        sent = 0
        for peer in list(self.peers.values()):
            if peer == exclude:
                continue
            
            if peer.send_message(message):
                sent += 1
                self.total_messages_sent += 1
        
        return sent
    
    def broadcast_transaction(self, tx_data: Dict[str, Any]) -> int:
        """
        Broadcast a transaction to all peers.
        
        Args:
            tx_data: Transaction data
        
        Returns:
            int: Number of peers sent to
        """
        msg = create_tx_message(tx_data)
        return self.broadcast_message(msg)
    
    def broadcast_block(self, block_data: Dict[str, Any]) -> int:
        """
        Broadcast a block to all peers.
        
        Args:
            block_data: Block data
        
        Returns:
            int: Number of peers sent to
        """
        msg = create_block_message(block_data)
        return self.broadcast_message(msg)
    
    # ============================================
    # PEER MANAGEMENT
    # ============================================
    
    def get_peer_count(self) -> int:
        """Get number of connected peers."""
        return len(self.peers)
    
    def get_peers(self) -> List[Dict[str, Any]]:
        """Get information about all peers."""
        return [peer.get_info() for peer in self.peers.values()]
    
    def disconnect_peer(self, address: str, port: int) -> None:
        """
        Disconnect a specific peer.
        
        Args:
            address: Peer address
            port: Peer port
        """
        key = peer_key(address, port)
        if key in self.peers:
            self.peers[key].disconnect()
    
    # ============================================
    # TESTING
    # ============================================
    
    def test_network(self) -> bool:
        """
        Test network functionality.
        
        Returns:
            bool: True if tests pass
        """
        print("\n🧪 Testing Network...")
        
        # 1. Test message serialization
        from network.protocol import create_version_message
        msg = create_version_message(1, 0, "test", "localhost", "localhost", 123)
        serialized = msg.to_json()
        deserialized = Message.from_json(serialized)
        assert msg.type == deserialized.type
        print("1. Serialization: ✅")
        
        # 2. Test peer creation
        peer = Peer("127.0.0.1", 8333)
        print(f"2. Peer created: {peer}")
        
        print("\n✅ Network test complete")
        return True


# ============================================
# UTILITY FUNCTIONS
# ============================================

def peer_key(address: str, port: int) -> str:
    """Create a unique key for a peer."""
    return f"{address}:{port}"


# ============================================
# GLOBAL INSTANCE
# ============================================

node = Node()


# ============================================
# TEST FUNCTIONS
# ============================================

def test_node():
    """Quick test for Node."""
    print("\n🧪 Testing Node...")
    
    # Test basic node
    n = Node()
    print(f"1. Node created: {n.host}:{n.port}")
    
    # Test peer key
    key = peer_key("127.0.0.1", 8333)
    print(f"2. Peer key: {key}")
    
    print("\n✅ Node test complete")
    return True


if __name__ == "__main__":
    test_node()
    test_protocol()