#!/usr/bin/env python
"""
Test import script to debug API loading issues.
"""
import sys
import os
import traceback

print("=" * 60)
print("🔍 Testing ZARU API Imports")
print("=" * 60)

# Step 1: Test config
try:
    print("1. Testing config...")
    from config import settings
    print(f"   ✅ Config loaded: API_PORT={settings.API_PORT}")
except Exception as e:
    print(f"   ❌ Config failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 2: Test database
try:
    print("2. Testing database...")
    from database import store
    print(f"   ✅ Database loaded: {type(store).__name__}")
except Exception as e:
    print(f"   ❌ Database failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 3: Test blockchain
try:
    print("3. Testing blockchain...")
    from blockchain.chain_manager import chain_manager
    print(f"   ✅ Blockchain loaded: height={chain_manager.get_height()}")
except Exception as e:
    print(f"   ❌ Blockchain failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 4: Test mempool
try:
    print("4. Testing mempool...")
    from mempool import mempool
    print(f"   ✅ Mempool loaded: size={mempool.get_mempool_size()}")
except Exception as e:
    print(f"   ❌ Mempool failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 5: Test wallet
try:
    print("5. Testing wallet...")
    from wallet import wallet
    print(f"   ✅ Wallet loaded")
except Exception as e:
    print(f"   ❌ Wallet failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 6: Test api.main
try:
    print("6. Testing api.main...")
    from api.main import app
    print(f"   ✅ API main loaded: app={app}")
except Exception as e:
    print(f"   ❌ API main failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("✅ ALL IMPORTS SUCCESSFUL!")
print("=" * 60)