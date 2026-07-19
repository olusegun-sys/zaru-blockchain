#!/bin/bash
# ZARU Render Build Script
# Installs all dependencies for production

echo "🔧 Installing ZARU dependencies..."
pip install --upgrade pip

# Install production dependencies
echo "📦 Installing production packages..."
pip install -r requirements.txt

# Verify critical packages
echo "✅ Verifying installations..."
python -c "import fastapi; print('FastAPI:', fastapi.__version__)"
python -c "import uvicorn; print('Uvicorn:', uvicorn.__version__)"
python -c "import ecdsa; print('ECDSA:', ecdsa.__version__)"
python -c "import psycopg2; print('Psycopg2 installed')"

echo "✅ Installation complete!"