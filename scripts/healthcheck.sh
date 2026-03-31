#!/bin/bash
# ChuckAI Stack Health Check
# Checks all services and reports status

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}OK${NC} — $1"; }
fail() { echo -e "  ${RED}FAIL${NC} — $1"; }
warn() { echo -e "  ${YELLOW}WARN${NC} — $1"; }

echo "========================================"
echo " ChuckAI Stack Health Check"
echo " $(date)"
echo "========================================"
echo

# 1. llama.cpp
echo "--- llama-server (port 8080) ---"
HEALTH=$(curl -s --max-time 5 http://localhost:8080/health 2>/dev/null) && {
  STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "$HEALTH")
  pass "status: $STATUS"
  MODEL=$(curl -s --max-time 5 http://localhost:8080/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null) && pass "model: $MODEL" || warn "could not query model name"
} || fail "llama-server not responding"
echo

# 2. Open WebUI
echo "--- Open WebUI (port 3000) ---"
VERSION=$(curl -s --max-time 5 http://localhost:3000/api/version 2>/dev/null) && {
  VER=$(echo "$VERSION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','unknown'))" 2>/dev/null || echo "$VERSION")
  pass "version: $VER"
} || fail "Open WebUI not responding"
echo

# 3. SearXNG
echo "--- SearXNG (port 8081) ---"
SEARCH=$(curl -s --max-time 10 "http://localhost:8081/search?q=test&format=json" 2>/dev/null) && {
  COUNT=$(echo "$SEARCH" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('results',[])))" 2>/dev/null || echo "?")
  pass "responding — $COUNT results for test query"
} || fail "SearXNG not responding"
echo

# 4. Docker containers
echo "--- Docker Compose ---"
if command -v docker &>/dev/null; then
  docker compose ps 2>/dev/null || docker-compose ps 2>/dev/null || warn "docker compose not available"
else
  fail "docker not found"
fi
echo

# 5. GPU
echo "--- GPU (ROCm) ---"
if command -v rocm-smi &>/dev/null; then
  rocm-smi --showuse --showtemp --showmemuse 2>/dev/null || rocm-smi 2>/dev/null || warn "rocm-smi error"
else
  warn "rocm-smi not found"
fi
echo

echo "========================================"
echo " Health check complete"
echo "========================================"
