#!/bin/bash
# Full ChuckAI stack startup — run manually after reboot
# Sequences services in dependency order with health checks between stages

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[startup]${NC} $1"; }
warn() { echo -e "${YELLOW}[startup]${NC} $1"; }
fail() { echo -e "${RED}[startup]${NC} $1"; exit 1; }

wait_for() {
  local name="$1" url="$2" max="$3"
  local i=0
  while [ $i -lt $max ]; do
    if curl -sf "$url" > /dev/null 2>&1; then
      log "$name is ready"
      return 0
    fi
    sleep 2
    i=$((i + 2))
  done
  fail "$name did not respond after ${max}s — aborting"
}

wait_for_pipelines() {
  local max="$1" i=0
  while [ $i -lt $max ]; do
    if curl -sf -H "Authorization: Bearer 0p3n-w3bu!" http://localhost:9099/models > /dev/null 2>&1; then
      log "Pipelines is ready"
      return 0
    fi
    sleep 2
    i=$((i + 2))
  done
  fail "Pipelines did not respond after ${max}s — aborting"
}

# ── Step 1: Kill existing services ──
if pgrep -f llama-server > /dev/null; then
  log "Killing existing llama-server..."
  pkill -9 -f llama-server
  sleep 2
fi

log "Stopping Docker services..."
cd /home/chuck && docker compose down
sleep 2

log "Restarting Ollama..."
sudo systemctl restart ollama
sleep 2
wait_for "Ollama" "http://localhost:11434/api/version" 30

# ── Step 2: llama-server ──
log "Starting llama-server..."
bash ~/start-llama-qwen.sh &
sleep 2
wait_for "llama-server" "http://localhost:8080/health" 60

# ── Step 3: Infrastructure services (Qdrant, Tika, SearXNG) ──
log "Starting infrastructure services..."
cd /home/chuck && docker compose up -d qdrant tika searxng
sleep 3

wait_for "Qdrant" "http://localhost:6333/healthz" 30
wait_for "Tika" "http://localhost:9998/tika" 30
wait_for "SearXNG" "http://localhost:8081" 30

# ── Step 4: Pipelines (needs Ollama + Qdrant) ──
log "Starting Pipelines..."
cd /home/chuck && docker compose up -d pipelines
sleep 3
wait_for_pipelines 30

# ── Step 5: Open WebUI (needs Pipelines for filter discovery) ──
log "Starting Open WebUI..."
cd /home/chuck && docker compose up -d open-webui
sleep 3
wait_for "Open WebUI" "http://localhost:3000" 30

# ── Step 6: Warmup — prime cold caches ──
log "Warming up Ollama embeddings..."
curl -sf http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text:v1.5","input":"warmup"}' > /dev/null 2>&1
log "Ollama embed warm"

log "Warming up Qdrant indexes..."
for col in docs_hot docs_cold; do
  curl -sf "http://localhost:6333/collections/${col}/points/query" \
    -H "Content-Type: application/json" \
    -d '{"query":[0.0],"using":"dense","limit":1}' > /dev/null 2>&1
done
log "Qdrant indexes loaded"

log "Warming up llama-server..."
curl -sf http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-active.gguf","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' > /dev/null 2>&1
log "llama-server warm"

# ── Done ──
echo ""
log "Stack is ready. Open http://192.168.1.59:3000"
