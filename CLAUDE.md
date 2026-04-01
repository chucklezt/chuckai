# CLAUDE.md — ChuckAI Private AI Server

This file is read automatically by Claude Code at the start of every session. It contains everything you need to work safely and effectively in this repository.

---

## Project Overview

ChuckAI is a self-hosted, GPU-accelerated AI inference and RAG (Retrieval-Augmented Generation) stack running on bare metal Ubuntu 22.04. It is designed and operated by Chuck Tsocanos — technology executive, AI strategist, and cloud transformation leader. This project serves two purposes: a working personal AI infrastructure and a portfolio demonstration of sovereign AI architecture for enterprise consulting conversations.

The stack is intentionally positioned as the on-premises counterpart to the GCP-native enterprise RAG system in the `enterprise-rag-gcp` repository. Together they demonstrate the full enterprise decision space: cloud-native scale vs. data-sovereign private inference.

---

## Hardware

| Component | Spec |
|---|---|
| Hostname | chuckai |
| IP | 192.168.1.59 (static) |
| User | chuck |
| CPU | Intel i7-10700 — 8C/16T |
| GPU | AMD RX 6800 XT — 16GB GDDR6 (RDNA 2, gfx1030) |
| RAM | 64GB DDR4 |
| Storage | 4TB NVMe SSD |
| OS | Ubuntu 22.04.5 LTS (Jammy) |

---

## Confirmed Software Versions (March 2026)

| Component | Version |
|---|---|
| llama.cpp | build 8454 (fb78ad29b) |
| Open WebUI | v0.8.12 (via :latest tag — see backup/rollback section) |
| SearXNG | 2026.3.18-3810dc9d1 |
| Docker CE | 29.3.0 |
| Docker Compose | v5.1.0 |
| Ollama | 0.18.2 (installed, NOT running — reserved for RAG) |
| ROCm SMI | 3.0.0+55c0f58 |
| Python | 3.10.12 |
| Ubuntu | 22.04.5 LTS |

---

## Repository Structure

```
chuckai/
├── CLAUDE.md                   # This file — read by Claude Code automatically
├── README.md                   # Public-facing project documentation
├── .gitignore                  # Excludes models, logs, vector DB data
├── configs/                    # All service configuration files
│   ├── docker-compose.yml      # Open WebUI (latest/v0.8.12) + SearXNG — the working compose file
│   ├── start-llama-qwe359.sh   # llama-server startup — Qwen 3.5 9B Q4
│   ├── start-llama-27b.sh      # llama-server startup — Qwen 3.5 27B Q3 (custom quant)
│   └── searxng-settings.yml    # SearXNG configuration
├── ingest/                     # Phase 2 — RAG ingestion service (in development)
│   ├── requirements.txt
│   ├── watcher.py              # inotify watchdog for /mnt/documents/
│   ├── extractor.py            # Apache Tika wrapper + EPUB handler
│   ├── chunker.py              # RecursiveCharacterTextSplitter
│   ├── bm25_vectorizer.py      # Sparse BM25 token weights
│   └── embedder.py             # Dense + sparse upsert to Qdrant
├── pipelines/                  # Open WebUI pipeline plugins
│   ├── rag_pipeline.py         # Hybrid BM25 + semantic RAG retrieval
│   └── doc_output_pipeline.py  # DOCX/PPTX/PDF output generation
├── scripts/                    # Utility and maintenance scripts
│   └── healthcheck.sh          # Full stack health check
└── docs/                       # Architecture and reference documentation
```

---

## Current Working State

### Phase 1 — COMPLETE ✓

The following is fully working and validated:

- **llama.cpp** serving Qwen 3.5 9B Q4_K_M on port 8080 via RX 6800 XT (ROCm)
- **Open WebUI** v0.8.12 on port 3000 — chat, conversation history, model switching
- **SearXNG** on port 8081 — web-augmented responses via globe icon in chat
- **Web search** configured via Admin Panel UI (not env vars)
- **Model switching** between 9B and 27B via separate startup scripts

### Phase 2 — IN DEVELOPMENT

- Qdrant vector database (port 6333)
- Apache Tika document parsing (port 9998)
- Ollama embeddings via nomic-embed-text (port 11434, CPU only)
- Python ingestion service with file watcher
- Hybrid BM25 + semantic search with RRF fusion
- EPUB support via ebooklib + BeautifulSoup4
- Tiered collections: docs_hot + docs_cold

### Phase 3 — PLANNED

- Open WebUI Pipelines (port 9099)
- Pandoc + LibreOffice for DOCX/PPTX/PDF output generation

---

## Port Map

| Port | Service | Status |
|---|---|---|
| 8080 | llama-server (OpenAI API + health) | Active |
| 3000 | Open WebUI | Active |
| 8081 | SearXNG | Active |
| 11434 | Ollama (embeddings only) | Installed, not running |
| 6333 | Qdrant REST | Phase 2 |
| 6334 | Qdrant gRPC | Phase 2 |
| 9998 | Apache Tika | Phase 2 |
| 9099 | Open WebUI Pipelines | Phase 3 |

---

## Critical Rules — Read Before Making Any Changes

These rules exist because we learned them the hard way. Breaking them will cost hours of debugging.

### 1. Open WebUI upgrade/rollback procedure
Open WebUI was upgraded from v0.5.20 to v0.8.12 on 2026-04-01. The `:latest` tag is now used in docker-compose. Before upgrading, backups were created:

**Backups available:**
- **v0.5.20 container image:** `open-webui-backup:v0.5.20` (local Docker image)
- **v0.5.20 data:** `~/open-webui-backup-v0.5.20/data/` (contains webui.db, cache, uploads, vector_db)
- **v0.8.12 container image:** `open-webui-backup:v0.8.12` (local Docker image)
- **Persistent data volume:** `chuck_open-webui` (named Docker volume, survives container recreation)

**To roll back to v0.5.20:**
```bash
# 1. Stop current container
cd ~ && docker compose down

# 2. Update docker-compose.yml to use the backup image
#    Change: image: ghcr.io/open-webui/open-webui:latest
#    To:     image: open-webui-backup:v0.5.20

# 3. Restore the v0.5.20 data backup
docker run --rm -v chuck_open-webui:/data -v ~/open-webui-backup-v0.5.20/data:/backup alpine \
  sh -c "rm -rf /data/* && cp -a /backup/. /data/"

# 4. Start with old version
docker compose up -d
```

**Note:** The earlier v0.5.20 pinning was due to streaming bugs in 0.6.x with llama.cpp. v0.8.12 resolved these issues. If a future `:latest` pull introduces regressions, pin to `v0.8.12` using the backup image or the registry tag.

### 2. Always use OPENAI_API_BASE_URL, never OLLAMA_BASE_URL
Open WebUI connects to llama.cpp via the OpenAI-compatible `/v1` endpoint. Using `OLLAMA_BASE_URL` causes Open WebUI to operate in Ollama mode which appends `:latest` to every model name, causing "model not found" errors.

### 3. llama.cpp requires --jinja and -rea off for Qwen 3.5
Qwen 3.5 outputs `<think>...</think>` reasoning blocks by default. These break Open WebUI's JSON stream parser. The `-rea off` flag disables thinking mode. It only works when `--jinja` is also present. `--reasoning-format none` alone does NOT work — we verified this across multiple llama.cpp builds.

### 4. SearXNG must use port mapping, not network_mode: host
SearXNG always binds internally to port 8080 regardless of settings.yml. Use `ports: "8081:8080"` in docker-compose. Do not use `network_mode: host` for SearXNG — it will collide with llama-server on 8080.

### 5. Web search must be configured via Admin Panel UI
Do NOT add `ENABLE_RAG_WEB_SEARCH`, `SEARXNG_QUERY_URL`, or related env vars to docker-compose. These caused the model to hang in v0.5.20 and should still be configured through Admin Panel → Settings → Web Search to avoid regressions.

### 6. SearXNG settings.yml requires a secret_key
SearXNG crashes on startup without `secret_key` set in settings.yml. The `json` format must also be in the formats list or Open WebUI cannot parse search results.

### 7. Always check running services before modifying configs
Before editing any config file, confirm what's running:
```bash
docker compose ps
pgrep -fa llama-server
curl -s http://localhost:8080/health
```
Never restart docker-compose without checking that llama-server is still running first — they are independent processes.

### 8. Model files are never committed to git
The `.gitignore` excludes `*.gguf` files. Models live at `~/models/` and are never tracked. Do not attempt to add them.

### 9. HSA_OVERRIDE_GFX_VERSION=10.3.0 is always required
This environment variable must be set before every llama-server launch. Without it, ROCm may not correctly identify the RX 6800 XT (gfx1030) and falls back to CPU inference silently.

---

## Key Commands

### Start everything (after reboot)
```bash
# 1. Start llama.cpp
bash ~/start-llama-qwe359.sh &
sleep 15 && curl -s http://localhost:8080/health

# 2. Start Docker services
cd ~ && docker compose up -d
```

### Switch models
```bash
# Switch to 27B
pkill -9 llama-server && sleep 3 && bash ~/start-llama-27b.sh &

# Switch back to 9B
pkill -9 llama-server && sleep 3 && bash ~/start-llama-qwe359.sh &

# Check which model is loaded
curl -s http://localhost:8080/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"
```

### Convenience aliases (in ~/.bashrc)
```bash
alias model-9b='pkill -9 llama-server; sleep 3; bash ~/start-llama-qwe359.sh & echo "Starting 9B..."'
alias model-27b='pkill -9 llama-server; sleep 3; bash ~/start-llama-27b.sh & echo "Starting 27B..."'
alias model-status='curl -s http://localhost:8080/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)[\"data\"][0][\"id\"])"'
```

### Full stack health check
```bash
bash ~/chuckai/scripts/healthcheck.sh
```

### Docker management
```bash
docker compose up -d              # start all containers
docker compose down               # stop all containers
docker compose ps                 # check status
docker logs open-webui            # Open WebUI logs
docker logs searxng               # SearXNG logs
```

### GPU monitoring
```bash
rocm-smi                          # current GPU state
watch -n 1 rocm-smi               # live refresh
```

---

## VRAM Reference

| Config | Model | KV Cache | Context | Total VRAM | Headroom |
|---|---|---|---|---|---|
| A — Current | Q4_K_M | q4_0 | 128K | 10.65 GB | 5.35 GB |
| B — Will spill | Q6_K | q8_0 | 128K | 15.95 GB | ~0 GB |
| C — Recommended | Q6_K | q8_0 | 32K | 8.70 GB | 7.30 GB |

Config C uses a better model and higher KV precision than Config A at lower VRAM — achieved by reducing context from 128K to 32K.

---

## llama.cpp Build Instructions

If you need to rebuild llama.cpp from source (e.g. after a git pull):

```bash
cd ~/llama.cpp
git pull
cmake -B build \
  -DGGML_HIP=ON \
  -DAMDGPU_TARGETS="gfx1030" \
  -DCMAKE_PREFIX_PATH="/opt/rocm/lib/cmake/hip;/opt/rocm/lib/cmake/hip-lang;/opt/rocm" \
  -DCMAKE_HIP_FLAGS="--gcc-toolchain=/usr/lib/gcc/x86_64-linux-gnu/11 \
    -I/usr/include/c++/11 \
    -I/usr/include/x86_64-linux-gnu/c++/11 \
    -L/usr/lib/gcc/x86_64-linux-gnu/11 \
    -L/usr/lib/x86_64-linux-gnu" \
  -DCMAKE_EXE_LINKER_FLAGS="-L/usr/lib/gcc/x86_64-linux-gnu/11 \
    -L/usr/lib/x86_64-linux-gnu -lstdc++ -lgcc_s"
cmake --build build --config Release -j$(nproc)
```

**Critical flag:** Use `-DGGML_HIP=ON` not `-DGGML_ROCM=ON`. The wrong flag causes a silent CPU-only fallback.

Verify GPU is detected before trusting the build:
```bash
./build/bin/llama-server --version 2>&1 | head -3
# Must show: found 1 ROCm devices: AMD Radeon RX 6800 XT, gfx1030
```

---

## Phase 2 RAG — Design Reference

When implementing Phase 2, follow these design decisions:

**Vector DB:** Qdrant with on-disk HNSW — required for 2-3TB corpus (~75-150M vectors). Configure `hnsw_index.on_disk: true` and `storage.on_disk_payload: true` from day one. Do not attempt in-memory indexing at this scale.

**Embeddings:** Ollama running `nomic-embed-text` on CPU (port 11434). This runs independently of Qwen on the GPU — no VRAM competition. 768-dim vectors, ~80ms per chunk on the i7.

**Search strategy:** Hybrid BM25 sparse + semantic dense with Reciprocal Rank Fusion (RRF). Pure semantic search misses exact-match queries on technical documents. Both vector types stored in the same Qdrant collection.

**Tiered collections:**
- `docs_hot` — priority documents, queried first
- `docs_cold` — full archive, queried only as fallback when hot tier returns < 3 results

**EPUB handling:** Route `.epub` files through `ebooklib` + `BeautifulSoup4`, NOT Tika. Tika flattens EPUBs into a single blob. ebooklib extracts per-chapter with title/author/chapter metadata. Install: `pip install ebooklib==0.18 beautifulsoup4==4.12.3`

**Document ingestion:** SFTP from Mac via Finder (`sftp://chuck@192.168.1.59`) or Cyberduck. Drop files to `/mnt/documents/inbox_priority/` (hot tier) or `/mnt/documents/inbox/` (cold tier).

**Abstraction principle:** Implement embeddings, vector store, and LLM calls behind simple interfaces from the start. This makes porting to GCP (Vertex AI embeddings, Vertex AI Vector Search, Gemini) a module swap rather than a rewrite.

---

## Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---|---|---|
| "Expecting value: line 1 column 1" | Qwen think tags in stream | Confirm `-rea off` and `--jinja` in startup script |
| "Model not found :latest" | OLLAMA_BASE_URL set | Use OPENAI_API_BASE_URL=http://localhost:8080/v1 |
| "Open WebUI Backend Required" | Browser cache mismatch | Cmd+Shift+R or open private window |
| SearXNG crashes immediately | Missing secret_key | Add secret_key to ~/searxng/settings.yml |
| Globe icon not visible | Web search not enabled | Admin Panel → Settings → Web Search → ON → Save |
| Web search hangs, no response | Web search env vars set | Remove from docker-compose, configure via UI only |
| GPU not detected | Missing HSA override | Export HSA_OVERRIDE_GFX_VERSION=10.3.0 |
| llama.cpp falls back to CPU | Wrong cmake flag | Use -DGGML_HIP=ON not -DGGML_ROCM=ON |
| Static IP reverts on reboot | cloud-init overwriting netplan | Add network: {config: disabled} to cloud-init config |
| Only 100GB disk visible | LVM not extended | sudo lvextend -l +100%FREE then resize2fs |
