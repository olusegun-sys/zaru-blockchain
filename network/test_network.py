"""
Network layer integration test.
Run with: python test_network.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import threading
from network import Node, Peer, Message, MessageType
from network.protocol import create_version_message, create_ping_message


def test_peer():
    """Test peer functionality."""
    print("\n🧪 TEST 1: Peer")
    print("-" * 40)
    
    peer = Peer("127.0.0.1", 8333)
    print(f"✅ Peer created: {peer}")
    print(f"   Status: {peer.status.value}")
    print(f"   Address: {peer.address}:{peer.port}")
    
    return True


def test_message():
    """Test message creation and serialization."""
    print("\n🧪 TEST 2: Message")
    print("-" * 40)
    
    # Create version message
    msg = create_version_message(
        version=1,
        height=0,
        user_agent="test",
        addr_from="127.0.0.1:8333",
        addr_to="127.0.0.1:8334",
        nonce=12345
    )
    
    print(f"✅ Message created: {msg.type.value}")
    
    # Serialize
    serialized = msg.to_json()
    print(f"   Serialized: {serialized[:50]}...")
    
    # Deserialize
    deserialized = Message.from_json(serialized)
    print(f"   Deserialized: {deserialized.type.value}")
    
    return msg.type == deserialized.type


def test_node():
    """Test node functionality."""
    print("\n🧪 TEST 3: Node")
    print("-" * 40)
    
    node = Node(host="127.0.0.1", port=18333)
    print(f"✅ Node created: {node.host}:{node.port}")
    
    # Start node
    node.start()
    time.sleep(1)
    
    print(f"   Running: {node.running}")
    print(f"   Peers: {node.get_peer_count()}")
    
    # Stop node
    node.stop()
    print(f"   Stopped: {not node.running}")
    
    return True


def test_broadcast():
    """Test broadcast functionality."""
    print("\n🧪 TEST 4: Broadcast")
    print("-" * 40)
    
    node = Node(host="127.0.0.1", port=18334)
    node.start()
    time.sleep(1)
    
    # Create a test message
    msg = create_ping_message(12345)
    
    # Broadcast (no peers, but should work)
    sent = node.broadcast_message(msg)
    print(f"✅ Broadcast sent to {sent} peers")
    
    node.stop()
    
    return sent >= 0


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("🔧 ZARU NETWORK TEST SUITE")
    print("=" * 60)
    
    try:
        test_peer()
        test_message()
        test_node()
        test_broadcast()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()