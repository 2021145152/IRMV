#!/bin/bash
# Ontology Server Startup Script
# Starts server and loads data in sequence

set -e  # Exit on error

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "================================================"
echo -e "${BLUE}Ontology Server Startup${NC}"
echo "================================================"
echo ""

# Clear Python cache to ensure fresh code
echo -e "${YELLOW}Clearing Python cache...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo -e "${GREEN}  Python cache cleared${NC}"
echo ""

# Kill existing servers first
echo -e "${YELLOW}Checking for existing servers...${NC}"
if pgrep -f "run_server.py" > /dev/null; then
    echo "  Found existing server processes. Killing..."
    pkill -9 -f "run_server.py" || true
    pkill -9 -f "uvicorn.*ontology_server" || true
    sleep 3
    echo -e "${GREEN}  Killed existing servers${NC}"
else
    echo "  No existing servers found"
fi
echo ""

# 1. Start server (in background)
echo -e "${GREEN}[1/3] Starting server...${NC}"
# Set PYTHONPATH to include project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
PYTHONDONTWRITEBYTECODE=1 python3 cli/run_server.py &
SERVER_PID=$!
echo "Server started (PID: $SERVER_PID)"
echo ""

# Wait for server to be ready (poll health endpoint)
echo "Waiting for server to be ready..."
MAX_WAIT=30
ELAPSED=0
SERVER_PORT=8000
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:${SERVER_PORT}/health > /dev/null 2>&1; then
        echo "Server is ready!"
        break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    echo -n "."
done
echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo -e "${YELLOW}Warning: Server did not start within ${MAX_WAIT}s${NC}"
    kill $SERVER_PID
    exit 1
fi

# 2. Load static data
echo -e "${GREEN}[2/3] Loading static data...${NC}"
python3 cli/load_static.py
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Warning: Static data load failed${NC}"
    kill $SERVER_PID
    exit 1
fi
echo ""

# 3. Load dynamic data
echo -e "${GREEN}[3/3] Loading dynamic data...${NC}"
python3 cli/load_dynamic.py
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Warning: Dynamic data load failed${NC}"
    kill $SERVER_PID
    exit 1
fi
echo ""

echo "================================================"
echo -e "${GREEN}All systems ready!${NC}"
echo "Server running on PID: $SERVER_PID"
echo "Press Ctrl+C to stop"
echo "================================================"

# Wait for server process
wait $SERVER_PID
