"""
Comprehensive test for the Miner module.
Run with: python test_miner_comprehensive.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
from miner import Miner
from blockchain.transaction import Transaction, TxInput, TxOutput
from blockchain.chain_manager import ChainManager
from mempool import Mempool
from database import store


def setup_test_environment():
    """Set up test environment with UTXOs and mempool transactions."""
    print("Setting up test environment...")
    
    # Clear database
    store.clear()
    
    # Create chain manager (creates genesis)
    cm = ChainManager()
    
    # Create mempool
    mempool = Mempool()
    
    # Create test UTXOs for transactions
    test_address = "TEST_SENDER_001"
    store.put_utxo(
        tx_id="TEST_TX_001",
        output_index=0,
        amount=10000,
        address=test_address,
        block_height=1
    )
    store.put_utxo(
        tx_id="TEST_TX_002",
        output_index=0,
        amount=20000,
        address=test_address,
        block_height=1
    )
    
    # Create test transactions
    for i in range(5):
        tx = Transaction(
            inputs=[TxInput(tx_id=f"TEST_TX_00{i+1}", output_index=0)],
            outputs=[TxOutput(amount=1000 * (i + 1), address=f"RECIPIENT_{i}")],
            is_coinbase=False
        )
        tx.tx_id = tx.compute_id()
        mempool.add_transaction(tx)
    
    print(f"   Created {mempool.get_mempool_size()} transactions in mempool")
    print(f"   Chain height: {cm.get_height()}")
    
    return cm, mempool


def test_miner_basic():
    """Test basic miner functionality."""
    print("\n🧪 TEST 1: Basic Miner Operations")
    print("-" * 40)
    
    cm, mempool = setup_test_environment()
    miner = Miner(chain_manager=cm, mempool=mempool)
    
    # Set mining address
    miner.set_mining_address("TEST_MINER_001")
    
    # Create block template
    block = miner.create_block_template()
    
    if block:
        print(f"✅ Block template created:")
        print(f"   Height: {block.header.block_height}")
        print(f"   Transactions: {len(block.transactions)}")
        print(f"   Difficulty: {block.header.difficulty_target}")
        return True
    else:
        print("❌ Failed to create block template")
        return False


def test_miner_single_block():
    """Test mining a single block."""
    print("\n🧪 TEST 2: Mine Single Block")
    print("-" * 40)
    
    cm, mempool = setup_test_environment()
    miner = Miner(chain_manager=cm, mempool=mempool)
    miner.set_mining_address("TEST_MINER_002")
    
    # Mine with lower difficulty (faster)
    block = miner.mine_test_block()
    
    if block:
        print(f"✅ Block mined successfully!")
        print(f"   Height: {block.header.block_height}")
        print(f"   Hash: {block.hash[:16]}...")
        print(f"   Nonce: {block.header.nonce}")
        print(f"   Transactions: {len(block.transactions)}")
        return True
    else:
        print("❌ Failed to mine block")
        return False


def test_miner_continuous():
    """Test continuous mining."""
    print("\n🧪 TEST 3: Continuous Mining")
    print("-" * 40)
    
    cm, mempool = setup_test_environment()
    miner = Miner(chain_manager=cm, mempool=mempool)
    miner.set_mining_address("TEST_MINER_003")
    
    # Start mining (mine 1 block then stop)
    print("Starting mining (will mine 1 block)...")
    miner.start_mining(continuous=False, num_threads=2)
    
    # Wait for mining to complete
    time.sleep(2)
    
    # Check stats
    stats = miner.get_stats()
    print(f"✅ Mining stats:")
    print(f"   Blocks mined: {stats['blocks_mined']}")
    print(f"   Hash rate: {stats['hash_rate']:,.0f} H/s")
    
    # Check chain height
    height = cm.get_height()
    print(f"   Chain height: {height}")
    
    # Stop mining
    miner.stop_mining()
    
    return stats['blocks_mined'] > 0


def test_miner_mempool_integration():
    """Test mempool integration."""
    print("\n🧪 TEST 4: Mempool Integration")
    print("-" * 40)
    
    cm, mempool = setup_test_environment()
    
    # Get initial mempool size
    initial_size = mempool.get_mempool_size()
    print(f"Initial mempool size: {initial_size}")
    
    # Mine a block
    miner = Miner(chain_manager=cm, mempool=mempool)
    miner.set_mining_address("TEST_MINER_004")
    block = miner.mine_test_block()
    
    if block:
        # Submit block
        success, message = miner.submit_block(block)
        print(f"✅ Block submitted: {success} - {message}")
        
        # Check mempool size
        final_size = mempool.get_mempool_size()
        print(f"Final mempool size: {final_size}")
        
        # Check chain height
        height = cm.get_height()
        print(f"Chain height: {height}")
        
        return success
    else:
        print("❌ Failed to mine block")
        return False


def test_miner_stats():
    """Test mining statistics."""
    print("\n🧪 TEST 5: Mining Statistics")
    print("-" * 40)
    
    cm, mempool = setup_test_environment()
    miner = Miner(chain_manager=cm, mempool=mempool)
    miner.set_mining_address("TEST_MINER_005")
    
    # Reset stats
    miner.reset_stats()
    print("Stats reset")
    
    # Mine a block
    block = miner.mine_test_block()
    
    if block:
        # Get stats
        stats = miner.get_stats()
        print(f"✅ Mining statistics:")
        print(f"   Blocks mined: {stats['blocks_mined']}")
        print(f"   Total hashes: {stats['total_hashes']:,}")
        print(f"   Total time: {stats['total_time']:.2f}s")
        print(f"   Hash rate: {stats['hash_rate']:,.0f} H/s")
        print(f"   Is mining: {stats['is_mining']}")
        print(f"   Address: {stats['address']}")
        print(f"   Difficulty: {stats['difficulty']}")
        print(f"   Chain height: {stats['chain_height']}")
        return True
    else:
        print("❌ Failed to mine block")
        return False


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("🔧 ZARU MINER TEST SUITE")
    print("=" * 60)
    
    try:
        test_miner_basic()
        test_miner_single_block()
        test_miner_continuous()
        test_miner_mempool_integration()
        test_miner_stats()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()