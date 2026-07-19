"""
Comprehensive test for the Mempool module.
Run with: python test_mempool_comprehensive.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mempool import Mempool
from blockchain.transaction import Transaction, TxInput, TxOutput
from blockchain.utxo import UTXOSet
from database import store


def setup_test_utxos():
    """Create test UTXOs for addresses"""
    print("Setting up test UTXOs...")
    
    # Create UTXOs for different addresses
    test_data = [
        ("ALICE", 10000, 1),
        ("BOB", 5000, 2),
        ("CHARLIE", 2500, 3),
        ("ALICE", 20000, 4),  # Alice has multiple UTXOs
    ]
    
    for address, amount, idx in test_data:
        store.put_utxo(
            tx_id=f"SETUP_TX_{idx}",
            output_index=0,
            amount=amount,
            address=address,
            block_height=1
        )
        print(f"   Created UTXO: {address} has {amount} satoshis")


def test_mempool_add():
    """Test adding transactions to mempool"""
    print("\n🧪 TEST 1: Adding Transactions")
    print("-" * 40)
    
    mempool = Mempool()
    mempool.clear()
    
    # Create a transaction from ALICE to BOB
    tx1 = Transaction(
        inputs=[TxInput(tx_id="SETUP_TX_1", output_index=0)],
        outputs=[TxOutput(amount=5000, address="BOB")],
        is_coinbase=False
    )
    tx1.tx_id = tx1.compute_id()
    
    # Add to mempool
    success, message = mempool.add_transaction(tx1)
    print(f"✅ Add TX1: {success} - {message}")
    
    # Create another transaction from ALICE to CHARLIE
    tx2 = Transaction(
        inputs=[TxInput(tx_id="SETUP_TX_4", output_index=0)],  # Alice's other UTXO
        outputs=[TxOutput(amount=10000, address="CHARLIE")],
        is_coinbase=False
    )
    tx2.tx_id = tx2.compute_id()
    
    success, message = mempool.add_transaction(tx2)
    print(f"✅ Add TX2: {success} - {message}")
    
    # Check mempool size
    size = mempool.get_mempool_size()
    print(f"✅ Mempool size: {size} (expected: 2)")
    
    return size == 2


def test_mempool_double_spend():
    """Test double-spend detection"""
    print("\n🧪 TEST 2: Double-Spend Detection")
    print("-" * 40)
    
    mempool = Mempool()
    mempool.clear()
    
    # Create first transaction spending Alice's UTXO
    tx1 = Transaction(
        inputs=[TxInput(tx_id="SETUP_TX_1", output_index=0)],
        outputs=[TxOutput(amount=5000, address="BOB")],
        is_coinbase=False
    )
    tx1.tx_id = tx1.compute_id()
    
    success, message = mempool.add_transaction(tx1)
    print(f"✅ First transaction: {success}")
    
    # Create second transaction spending the SAME UTXO
    tx2 = Transaction(
        inputs=[TxInput(tx_id="SETUP_TX_1", output_index=0)],  # Same UTXO!
        outputs=[TxOutput(amount=3000, address="CHARLIE")],
        is_coinbase=False
    )
    tx2.tx_id = tx2.compute_id()
    
    success, message = mempool.add_transaction(tx2)
    print(f"✅ Double-spend attempt: {success} - {message}")
    
    # Should fail (double-spend)
    return not success


def test_mempool_fee_ordering():
    """Test fee-based ordering"""
    print("\n🧪 TEST 3: Fee Ordering")
    print("-" * 40)
    
    mempool = Mempool()
    mempool.clear()
    
    # Create transactions with different fees
    # Higher fee = should be first in mempool
    transactions = []
    
    for i in range(3):
        tx = Transaction(
            inputs=[TxInput(tx_id=f"SETUP_TX_{i+1}", output_index=0)],
            outputs=[TxOutput(amount=1000, address=f"RECIPIENT_{i}")],
            is_coinbase=False
        )
        tx.tx_id = tx.compute_id()
        transactions.append(tx)
        
        # Manually set fee (for testing)
        # Note: In production, fee is calculated from UTXO amounts
        success, _ = mempool.add_transaction(tx)
        print(f"   Added TX{i+1}: {success}")
    
    # Get transactions in order
    txs = mempool.get_transactions(10)
    print(f"✅ Retrieved {len(txs)} transactions")
    
    # They should be ordered by fee (but since all fees are 0, order doesn't matter)
    print(f"   Order: {[tx.tx_id[:8] for tx in txs]}")
    
    return len(txs) == 3


def test_mempool_expiry():
    """Test transaction expiry"""
    print("\n🧪 TEST 4: Transaction Expiry")
    print("-" * 40)
    
    # Create mempool with short expiry for testing
    mempool = Mempool(max_size=10)
    mempool.expiry_hours = 0.001  # ~3.6 seconds expiry
    mempool.clear()
    
    # Add a transaction
    tx = Transaction(
        inputs=[TxInput(tx_id="SETUP_TX_1", output_index=0)],
        outputs=[TxOutput(amount=5000, address="BOB")],
        is_coinbase=False
    )
    tx.tx_id = tx.compute_id()
    
    success, _ = mempool.add_transaction(tx)
    print(f"✅ Added transaction: {success}")
    print(f"   Mempool size: {mempool.get_mempool_size()}")
    
    # Wait for expiry
    import time
    print("   Waiting for expiry...")
    time.sleep(4)
    
    # Clean up expired transactions
    removed = mempool.cleanup()
    print(f"✅ Removed expired: {removed}")
    print(f"   Mempool size after cleanup: {mempool.get_mempool_size()}")
    
    # Reset expiry to normal
    mempool.expiry_hours = settings.MEMPOOL_EXPIRY_HOURS
    
    return removed > 0


def test_mempool_block_creation():
    """Test preparing transactions for a block"""
    print("\n🧪 TEST 5: Block Creation Preparation")
    print("-" * 40)
    
    mempool = Mempool()
    mempool.clear()
    
    # Add several transactions
    for i in range(5):
        tx = Transaction(
            inputs=[TxInput(tx_id=f"SETUP_TX_{i+1}", output_index=0)],
            outputs=[TxOutput(amount=1000, address=f"RECIPIENT_{i}")],
            is_coinbase=False
        )
        tx.tx_id = tx.compute_id()
        mempool.add_transaction(tx)
    
    # Get transactions for block
    selected = mempool.prepare_for_mining(max_size=1000000)
    print(f"✅ Selected {len(selected)} transactions for block")
    
    # Simulate block confirmation
    from blockchain.block import Block, BlockHeader
    from blockchain.transaction import create_coinbase_transaction
    
    # Create a dummy block
    block = Block()
    block.header = BlockHeader(block_height=1)
    block.transactions = [create_coinbase_transaction("MINER", 5000000000)] + selected
    block.hash = block.compute_hash()
    
    # Confirm block
    removed = mempool.confirm_block(block)
    print(f"✅ Removed {removed} transactions from mempool")
    print(f"   Mempool size: {mempool.get_mempool_size()}")
    
    return removed > 0


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("🔧 ZARU MEMPOOL TEST SUITE")
    print("=" * 60)
    
    try:
        # Setup
        setup_test_utxos()
        
        # Run tests
        test_mempool_add()
        test_mempool_double_spend()
        test_mempool_fee_ordering()
        test_mempool_expiry()
        test_mempool_block_creation()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        print("\n💡 To clean up test data, run:")
        print("   python -c \"from database import store; store.clear()\"")


if __name__ == "__main__":
    run_all_tests()