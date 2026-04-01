#!/bin/bash
# Prime cold services after reboot: Ollama embeddings + Qdrant HNSW indexes
# Run after docker compose up -d and llama-server are ready

echo "Warming up services..."

# Ollama embedding model — first call loads model into memory
printf "  Ollama embed... "
t=$(date +%s%N)
curl -sf http://localhost:11434/api/embed \
  -d '{"model":"nomic-embed-text","input":"warmup"}' > /dev/null 2>&1
ms=$(( ($(date +%s%N) - t) / 1000000 ))
echo "${ms} ms"

# Qdrant — touch both collections to load HNSW indexes from disk
for col in docs_hot docs_cold; do
  printf "  Qdrant $col... "
  t=$(date +%s%N)
  curl -sf "http://localhost:6333/collections/${col}/points/query" \
    -H "Content-Type: application/json" \
    -d '{"query":[0.0],"using":"dense","limit":1}' > /dev/null 2>&1
  ms=$(( ($(date +%s%N) - t) / 1000000 ))
  echo "${ms} ms"
done

# llama-server — small prompt to warm KV cache allocation
printf "  llama-server... "
t=$(date +%s%N)
curl -sf http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-active.gguf","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' > /dev/null 2>&1
ms=$(( ($(date +%s%N) - t) / 1000000 ))
echo "${ms} ms"

echo "Warmup complete."
