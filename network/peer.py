"""
ZARU Peer Module
================
Represents a connected peer node.

WHY: Each connection to another node is represented as a Peer.
This manages the connection state and communication with that peer.
"""

import socket
import time
import threading
import json
from typing import Optional, Dict, Any, Callable
from enum import Enum
from dataclasses import dataclass

from network.protocol import Message, MessageType, serialize_message, deserialize_message


class PeerStatus(Enum):
    """Status of a peer connection."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    HANDSHAKE_SENT = "handshake_sent"
    HANDSHAKE_RECEIVED = "handshake_received"
    READY = "ready"
    ERROR = "error"


@dataclass
class PeerInfo:
    """Information about a peer."""
    address: str
    port: int
    version: int = 0
    user_agent: str = ""
    height: int = 0
    last_seen: float = 0
    last_ping: float = 0
    last_pong: float = 0
    ping_time: float = 0
    connected_at: float = 0
    bytes_sent: int = 0
    bytes_received: int = 0


class Peer:
    """
    Manages a connection to a peer node.
    
    Handles:
    - Socket connection
    - Handshake
    - Message sending/receiving
    - Connection state
    - Ping/Pong
    """
    
    def __init__(
        self,
        address: str,
        port: int,
        on_message: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None
    ):
        """
        Initialize a peer connection.
        
        Args:
            address: Peer address
            port: Peer port
            on_message: Callback for incoming messages
            on_disconnect: Callback for disconnection
        """
        self.address = address
        self.port = port
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        
        self.socket: Optional[socket.socket] = None
        self.status = PeerStatus.DISCONNECTED
        self.info = PeerInfo(address=address, port=port)
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        self._buffer = ""
    
    # ============================================
    # CONNECTION MANAGEMENT
    # ============================================
    
    def connect(self) -> bool:
        """
        Connect to the peer.
        
        Returns:
            bool: True if connected successfully
        """
        try:
            self.status = PeerStatus.CONNECTING
            
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            
            # Connect
            self.socket.connect((self.address, self.port))
            self.socket.settimeout(1)
            
            self.info.connected_at = time.time()
            self.status = PeerStatus.CONNECTED
            
            print(f"✅ Connected to {self.address}:{self.port}")
            
            # Start receiving messages
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            return True
            
        except Exception as e:
            self.status = PeerStatus.ERROR
            print(f"❌ Failed to connect to {self.address}:{self.port}: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the peer."""
        self.running = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.status = PeerStatus.DISCONNECTED
        
        if self.on_disconnect:
            self.on_disconnect(self)
        
        print(f"🔌 Disconnected from {self.address}:{self.port}")
    
    # ============================================
    # HANDSHAKE
    # ============================================
    
    def handshake(
        self,
        version: int,
        user_agent: str,
        height: int,
        nonce: int
    ) -> bool:
        """
        Perform handshake with peer.
        
        Args:
            version: Node version
            user_agent: Node user agent
            height: Current chain height
            nonce: Random nonce for identification
        
        Returns:
            bool: True if handshake successful
        """
        from network.protocol import create_version_message, create_verack_message
        
        # Send version
        msg = create_version_message(
            version=version,
            height=height,
            user_agent=user_agent,
            addr_from=f"{self.address}:{self.port}",
            addr_to=self.address,
            nonce=nonce
        )
        
        if not self.send_message(msg):
            return False
        
        self.status = PeerStatus.HANDSHAKE_SENT
        print(f"🤝 Handshake sent to {self.address}:{self.port}")
        
        # Wait for version and send verack
        # This is handled in the receive loop
        return True
    
    def handle_handshake(self, msg: Message) -> bool:
        """
        Handle incoming handshake message.
        
        Args:
            msg: Handshake message
        
        Returns:
            bool: True if handled successfully
        """
        from network.protocol import create_verack_message
        
        if msg.type == MessageType.VERSION:
            # Update peer info
            self.info.version = msg.payload.get('version', 0)
            self.info.user_agent = msg.payload.get('user_agent', '')
            self.info.height = msg.payload.get('height', 0)
            
            # Send verack
            verack = create_verack_message()
            if self.send_message(verack):
                self.status = PeerStatus.HANDSHAKE_RECEIVED
                print(f"🤝 Handshake received from {self.address}:{self.port}")
                return True
        
        elif msg.type == MessageType.VERACK:
            self.status = PeerStatus.READY
            print(f"✅ Handshake complete with {self.address}:{self.port}")
            return True
        
        return False
    
    # ============================================
    # MESSAGE SENDING/RECEIVING
    # ============================================
    
    def send_message(self, message: Message) -> bool:
        """
        Send a message to the peer.
        
        Args:
            message: Message to send
        
        Returns:
            bool: True if sent successfully
        """
        if not self.socket:
            return False
        
        try:
            data = serialize_message(message)
            self.socket.sendall((data + "\n").encode())
            
            with self.lock:
                self.info.bytes_sent += len(data)
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to send message to {self.address}:{self.port}: {e}")
            return False
    
    def _receive_loop(self) -> None:
        """
        Main receive loop for incoming messages.
        
        WHY: Runs in a separate thread to handle messages
        without blocking other operations.
        """
        while self.running and self.socket:
            try:
                # Receive data
                data = self.socket.recv(4096).decode()
                if not data:
                    break
                
                with self.lock:
                    self.info.bytes_received += len(data)
                
                # Buffer and parse messages
                self._buffer += data
                
                # Split by newlines
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    if line.strip():
                        self._handle_message(line.strip())
                
            except socket.timeout:
                # Timeout is expected - continue
                continue
            except Exception as e:
                # Silently ignore receive errors to reduce noise
                # Only log if it's not a normal disconnection
                if self.running:
                    print(f"⚠️  Receive error from {self.address}:{self.port}: {e}")
                break
        
        # Clean up on exit
        self.disconnect()
    
    def _handle_message(self, data: str) -> None:
        """
        Handle an incoming message with improved error handling.
        
        Args:
            data: Raw message data
        """
        try:
            # Skip empty messages
            if not data or not data.strip():
                return
            
            # Try to deserialize the message
            try:
                message = deserialize_message(data)
            except json.JSONDecodeError:
                # Silently ignore non-JSON data (health checks, scrapers, etc.)
                # This prevents log spam on Render
                return
            except Exception:
                # Silently ignore any other deserialization errors
                return
            
            # Handle handshake
            if message.type in [MessageType.VERSION, MessageType.VERACK]:
                self.handle_handshake(message)
            
            # Handle ping/pong
            elif message.type == MessageType.PING:
                from network.protocol import create_pong_message
                pong = create_pong_message(message.payload.get('nonce', 0))
                self.send_message(pong)
                self.info.last_ping = time.time()
            
            elif message.type == MessageType.PONG:
                self.info.last_pong = time.time()
                self.info.ping_time = self.info.last_pong - self.info.last_ping
            
            # Handle reject
            elif message.type == MessageType.REJECT:
                print(f"⚠️  Reject from {self.address}: {message.payload.get('reason', 'Unknown')}")
            
            # Call message callback (only for valid messages)
            if self.on_message:
                self.on_message(self, message)
                
        except json.JSONDecodeError:
            # Silently ignore JSON errors
            pass
        except Exception as e:
            # Silently ignore all other errors to reduce noise
            pass
    
    # ============================================
    # PING/PONG
    # ============================================
    
    def ping(self) -> bool:
        """
        Send a ping to the peer.
        
        Returns:
            bool: True if ping sent successfully
        """
        from network.protocol import create_ping_message
        import random
        
        nonce = random.randint(0, 2**32 - 1)
        msg = create_ping_message(nonce)
        self.info.last_ping = time.time()
        return self.send_message(msg)
    
    def is_alive(self, timeout: float = 30) -> bool:
        """
        Check if the peer is still alive.
        
        Args:
            timeout: Seconds since last message to consider dead
        
        Returns:
            bool: True if peer is alive
        """
        if self.status != PeerStatus.READY:
            return False
        
        if time.time() - self.info.last_seen > timeout:
            return False
        
        return True
    
    # ============================================
    # UTILITY METHODS
    # ============================================
    
    def get_info(self) -> Dict[str, Any]:
        """Get peer information."""
        return {
            'address': self.address,
            'port': self.port,
            'status': self.status.value,
            'version': self.info.version,
            'user_agent': self.info.user_agent,
            'height': self.info.height,
            'connected_at': self.info.connected_at,
            'bytes_sent': self.info.bytes_sent,
            'bytes_received': self.info.bytes_received,
            'ping_time': self.info.ping_time,
        }
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.address}:{self.port} ({self.status.value})"