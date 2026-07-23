"""
ZARU Wallet Module
==================
Complete wallet implementation with key management, address generation,
transaction creation, and balance checking.

WHY: The wallet is the user interface to the blockchain.
It allows users to:
1. Generate new addresses (keys)
2. Check balances
3. Send transactions
4. Receive transactions

FIXED: Address cache is explicitly updated when creating a new address.
"""

import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

# ECDSA for key generation
from ecdsa import SigningKey, VerifyingKey, SECP256k1

from config import settings
from blockchain.transaction import Transaction, TxInput, TxOutput, create_transaction
from blockchain.utxo import UTXOSet, get_balance_for_address, get_utxos_for_address
from blockchain.chain_manager import ChainManager
from mempool import Mempool
from wallet.key_store import KeyStore


class Wallet:
    """
    Complete cryptocurrency wallet.
    
    Manages:
    - Key generation and storage
    - Address creation
    - Balance checking
    - Transaction creation and signing
    - Transaction history
    """
    
    def __init__(
        self,
        key_store: Optional[KeyStore] = None,
        utxo_set: Optional[UTXOSet] = None,
        chain_manager: Optional[ChainManager] = None,
        mempool: Optional[Mempool] = None,
        password: Optional[str] = None
    ):
        """
        Initialize the wallet.
        
        Args:
            key_store: Key store instance (creates new if None)
            utxo_set: UTXO set instance (creates new if None)
            chain_manager: Chain manager instance (creates new if None)
            mempool: Mempool instance (creates new if None)
            password: Master password for key store
        """
        self.key_store = key_store if key_store else KeyStore(password=password)
        self.utxo_set = utxo_set if utxo_set else UTXOSet()
        self.chain_manager = chain_manager if chain_manager else ChainManager()
        self.mempool = mempool if mempool else Mempool()
        
        # Cache
        self._address_cache: Dict[str, Dict[str, Any]] = {}
        
        print(f"✅ Wallet initialized")
        print(f"   Keys: {len(self.key_store)}")
        print(f"   Chain height: {self.chain_manager.get_height()}")
    
    # ============================================
    # KEY AND ADDRESS MANAGEMENT
    # ============================================
    
    def create_address(self, label: str = "") -> str:
        """
        Create a new address (key pair).
        
        Args:
            label: Optional label for the address
        
        Returns:
            str: New address (public key hash)
        
        WHY: Users need new addresses to receive payments.
        Each address has a unique private key.
        """
        # Generate private key
        sk = SigningKey.generate(curve=SECP256k1)
        private_key = sk.to_string()
        
        # Get public key
        vk = sk.get_verifying_key()
        pub_key = vk.to_string()
        
        # Create address (hash of public key)
        address = self._public_key_to_address(pub_key)
        
        # Store private key in key store (saves to disk)
        self.key_store.add_key(address, private_key, label)
        
        # FIXED: Explicitly update the address cache with the new address
        self._address_cache[address] = {
            'public_key': pub_key.hex(),
            'label': label,
            'created_at': time.time()
        }
        
        print(f"✅ Address created: {address[:10]}... ({label or 'no label'})")
        print(f"   Total addresses: {len(self.key_store)}")
        return address
    
    def get_addresses(self) -> List[str]:
        """Get all addresses in the wallet."""
        return self.key_store.get_all_addresses()
    
    def get_address_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an address.
        
        Args:
            address: Address to look up
        
        Returns:
            Optional[Dict]: Address information
        """
        if address not in self._address_cache:
            # Load from key store
            info = self.key_store.get_key_info(address)
            if info:
                self._address_cache[address] = info
        
        return self._address_cache.get(address)
    
    def _public_key_to_address(self, pub_key: bytes) -> str:
        """
        Convert a public key to an address.
        
        WHY: Addresses are a human-readable form of the public key.
        We use SHA-256 to create a fixed-length identifier.
        """
        # SHA-256 hash of public key
        hash1 = hashlib.sha256(pub_key).digest()
        # Second hash (for extra security)
        hash2 = hashlib.sha256(hash1).digest()
        # Return as hex string (first 40 chars)
        return hash2.hex()[:40]
    
    # ============================================
    # BALANCE CHECKING
    # ============================================
    
    def get_balance(self, address: Optional[str] = None) -> int:
        """
        Get balance for an address or all addresses.
        
        Args:
            address: Specific address or None for total
        
        Returns:
            int: Balance in satoshis
        
        WHY: Users need to know how much money they have.
        """
        if address:
            return get_balance_for_address(address)
        
        # Total balance across all addresses
        total = 0
        for addr in self.get_addresses():
            total += get_balance_for_address(addr)
        return total
    
    def get_pending_balance(self, address: Optional[str] = None) -> int:
        """
        Get pending balance (in mempool).
        
        Args:
            address: Specific address or None for total
        
        Returns:
            int: Pending balance in satoshis
        
        WHY: Transactions in the mempool are not yet confirmed.
        Users should see pending transactions separately.
        """
        if address:
            return self.mempool.get_pending_balance(address)
        
        total = 0
        for addr in self.get_addresses():
            total += self.mempool.get_pending_balance(addr)
        return total
    
    def get_full_balance(self, address: Optional[str] = None) -> Dict[str, int]:
        """
        Get full balance including pending.
        
        Args:
            address: Specific address or None for total
        
        Returns:
            Dict: {confirmed, pending, total}
        """
        confirmed = self.get_balance(address)
        pending = self.get_pending_balance(address)
        return {
            'confirmed': confirmed,
            'pending': pending,
            'total': confirmed + pending
        }
    
    def get_utxos(self, address: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get UTXOs for an address or all addresses.
        
        Args:
            address: Specific address or None for all
        
        Returns:
            List[Dict]: List of UTXOs
        """
        if address:
            return get_utxos_for_address(address)
        
        all_utxos = []
        for addr in self.get_addresses():
            all_utxos.extend(get_utxos_for_address(addr))
        return all_utxos
    
    # ============================================
    # TRANSACTION CREATION
    # ============================================
    
    def send(
        self,
        to_address: str,
        amount: int,
        from_address: Optional[str] = None,
        fee: int = 0,
        memo: str = ""
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """
        Send coins to an address.
        
        Args:
            to_address: Recipient address
            amount: Amount in satoshis
            from_address: Sender address (uses first with sufficient balance if None)
            fee: Transaction fee in satoshis (auto-calculated if 0)
            memo: Optional memo
        
        Returns:
            Tuple[bool, str, Optional[Transaction]]: (success, message, transaction)
        
        WHY: This is the main function for sending money.
        It handles all the complexity of selecting UTXOs and signing.
        
        THINK OF IT LIKE: Writing a check. You specify the recipient,
        amount, and your account. The wallet handles the rest.
        """
        # 1. Find a sender address
        if from_address:
            sender = from_address
        else:
            # Find an address with sufficient balance
            sender = self._find_address_with_balance(amount + fee)
        
        if not sender:
            return False, "No address with sufficient balance found", None
        
        # 2. Get private key for sender
        private_key = self.key_store.get_private_key(sender)
        if not private_key:
            return False, "Private key not found for address", None
        
        # 3. Get UTXOs for the sender
        utxos = get_utxos_for_address(sender)
        if not utxos:
            return False, "No UTXOs found for address", None
        
        # 4. Select UTXOs to cover amount
        selected_utxos = []
        total_selected = 0
        
        for utxo in utxos:
            selected_utxos.append(utxo)
            total_selected += utxo['amount']
            if total_selected >= amount + fee:
                break
        
        if total_selected < amount + fee:
            return False, f"Insufficient funds: need {amount + fee}, have {total_selected}", None
        
        # 5. Calculate fee (auto if not specified)
        if fee == 0:
            fee = self._calculate_fee(len(selected_utxos), 2)  # 1 recipient + 1 change
        
        # 6. Create transaction inputs
        inputs = []
        for utxo in selected_utxos:
            inputs.append(TxInput(
                tx_id=utxo['tx_id'],
                output_index=utxo['output_index']
            ))
        
        # 7. Create transaction outputs
        outputs = [TxOutput(amount=amount, address=to_address)]
        
        # 8. Add change output if needed
        change = total_selected - amount - fee
        if change > 0:
            outputs.append(TxOutput(amount=change, address=sender))
        
        # 9. Create and sign transaction
        tx = create_transaction(inputs, outputs, private_key)
        if not tx:
            return False, "Failed to create transaction", None
        
        # 10. Validate transaction
        is_valid, error = self.utxo_set.validate_transaction(tx)
        if not is_valid:
            return False, f"Transaction invalid: {error}", None
        
        # 11. Add to mempool
        success, message = self.mempool.add_transaction(tx)
        if not success:
            return False, f"Failed to add to mempool: {message}", None
        
        print(f"✅ Transaction sent!")
        print(f"   From: {sender[:10]}...")
        print(f"   To: {to_address[:10]}...")
        print(f"   Amount: {amount} satoshis")
        print(f"   Fee: {fee} satoshis")
        print(f"   TX ID: {tx.tx_id[:16]}...")
        
        return True, "Transaction sent successfully", tx
    
    def _find_address_with_balance(self, amount: int) -> Optional[str]:
        """
        Find an address with sufficient balance.
        
        Args:
            amount: Amount needed in satoshis
        
        Returns:
            Optional[str]: Address with sufficient balance
        """
        for address in self.get_addresses():
            balance = get_balance_for_address(address)
            if balance >= amount:
                return address
        return None
    
    def _calculate_fee(self, input_count: int, output_count: int) -> int:
        """
        Calculate transaction fee.
        
        Args:
            input_count: Number of inputs
            output_count: Number of outputs
        
        Returns:
            int: Fee in satoshis
        """
        # Estimate size: 10 bytes overhead + 148 bytes per input + 34 bytes per output
        estimated_size = 10 + (input_count * 148) + (output_count * 34)
        
        # Fee per byte (default: 10 satoshis/byte)
        fee_per_byte = 10
        
        fee = estimated_size * fee_per_byte
        return max(fee, settings.MIN_RELAY_FEE)
    
    # ============================================
    # TRANSACTION HISTORY
    # ============================================
    
    def get_transaction_history(
        self,
        address: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get transaction history.
        
        Args:
            address: Specific address or None for all
            limit: Maximum number of transactions
        
        Returns:
            List[Dict]: Transaction history
        
        WHY: Users need to see their transaction history.
        """
        # TODO: Implement transaction history from database
        # For now, return empty list
        return []
    
    # ============================================
    # ADDRESS VALIDATION
    # ============================================
    
    def validate_address(self, address: str) -> bool:
        """
        Validate a cryptocurrency address.
        
        Args:
            address: Address to validate
        
        Returns:
            bool: True if address is valid
        
        WHY: Prevent sending to invalid addresses.
        """
        # Check length
        if len(address) != 40:
            return False
        
        # Check if it's hex
        try:
            int(address, 16)
            return True
        except ValueError:
            return False
    
    # ============================================
    # WALLET MANAGEMENT
    # ============================================
    
    def lock(self) -> None:
        """Lock the wallet."""
        self.key_store.lock()
        print("🔒 Wallet locked")
    
    def unlock(self, password: str) -> bool:
        """
        Unlock the wallet.
        
        Args:
            password: Master password
        
        Returns:
            bool: True if unlocked
        """
        return self.key_store.unlock(password)
    
    def export(self, file_path: Path) -> bool:
        """
        Export the wallet to a file.
        
        Args:
            file_path: Path to export to
        
        Returns:
            bool: True if exported
        """
        return self.key_store.export_wallet(file_path)
    
    def import_wallet(self, file_path: Path) -> bool:
        """
        Import a wallet from a file.
        
        Args:
            file_path: Path to import from
        
        Returns:
            bool: True if imported
        """
        return self.key_store.import_wallet(file_path)
    
    def get_wallet_info(self) -> Dict[str, Any]:
        """
        Get wallet information.
        
        Returns:
            Dict: Wallet information
        """
        addresses = self.get_addresses()
        total_balance = self.get_balance()
        pending_balance = self.get_pending_balance()
        
        return {
            'address_count': len(addresses),
            'addresses': addresses[:10],  # Show first 10
            'total_balance': total_balance,
            'pending_balance': pending_balance,
            'total_balance_display': f"{total_balance / 100_000_000:.8f} ZARU",
            'chain_height': self.chain_manager.get_height(),
            'utxo_count': self.utxo_set.get_utxo_count(),
            'mempool_size': self.mempool.get_mempool_size(),
        }
    
    # ============================================
    # UTILITY
    # ============================================
    
    def generate_mnemonic(self) -> str:
        """
        Generate a seed phrase (BIP39 style).
        
        Returns:
            str: 12-word seed phrase
        
        WHY: Seed phrases are a human-readable way to backup wallets.
        """
        # TODO: Implement BIP39 mnemonic generation
        return "TODO: Implement mnemonic generation"
    
    def restore_from_mnemonic(self, mnemonic: str) -> bool:
        """
        Restore wallet from seed phrase.
        
        Args:
            mnemonic: 12-word seed phrase
        
        Returns:
            bool: True if restored
        
        WHY: Users can restore their wallet from a seed phrase.
        """
        # TODO: Implement BIP39 restoration
        return False


# ============================================
# GLOBAL INSTANCE
# ============================================

# Create a global wallet instance
wallet = Wallet()


# ============================================
# TEST FUNCTIONS
# ============================================

def test_wallet():
    """
    Quick test to verify Wallet is working.
    """
    print("\n🧪 Testing Wallet...")
    
    # 1. Create wallet
    w = Wallet()
    print("1. Wallet created")
    
    # 2. Create address
    address = w.create_address(label="Test Address")
    print(f"2. Address created: {address[:10]}...")
    
    # 3. Get balance
    balance = w.get_balance(address)
    print(f"3. Balance: {balance} satoshis")
    
    # 4. Get wallet info
    info = w.get_wallet_info()
    print(f"4. Wallet info:")
    print(f"   Addresses: {info['address_count']}")
    print(f"   Total balance: {info['total_balance_display']}")
    
    print("\n✅ Wallet test complete")
    return True


if __name__ == "__main__":
    test_wallet()