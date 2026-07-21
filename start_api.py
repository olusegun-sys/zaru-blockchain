#!/usr/bin/env python
"""
ZARU API Startup Wrapper - With Full Error Logging
"""
import sys
import os
import traceback
import logging

# Force flush prints
sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
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
        
        # Check critical files
        critical_files = ['config.py', 'api', 'blockchain', 'database']
        for f in critical_files:
            if os.path.exists(f):
                logger.info(f"   ✅ Found: {f}")
            else:
                logger.error(f"   ❌ Missing: {f}")
                sys.exit(1)
        
        # Try importing with detailed error
        logger.info("📦 Importing api.main...")
        try:
            import api.main
            from api.main import app
            logger.info("✅ App imported successfully!")
        except ImportError as e:
            logger.error(f"❌ ImportError: {e}")
            logger.error(f"❌ Full traceback:\n{traceback.format_exc()}")
            # Try to find which module is failing
            logger.info("🔍 Attempting to debug import...")
            import importlib
            for module in ['config', 'database', 'blockchain', 'mempool', 'wallet', 'miner', 'network']:
                try:
                    importlib.import_module(module)
                    logger.info(f"   ✅ {module} imported")
                except Exception as e2:
                    logger.error(f"   ❌ {module} failed: {e2}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Error importing app: {e}")
            logger.error(f"❌ Full traceback:\n{traceback.format_exc()}")
            sys.exit(1)
        
        # Get port
        port = int(os.getenv("PORT", 8332))
        logger.info(f"🔌 Using port: {port}")
        
        # Run server
        logger.info("=" * 60)
        logger.info(f"🚀 Starting server on port {port}...")
        logger.info("=" * 60)
        
        import uvicorn
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="debug",
            access_log=True
        )
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ Startup failed: {e}")
        logger.error("=" * 60)
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()