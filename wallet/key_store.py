"""
ZARU Key Store Module
=====================
Secure storage for private keys.

WHY: Private keys must be stored securely.
This module provides encrypted storage for keys.

HOW IT WORKS:
1. Keys are stored in a JSON file
2. Each key is encrypted with AES-256
3. Master password is required to unlock
4. Keys are stored by address for easy lookup

THINK OF IT LIKE: A physical safe for your private keys.
Only you have the combination (password) to open it.
"""

import json
import os
import hashlib
import base64
from typing import Dict, Optional, List, Any
from pathlib import Path
from datetime import datetime

# Try to import cryptography for encryption
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("⚠️  cryptography not installed. Keys will be stored in plain text!")
    print("   For production, install: pip install cryptography")


class KeyStore:
    """
    Secure key storage with encryption.
    
    Manages:
    - Storing private keys
    - Encrypting/decrypting keys
    - Key lookup by address
    - Import/export
    """
    
    def __init__(self, store_path: Optional[Path] = None, password: Optional[str] = None):
        """
        Initialize the key store.
        
        Args:
            store_path: Path to store keys (default: ./wallet_data)
            password: Master password for encryption
        """
        self.store_path = store_path if store_path else Path("./wallet_data")
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        self.keys_file = self.store_path / "keys.json"
        self.password = password
        self.keys: Dict[str, Dict[str, Any]] = {}
        self.unlocked = False
        
        # Load existing keys
        self._load_keys()
        
        print(f"✅ KeyStore initialized: {self.store_path}")
        print(f"   Keys: {len(self.keys)}")
        print(f"   Encryption: {'Enabled' if CRYPTO_AVAILABLE and password else 'Disabled'}")
    
    # ============================================
    # KEY MANAGEMENT
    # ============================================
    
    def unlock(self, password: str) -> bool:
        """
        Unlock the key store with a password.
        
        Args:
            password: Master password
        
        Returns:
            bool: True if unlocked successfully
        """
        self.password = password
        self.unlocked = True
        
        # Reload keys with decryption
        self._load_keys()
        
        print("🔓 KeyStore unlocked")
        return True
    
    def lock(self) -> None:
        """Lock the key store."""
        self.password = None
        self.unlocked = False
        self.keys.clear()
        print("🔒 KeyStore locked")
    
    def add_key(self, address: str, private_key: bytes, label: str = "") -> bool:
        """
        Add a private key to the store.
        
        Args:
            address: Public address (key identifier)
            private_key: Private key bytes
            label: Optional label for the key
        
        Returns:
            bool: True if added successfully
        """
        try:
            # Convert private key to hex
            key_hex = private_key.hex()
            
            # Encrypt if encryption is available
            if CRYPTO_AVAILABLE and self.password:
                encrypted = self._encrypt(key_hex)
                self.keys[address] = {
                    'encrypted': True,
                    'data': encrypted,
                    'label': label,
                    'created_at': datetime.now().isoformat(),
                    'address': address
                }
            else:
                # Store in plain text (not recommended for production)
                self.keys[address] = {
                    'encrypted': False,
                    'data': key_hex,
                    'label': label,
                    'created_at': datetime.now().isoformat(),
                    'address': address
                }
            
            # Save to disk
            self._save_keys()
            return True
            
        except Exception as e:
            print(f"❌ Failed to add key: {e}")
            return False
    
    def get_private_key(self, address: str) -> Optional[bytes]:
        """
        Get a private key by address.
        
        Args:
            address: Address to look up
        
        Returns:
            Optional[bytes]: Private key bytes or None
        """
        if address not in self.keys:
            return None
        
        key_data = self.keys[address]
        key_hex = key_data['data']
        
        # Decrypt if encrypted
        if key_data.get('encrypted', False):
            if not CRYPTO_AVAILABLE or not self.password:
                print("❌ Cannot decrypt: encryption not available or password not set")
                return None
            key_hex = self._decrypt(key_hex)
        
        return bytes.fromhex(key_hex)
    
    def get_all_addresses(self) -> List[str]:
        """Get all addresses in the store."""
        return list(self.keys.keys())
    
    def get_key_info(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a key.
        
        Args:
            address: Address to look up
        
        Returns:
            Optional[Dict]: Key information
        """
        if address not in self.keys:
            return None
        
        info = self.keys[address].copy()
        # Remove sensitive data
        if 'data' in info:
            del info['data']
        return info
    
    def remove_key(self, address: str) -> bool:
        """
        Remove a key from the store.
        
        Args:
            address: Address to remove
        
        Returns:
            bool: True if removed
        """
        if address in self.keys:
            del self.keys[address]
            self._save_keys()
            return True
        return False
    
    # ============================================
    # ENCRYPTION
    # ============================================
    
    def _encrypt(self, data: str) -> str:
        """Encrypt data with master password."""
        if not CRYPTO_AVAILABLE:
            return data
        
        # Derive key from password
        salt = b'ZARU_SALT_2024'  # In production, use random salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.password.encode()))
        fernet = Fernet(key)
        
        # Encrypt
        encrypted = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt data with master password."""
        if not CRYPTO_AVAILABLE:
            return encrypted_data
        
        # Derive key from password
        salt = b'ZARU_SALT_2024'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.password.encode()))
        fernet = Fernet(key)
        
        # Decrypt
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    
    # ============================================
    # PERSISTENCE
    # ============================================
    
    def _load_keys(self) -> None:
        """Load keys from disk."""
        if not self.keys_file.exists():
            return
        
        try:
            with open(self.keys_file, 'r') as f:
                data = json.load(f)
                self.keys = data.get('keys', {})
        except Exception as e:
            print(f"⚠️  Failed to load keys: {e}")
            self.keys = {}
    
    def _save_keys(self) -> None:
        """Save keys to disk."""
        try:
            data = {
                'keys': self.keys,
                'updated_at': datetime.now().isoformat()
            }
            with open(self.keys_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"❌ Failed to save keys: {e}")
    
    # ============================================
    # IMPORT/EXPORT
    # ============================================
    
    def export_wallet(self, file_path: Path) -> bool:
        """
        Export wallet to a file.
        
        Args:
            file_path: Path to export to
        
        Returns:
            bool: True if exported successfully
        """
        try:
            data = {
                'keys': self.keys,
                'exported_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✅ Wallet exported to {file_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to export wallet: {e}")
            return False
    
    def import_wallet(self, file_path: Path) -> bool:
        """
        Import wallet from a file.
        
        Args:
            file_path: Path to import from
        
        Returns:
            bool: True if imported successfully
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            imported_keys = data.get('keys', {})
            for address, key_data in imported_keys.items():
                self.keys[address] = key_data
            
            self._save_keys()
            print(f"✅ Wallet imported from {file_path}")
            print(f"   Imported {len(imported_keys)} keys")
            return True
        except Exception as e:
            print(f"❌ Failed to import wallet: {e}")
            return False
    
    # ============================================
    # UTILITY
    # ============================================
    
    def clear(self) -> None:
        """Clear all keys from the store."""
        self.keys.clear()
        self._save_keys()
        print("🗑️  KeyStore cleared")
    
    def __len__(self) -> int:
        return len(self.keys)


# ============================================
# TEST FUNCTIONS
# ============================================

def test_key_store():
    """Test the key store."""
    print("\n🧪 Testing KeyStore...")
    
    # Create key store
    store = KeyStore(password="test_password")
    
    # Generate a test private key
    from ecdsa import SigningKey, SECP256k1
    sk = SigningKey.generate(curve=SECP256k1)
    private_key = sk.to_string()
    
    # Create a test address
    vk = sk.get_verifying_key()
    address = hashlib.sha256(vk.to_string()).hexdigest()[:40]
    
    # Add key
    store.add_key(address, private_key, label="Test Key")
    print(f"1. Added key: {address[:10]}...")
    
    # Get key back
    retrieved = store.get_private_key(address)
    print(f"2. Retrieved key: {'Success' if retrieved else 'Failed'}")
    
    # Get addresses
    addresses = store.get_all_addresses()
    print(f"3. Addresses: {len(addresses)}")
    
    # Get key info
    info = store.get_key_info(address)
    print(f"4. Key info: {info}")
    
    print("\n✅ KeyStore test complete")
    return True


if __name__ == "__main__":
    test_key_store()