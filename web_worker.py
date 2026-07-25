#!/usr/bin/env python
"""
ZARU Web Worker for Render Free Tier
====================================
Runs as a web service with Flask to keep the miner alive.
Render pings /health every few minutes, which keeps the service awake.
The miner runs in a background thread while Flask handles requests.

FIXED: Uses the wallet's first address for mining.
ADDED: Export private key endpoint and send endpoint.
All mined coins will go to the wallet address displayed in the UI.
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request

# Import ZARU components
from miner import miner
from wallet import wallet
from blockchain.chain_manager import chain_manager
from blockchain.transaction import Transaction, TxInput, TxOutput, create_transaction
from blockchain.utxo import get_utxos_for_address
from mempool import mempool

# ============================================
# LOGGING CONFIGURATION
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================
# FLASK APP
# ============================================

app = Flask(__name__)

# Global state
mining_active = False
mining_address = None
start_time = time.time()
blocks_mined = 0

# ============================================
# ROUTES
# ============================================

@app.route('/')
@app.route('/health')
def health():
    """Health check endpoint - keeps the service alive on Render."""
    stats = miner.get_stats() if mining_active else {}
    return jsonify({
        "status": "healthy",
        "mining": mining_active,
        "address": mining_address,
        "blocks_mined": stats.get('blocks_mined', 0),
        "chain_height": chain_manager.get_height(),
        "uptime_seconds": int(time.time() - start_time),
        "uptime_hours": round((time.time() - start_time) / 3600, 2),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/start')
def start_mining_route():
    """Start the mining process via API."""
    global mining_active, mining_address
    if not mining_active:
        try:
            # Use the wallet's first address
            addresses = wallet.get_addresses()
            if addresses:
                mining_address = addresses[0]
                logger.info(f"📝 Using existing wallet address: {mining_address}")
            else:
                mining_address = wallet.create_address(label="Render_Web_Miner")
                logger.info(f"📝 Created new wallet address: {mining_address}")
            
            miner.set_mining_address(mining_address)
            miner.start_mining(continuous=True, num_threads=2)
            mining_active = True
            logger.info(f"✅ Mining started with address: {mining_address}")
            logger.info(f"💰 All rewards will go to: {mining_address}")
            return jsonify({"status": "started", "address": mining_address})
        except Exception as e:
            logger.error(f"❌ Failed to start mining: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "already_running", "address": mining_address})

@app.route('/stop')
def stop_mining_route():
    """Stop the mining process via API."""
    global mining_active
    if mining_active:
        miner.stop_mining()
        mining_active = False
        logger.info("⛏️ Mining stopped")
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})

@app.route('/status')
def status():
    """Detailed status endpoint."""
    stats = miner.get_stats() if mining_active else {}
    balance = 0
    if mining_address:
        try:
            balance = wallet.get_balance(mining_address)
        except:
            pass
    return jsonify({
        "mining": mining_active,
        "address": mining_address,
        "balance_satoshis": balance,
        "balance_zar": balance / 100000000 if balance else 0,
        "blocks_mined": stats.get('blocks_mined', 0),
        "hash_rate": stats.get('hash_rate', 0),
        "chain_height": chain_manager.get_height(),
        "uptime_hours": round((time.time() - start_time) / 3600, 2),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/export_private_key')
def export_private_key():
    """
    Export the mining address private key.
    
    Returns:
        JSON with address and private_key_hex
    
    WHY: This allows importing the mining address into the API wallet
    so users can send ZARU from the mining address.
    """
    try:
        if not mining_address:
            return jsonify({"error": "Mining address not set"}), 400
        
        # Get the private key from the wallet's key store
        private_key = wallet.key_store.get_private_key(mining_address)
        
        if not private_key:
            return jsonify({"error": "Private key not found for mining address"}), 404
        
        return jsonify({
            "success": True,
            "address": mining_address,
            "private_key_hex": private_key.hex()
        })
    except Exception as e:
        logger.error(f"❌ Failed to export private key: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/send_to', methods=['POST'])
def send_from_mining():
    """
    Send ZARU from the mining address to a specified address.
    
    Request body:
    {
        "to_address": "recipient_address",
        "amount": 100000000  # amount in satoshis
    }
    
    Returns:
        JSON with transaction result
    """
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400
        
        to_address = data.get('to_address')
        amount = data.get('amount')
        
        if not to_address:
            return jsonify({"error": "Missing to_address"}), 400
        
        if not amount or int(amount) <= 0:
            return jsonify({"error": "Invalid amount"}), 400
        
        amount = int(amount)
        
        # Check if mining address is set
        if not mining_address:
            return jsonify({"error": "Mining address not set"}), 400
        
        # Get UTXOs for the mining address
        utxos = get_utxos_for_address(mining_address)
        if not utxos:
            return jsonify({"error": "No UTXOs found for mining address"}), 400
        
        # Select UTXOs to cover the amount
        selected_utxos = []
        total_selected = 0
        for utxo in utxos:
            selected_utxos.append(utxo)
            total_selected += utxo['amount']
            if total_selected >= amount:
                break
        
        if total_selected < amount:
            return jsonify({"error": f"Insufficient funds: need {amount}, have {total_selected}"}), 400
        
        # Calculate fee (use default)
        fee = 1000  # Small fee
        
        # Create transaction inputs
        inputs = []
        for utxo in selected_utxos:
            inputs.append(TxInput(
                tx_id=utxo['tx_id'],
                output_index=utxo['output_index']
            ))
        
        # Create transaction outputs
        outputs = [TxOutput(amount=amount, address=to_address)]
        
        # Add change output if needed
        change = total_selected - amount - fee
        if change > 0:
            outputs.append(TxOutput(amount=change, address=mining_address))
        
        # Get private key
        private_key = wallet.key_store.get_private_key(mining_address)
        if not private_key:
            return jsonify({"error": "Private key not found for mining address"}), 400
        
        # Create and sign transaction
        tx = create_transaction(inputs, outputs, private_key)
        if not tx:
            return jsonify({"error": "Failed to create transaction"}), 400
        
        # Validate transaction
        from blockchain.utxo import UTXOSet
        utxo_set = UTXOSet()
        is_valid, error = utxo_set.validate_transaction(tx)
        if not is_valid:
            return jsonify({"error": f"Transaction invalid: {error}"}), 400
        
        # Add to mempool
        success, message = mempool.add_transaction(tx)
        if not success:
            return jsonify({"error": f"Failed to add to mempool: {message}"}), 400
        
        logger.info(f"✅ Transaction sent from {mining_address[:10]}... to {to_address[:10]}...")
        logger.info(f"   Amount: {amount} satoshis")
        logger.info(f"   TX ID: {tx.tx_id[:16]}...")
        
        return jsonify({
            "success": True,
            "message": "Transaction sent successfully",
            "tx_id": tx.tx_id,
            "amount": amount,
            "from_address": mining_address,
            "to_address": to_address,
            "fee": fee
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to send transaction: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 Starting ZARU Web Worker on RENDER")
    logger.info("=" * 60)
    logger.info(f"   Time: {datetime.now().isoformat()}")
    logger.info(f"   Python: {sys.version}")
    logger.info(f"   Working Dir: {os.getcwd()}")
    
    # Use the wallet's first address for mining
    addresses = wallet.get_addresses()
    
    if addresses:
        mining_address = addresses[0]
        logger.info(f"📝 Using existing wallet address: {mining_address}")
    else:
        mining_address = wallet.create_address(label="Render_Web_Miner")
        logger.info(f"📝 Created new wallet address: {mining_address}")
    
    logger.info(f"💰 MINING REWARDS WILL GO TO: {mining_address}")
    logger.info(f"🔑 Private key is stored in the miner's key store")
    logger.info(f"📤 Use /export_private_key to get the private key")
    logger.info(f"📤 Use /send_to to send ZARU from the mining address")
    
    # Set the mining address
    miner.set_mining_address(mining_address)
    
    # Start mining with 2 threads (balanced for Render free tier)
    miner.start_mining(continuous=True, num_threads=2)
    mining_active = True
    
    logger.info(f"✅ Mining started successfully!")
    logger.info(f"   Address: {mining_address}")
    logger.info(f"   Threads: 2")
    logger.info(f"   Mode: Continuous")
    
    # Run Flask web server for health checks
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Starting Flask server on port {port}")
    logger.info("=" * 60)
    app.run(host="0.0.0.0", port=port)