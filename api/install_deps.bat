@echo off
echo ============================================
echo Installing ZARU Dependencies
echo ============================================

echo.
echo Installing Core Dependencies...
pip install fastapi uvicorn[standard] pydantic pydantic-settings python-multipart

echo.
echo Installing Cryptography...
pip install ecdsa cryptography

echo.
echo Installing Networking...
pip install websockets

echo.
echo Installing System Utilities...
pip install python-dotenv colorama click schedule psutil

echo.
echo Installing Monitoring...
pip install prometheus-client structlog

echo.
echo Installing Testing...
pip install pytest pytest-asyncio pytest-cov

echo.
echo Installing Development Tools...
pip install black mypy ruff

echo.
echo ============================================
echo Installation Complete!
echo ============================================
echo.
echo To verify installations, run:
echo   python -c "import fastapi; print('✅ FastAPI')"
echo.

pause