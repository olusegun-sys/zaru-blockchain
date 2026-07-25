"""
ZARU API Routes Module
======================
All REST API endpoints for ZARU.

ADDED: Import private key endpoint.
FIXED: Correct imports from blockchain.utxo.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from blockchain.transaction import Transaction
from blockchain.block import Block
from blockchain.chain_manager import chain_manager
# FIXED: Correct import from blockchain.utxo
from blockchain.utxo import utxo_set
from mempool import mempool
from miner import get_miner
from wallet import wallet
from network import get_node
from config import settings


# ============================================
# PYDANTIC MODELS
# ============================================

class AddressRequest(BaseModel):
    label: Optional[str] = ""


class SendRequest(BaseModel):
    to_address: str = Field(..., description="Recipient address")
    amount: int = Field(..., description="Amount in satoshis")
    from_address: Optional[str] = Field(None, description="Sender address")
    fee: Optional[int] = Field(0, description="Transaction fee in satoshis")
    memo: Optional[str] = Field("", description="Optional memo")


class ImportKeyRequest(BaseModel):
    address: str = Field(..., description="Address associated with the private key")
    private_key: str = Field(..., description="Private key in hex format")
    label: Optional[str] = Field("Imported", description="Label for the imported key")


# ============================================
# ROUTER
# ============================================

router = APIRouter()


# ============================================
# WALLET ENDPOINTS
# ============================================

@router.get("/wallet/addresses")
async def get_addresses() -> Dict[str, Any]:
    try:
        addresses = wallet.get_addresses()
        return {
            "addresses": addresses,
            "count": len(addresses)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wallet/address")
async def create_address(request: AddressRequest) -> Dict[str, Any]:
    try:
        address = wallet.create_address(label=request.label)
        return {
            "address": address,
            "label": request.label,
            "message": "Address created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wallet/import")
async def import_private_key(request: ImportKeyRequest) -> Dict[str, Any]:
    try:
        if not wallet.validate_address(request.address):
            raise HTTPException(status_code=400, detail="Invalid address format")
        
        success = wallet.import_private_key(
            address=request.address,
            private_key_hex=request.private_key,
            label=request.label
        )
        
        if success:
            return {
                "success": True,
                "message": f"Private key imported successfully",
                "address": request.address,
                "label": request.label
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to import private key")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallet/balance/{address}")
async def get_balance(address: str) -> Dict[str, Any]:
    try:
        if not wallet.validate_address(address):
            raise HTTPException(status_code=400, detail="Invalid address format")
        
        full_balance = wallet.get_full_balance(address)
        return {
            "address": address,
            "confirmed": full_balance["confirmed"],
            "pending": full_balance["pending"],
            "total": full_balance["total"],
            "confirmed_display": f"{full_balance['confirmed'] / 100_000_000:.8f} ZARU",
            "pending_display": f"{full_balance['pending'] / 100_000_000:.8f} ZARU",
            "total_display": f"{full_balance['total'] / 100_000_000:.8f} ZARU"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallet/balance")
async def get_total_balance() -> Dict[str, Any]:
    try:
        total = wallet.get_balance()
        pending = wallet.get_pending_balance()
        return {
            "total_confirmed": total,
            "total_pending": pending,
            "total": total + pending,
            "total_confirmed_display": f"{total / 100_000_000:.8f} ZARU",
            "total_pending_display": f"{pending / 100_000_000:.8f} ZARU",
            "total_display": f"{(total + pending) / 100_000_000:.8f} ZARU"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallet/utxos/{address}")
async def get_utxos(address: str) -> Dict[str, Any]:
    try:
        if not wallet.validate_address(address):
            raise HTTPException(status_code=400, detail="Invalid address format")
        
        utxos = wallet.get_utxos(address)
        total = sum(u['amount'] for u in utxos)
        return {
            "address": address,
            "utxos": utxos,
            "count": len(utxos),
            "total": total,
            "total_display": f"{total / 100_000_000:.8f} ZARU"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wallet/send")
async def send_transaction(request: SendRequest) -> Dict[str, Any]:
    try:
        if not wallet.validate_address(request.to_address):
            raise HTTPException(status_code=400, detail="Invalid recipient address")
        
        if request.from_address and not wallet.validate_address(request.from_address):
            raise HTTPException(status_code=400, detail="Invalid sender address")
        
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        success, message, tx = wallet.send(
            to_address=request.to_address,
            amount=request.amount,
            from_address=request.from_address,
            fee=request.fee,
            memo=request.memo
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "success": True,
            "message": message,
            "tx_id": tx.tx_id if tx else None,
            "from_address": request.from_address,
            "to_address": request.to_address,
            "amount": request.amount,
            "fee": request.fee
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallet/transactions/{address}")
async def get_transactions(
    address: str,
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    try:
        if not wallet.validate_address(address):
            raise HTTPException(status_code=400, detail="Invalid address format")
        
        history = wallet.get_transaction_history(address, limit)
        return {
            "address": address,
            "transactions": history,
            "count": len(history),
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallet/info")
async def get_wallet_info() -> Dict[str, Any]:
    try:
        return wallet.get_wallet_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# BLOCKCHAIN ENDPOINTS
# ============================================

@router.get("/blockchain/info")
async def get_chain_info() -> Dict[str, Any]:
    try:
        height = chain_manager.get_height()
        tip = chain_manager.get_tip_hash()
        difficulty = chain_manager.get_difficulty()
        utxo_count = utxo_set.get_utxo_count()
        
        latest = chain_manager.get_block_by_height(height - 1) if height > 0 else None
        
        return {
            "height": height,
            "tip_hash": tip,
            "difficulty": difficulty,
            "utxo_count": utxo_count,
            "mempool_size": mempool.get_mempool_size(),
            "latest_block": {
                "hash": latest.hash if latest else None,
                "timestamp": latest.header.timestamp if latest else None,
                "transactions": len(latest.transactions) if latest else 0,
            } if latest else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blockchain/block/{block_hash}")
async def get_block(block_hash: str) -> Dict[str, Any]:
    try:
        block = chain_manager.get_block(block_hash)
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")
        
        return block.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blockchain/block/height/{height}")
async def get_block_by_height(height: int) -> Dict[str, Any]:
    try:
        if height < 0 or height >= chain_manager.get_height():
            raise HTTPException(status_code=404, detail="Block not found")
        
        block = chain_manager.get_block_by_height(height)
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")
        
        return block.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blockchain/blocks")
async def get_blocks(
    start: int = Query(0, ge=0),
    count: int = Query(10, ge=1, le=100)
) -> Dict[str, Any]:
    try:
        height = chain_manager.get_height()
        end = min(start + count, height)
        
        blocks = []
        for i in range(start, end):
            block = chain_manager.get_block_by_height(i)
            if block:
                blocks.append({
                    "hash": block.hash,
                    "height": block.header.block_height,
                    "timestamp": block.header.timestamp,
                    "transactions": len(block.transactions),
                    "size": block.size
                })
        
        return {
            "blocks": blocks,
            "count": len(blocks),
            "start": start,
            "end": end,
            "total": height
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blockchain/transaction/{tx_id}")
async def get_transaction(tx_id: str) -> Dict[str, Any]:
    try:
        tx = mempool.get_transaction(tx_id)
        if tx:
            return {
                "transaction": tx.to_dict(),
                "source": "mempool",
                "confirmed": False
            }
        
        raise HTTPException(status_code=404, detail="Transaction not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# MINING ENDPOINTS
# ============================================

@router.post("/mining/start")
async def start_mining(
    address: Optional[str] = Body(None, embed=True),
    threads: int = Body(1, embed=True)
) -> Dict[str, Any]:
    try:
        miner = get_miner()
        
        if address:
            miner.set_mining_address(address)
        
        if not miner.address:
            raise HTTPException(status_code=400, detail="Mining address not set")
        
        if miner.is_mining:
            return {"message": "Mining already running", "is_mining": True}
        
        miner.start_mining(continuous=True, num_threads=threads)
        
        return {
            "message": "Mining started",
            "address": miner.address,
            "threads": threads,
            "is_mining": True
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mining/stop")
async def stop_mining() -> Dict[str, Any]:
    try:
        miner = get_miner()
        
        if not miner.is_mining:
            return {"message": "Mining not running", "is_mining": False}
        
        miner.stop_mining()
        return {
            "message": "Mining stopped",
            "is_mining": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mining/status")
async def get_mining_status() -> Dict[str, Any]:
    try:
        miner = get_miner()
        stats = miner.get_stats()
        return {
            "is_mining": stats.get('is_mining', False),
            "blocks_mined": stats.get('blocks_mined', 0),
            "hash_rate": stats.get('hash_rate', 0),
            "hash_rate_display": f"{stats.get('hash_rate', 0):,.0f} H/s",
            "total_hashes": stats.get('total_hashes', 0),
            "total_time": stats.get('total_time', 0),
            "address": stats.get('address'),
            "difficulty": stats.get('difficulty', 0),
            "chain_height": stats.get('chain_height', 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mining/mine")
async def mine_single_block(
    address: Optional[str] = Body(None, embed=True)
) -> Dict[str, Any]:
    try:
        miner = get_miner()
        
        if address:
            miner.set_mining_address(address)
        
        if not miner.address:
            raise HTTPException(status_code=400, detail="Mining address not set")
        
        block = miner.mine_test_block()
        
        if block:
            success, message = miner.submit_block(block)
            return {
                "success": success,
                "message": message,
                "block": {
                    "hash": block.hash,
                    "height": block.header.block_height,
                    "transactions": len(block.transactions),
                    "nonce": block.header.nonce
                }
            }
        else:
            return {
                "success": False,
                "message": "Failed to mine block"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# NETWORK ENDPOINTS
# ============================================

@router.get("/network/info")
async def get_network_info() -> Dict[str, Any]:
    try:
        node = get_node()
        is_running = node.running if hasattr(node, 'running') else False
        
        return {
            "node": {
                "host": settings.NODE_HOST,
                "port": settings.NODE_PORT,
                "running": is_running
            },
            "peers": {
                "count": node.get_peer_count() if hasattr(node, 'get_peer_count') else 0,
                "max": settings.MAX_PEERS
            },
            "bootstrap_peers": settings.BOOTSTRAP_NODES,
            "user_agent": node.user_agent if hasattr(node, 'user_agent') else "Unknown"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/network/peers")
async def get_peers() -> Dict[str, Any]:
    try:
        node = get_node()
        peers = node.get_peers() if hasattr(node, 'get_peers') else []
        return {
            "peers": peers,
            "count": len(peers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/network/connect")
async def connect_peer(
    address: str = Body(..., embed=True),
    port: int = Body(..., embed=True)
) -> Dict[str, Any]:
    try:
        node = get_node()
        peer = node.connect_to_peer(address, port)
        if peer:
            return {
                "success": True,
                "message": f"Connected to {address}:{port}",
                "peer": peer.get_info()
            }
        else:
            return {
                "success": False,
                "message": f"Failed to connect to {address}:{port}"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# MEMPOOL ENDPOINTS
# ============================================

@router.get("/mempool/info")
async def get_mempool_info() -> Dict[str, Any]:
    try:
        state = mempool.get_state()
        return {
            "size": state.get('size', 0),
            "max_size": state.get('max_size', 0),
            "total_fees": state.get('total_fees', 0),
            "total_fees_display": f"{state.get('total_fees', 0) / 100_000_000:.8f} ZARU",
            "transaction_count": state.get('size', 0),
            "addresses": state.get('addresses', 0),
            "spent_utxos": state.get('spent_utxos', 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mempool/transactions")
async def get_mempool_transactions(
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    try:
        transactions = mempool.get_transactions(limit)
        return {
            "transactions": [tx.to_dict() for tx in transactions],
            "count": len(transactions),
            "total": mempool.get_mempool_size()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SYSTEM ENDPOINTS
# ============================================

@router.get("/system/info")
async def get_system_info() -> Dict[str, Any]:
    try:
        import platform
        import psutil
        import time
        
        return {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "node": platform.node(),
            "memory": {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "used": psutil.virtual_memory().used,
                "percent": psutil.virtual_memory().percent
            },
            "cpu": {
                "cores": psutil.cpu_count(),
                "percent": psutil.cpu_percent(interval=1)
            },
            "uptime": time.time() - psutil.boot_time()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))