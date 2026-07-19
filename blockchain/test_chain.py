"""
Comprehensive test for the Chain Manager module.
Run with: python test_chain.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from blockchain.chain_manager import ChainManager
from blockchain.transaction import create_coinbase_transaction
from blockchain.block import Block
from database import store


def test_chain_basic():
    """Test basic chain operations"""
    print("\n🧪 TEST 1: Basic Chain Operations")
    print("-" * 40)
    
    # Create chain manager
    cm = ChainManager()
    
    # Check genesis block
    height = cm.get_height()
    tip = cm.get_tip_hash()
    print(f"✅ Chain height: {height}")
    print(f"✅ Chain tip: {tip[:10]}..." if tip else "❌ No tip")
    
    # Get genesis block
    genesis = cm.get_block_by_height(0)
    if genesis:
        print(f"✅ Genesis block: {genesis.hash[:10]}...")
        print(f"   Transactions: {len(genesis.transactions)}")
    else:
        print("❌ Genesis block not found")
    
    return height > 0


def test_block_template():
    """Test block template creation"""
    print("\n🧪 TEST 2: Block Template Creation")
    print("-" * 40)
    
    cm = ChainManager()
    
    # Create a coinbase transaction
    coinbase = create_coinbase_transaction("TEST_MINER_001", 5000000000)
    
    # Get block template
    template = cm.get_next_block_template([coinbase])
    
    print(f"✅ Block template created:")
    print(f"   Height: {template.header.block_height}")
    print(f"   Difficulty: {template.header.difficulty_target}")
    print(f"   Prev hash: {template.header.prev_block_hash[:10]}...")
    print(f"   Transactions: {len(template.transactions)}")
    
    return template is not None


def test_chain_stats():
    """Test chain statistics"""
    print("\n🧪 TEST 3: Chain Statistics")
    print("-" * 40)
    
    cm = ChainManager()
    stats = cm.get_chain_stats()
    
    print(f"✅ Chain Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    return True


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🔧 ZARU CHAIN MANAGER TEST SUITE")
    print("=" * 60)
    
    try:
        test_chain_basic()
        test_block_template()
        test_chain_stats()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()