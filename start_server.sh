#!/bin/bash
# Start script for iMessage Bridge Server
# Run this on your Mac that has iMessage running

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3."
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Verify dependencies are installed
if ! python3 -c "import dotenv" 2>/dev/null; then
    echo "Error: Dependencies not installed properly. Installing now..."
    pip install -r requirements.txt
fi

# Get the local IP address
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")

echo ""
echo "=========================================="
echo "iMessage Bridge Server Starting..."
echo "=========================================="
echo ""
echo "Local access: http://localhost:8765"
echo "Network access: http://${LOCAL_IP}:8765"
echo ""
echo "WebSocket: ws://${LOCAL_IP}:8765/ws"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Run the server (use python from venv)
python -m src.http_server

