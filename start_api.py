#!/usr/bin/env python
"""
ZARU API Startup Wrapper
=======================
This wrapper captures and logs any startup errors.
WHY: Render doesn't show Python errors, so we need to log them.
"""

import sys
import os
import traceback
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Start the API with error handling."""
    try:
        logger.info("=" * 60)
        logger.info("🚀 Starting ZARU API...")
        logger.info("=" * 60)
        logger.info(f"   Python version: {sys.version}")
        logger.info(f"   Working directory: {os.getcwd()}")
        logger.info(f"   Files in directory: {os.listdir('.')[:20]}...")
        
        # Check for critical files
        critical_files = ['config.py', 'api', 'blockchain', 'database']
        for f in critical_files:
            if os.path.exists(f):
                logger.info(f"   ✅ Found: {f}")
            else:
                logger.error(f"   ❌ Missing: {f}")
        
        # Import the app
        logger.info("📦 Importing api.main...")
        from api.main import app
        logger.info("✅ App imported successfully!")
        
        # Import uvicorn
        logger.info("📦 Importing uvicorn...")
        import uvicorn
        logger.info("✅ Uvicorn imported successfully!")
        
        # Get port from environment
        port = int(os.getenv("PORT", 8332))
        logger.info(f"🔌 Using port: {port}")
        logger.info(f"🔌 Render PORT: {os.getenv('PORT', 'Not set')}")
        
        # Log environment variables (non-sensitive)
        env_vars = ['DATABASE_URL', 'ZARU_TESTNET', 'LOG_LEVEL']
        for var in env_vars:
            if os.getenv(var):
                logger.info(f"   {var}: {os.getenv(var)[:30]}...")
        
        # Run the server
        logger.info("=" * 60)
        logger.info(f"🚀 Starting server on port {port}...")
        logger.info("=" * 60)
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Startup failed: {e}")
        logger.error("=" * 60)
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Error message: {str(e)}")
        logger.error("❌ Full traceback:")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()