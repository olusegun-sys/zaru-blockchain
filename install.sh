#!/bin/bash
# ZARU Render Build Script - Python 3.12

echo "🔧 Installing ZARU dependencies..."

# Set Python version explicitly
export PYTHON_VERSION=3.12

# Upgrade pip
pip install --upgrade pip

# Install with no cache
pip install --no-cache-dir -r requirements.txt

# Verify critical packages
echo "✅ Verifying installations..."
python -c "import fastapi; print('FastAPI:', fastapi.__version__)"
python -c "import pydantic; print('Pydantic:', pydantic.__version__)"
python -c "import ecdsa; print('ECDSA:', ecdsa.__version__)"
python -c "import psycopg2; print('Psycopg2 installed')"

echo "✅ Installation complete!"