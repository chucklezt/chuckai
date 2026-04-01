# ChuckAI — Private AI Infrastructure

**A production-grade, self-hosted AI inference and RAG stack running on bare metal Ubuntu 22.04 with AMD GPU acceleration. Zero cloud dependency. Zero per-token cost. Full data sovereignty.**

> Designed and built by [Chuck Tsocanos](https://chucktsocanos.com) — Technology Executive, AI Strategist, Cloud Transformation Leader.

---

## Why Build This?

The case for a private AI server is strategic as much as technical. Every prompt sent to a cloud provider contributes intellectual work to someone else's training pipeline, incurs per-token cost, and accepts a rate limit on your own thinking. From an enterprise AI strategy perspective, the data sovereignty argument alone is compelling — add zero marginal cost inference, sub-100ms local latency, and the ability to run specialized models without asking permission, and the economics become hard to ignore.

This project, as outlined in [this blog post](https://chucktsocanos.com/#blog/building-private-ai-server-part1), is the on-premises counterpart to the [enterprise-rag-gcp](https://github.com/chucklezt/enterprise-rag-gcp) repository, which implements the same RAG capability on Google Cloud Platform. Together they demonstrate the full enterprise decision space: **cloud-native scale vs. data-sovereign private inference** — a distinction that matters enormously in regulated industries, financial services, and any organization where data residency is non-negotiable.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client (Mac / Browser)               │
└─────────────────────────┬───────────────────────────────┘
                          │ http://192.168.1.59:3000
┌─────────────────────────▼───────────────────────────────┐
│              Open WebUI v0.8.12  (port 3000)             │
│         Chat UI · Web Search · Model Switching           │
└──────┬──────────────────┬──────────────────┬────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────┐  ┌─────────────────┐  ┌────────────────┐
│ llama-server│  │    SearXNG      │  │  Pipelines     │
│  port 8080  │  │   port 8081     │  │  port 9099     │
│             │  │                 │  │                │
│ qwen-active │  │ Web-augmented   │  │ RAG filter     │
│ (symlink)   │  │ search          │  │ Hybrid search  │
│ AMD RX 6800 │  │                 │  │ + RRF fusion   │
│ XT (ROCm)   │  │                 │  │                │
└─────────────┘  └─────────────────┘  └───────┬────────┘
                                              │
       ┌──────────────────────────────────────┘
       ▼  (RAG Stack)
┌─────────────┐  ┌─────────────────┐  ┌────────────────┐
│   Qdrant    │  │  Apache Tika    │  │    Ollama      │
│  port 6333  │  │   port 9998     │  │  port 11434    │
│             │  │                 │  │                │
│ Vector DB   │  │ Document parse  │  │ nomic-embed    │
│ On-disk HNSW│  │ PDF DOCX EPUB   │  │ text (CPU)     │
│ 75-150M vec │  │ email HTML etc  │  │ 768-dim embed  │
└─────────────┘  └─────────────────┘  └────────────────┘
```

---

## Hardware

| Component | Spec | Notes |
|---|---|---|
| CPU | Intel i7-10700 — 8C/16T | Model loading, CPU-offloaded layers |
| GPU | AMD RX 6800 XT — 16GB GDDR6 | Primary inference engine (RDNA 2, gfx1030) |
| RAM | 64GB DDR4 | Headroom for large models + RAG services |
| Storage | 4TB NVMe SSD | Model collection + vector store |
| OS | Ubuntu 22.04.5 LTS (Jammy) | ROCm 6.3 requires Jammy specifically |
| Total build cost | ~$800 used | RX 6800 XT is the key purchase |

---

## Stack

| Component | Software | Version | Purpose |
|---|---|---|---|
| Inference | llama.cpp | build 8454 | GPU-accelerated LLM serving via ROCm |
| Chat UI | Open WebUI | v0.8.12 | Full-featured chat interface |
| Web Search | SearXNG | 2026.3.18 | Self-hosted web search augmentation |
| Containers | Docker CE | 29.3.0 | Hosts WebUI and SearXNG |
| Embeddings | Ollama + nomic-embed-text | 0.18.2 | RAG embeddings on CPU |
| Vector DB | Qdrant | latest | On-disk HNSW vector search |
| Doc Parser | Apache Tika | latest-full | Universal document extraction |
| RAG Pipeline | Open WebUI Pipelines | main | Hybrid retrieval filter with RRF fusion |

---

## Models

### Model Files

| File | Quantization | Size | Notes |
|---|---|---|---|
| `Qwen3.5-9B-Q6_K.gguf` | Q6_K | 7.0 GB | Primary — high quality, fully on GPU |
| `Qwen_Qwen3.5-9B-Q4_K_M.gguf` | Q4_K_M | 5.5 GB | Fallback — lower VRAM, faster load |
| `qwen3.5-27b-q3_K_M.gguf` | Q3_K_M | 13.4 GB | Custom quantized — capable, still on GPU |

> **Note:** `qwen3.5-27b-f16.gguf` (54GB) is the intermediate conversion artifact used to produce the Q3_K_M. It can be safely deleted once the Q3_K_M is confirmed working — `rm ~/models/qwen3.5-27b-f16.gguf` recovers 54GB.

### Active Model Symlink

llama-server loads `~/models/qwen-active.gguf` — a symlink that points to whichever model is currently active. Switching models requires only repointing the symlink and restarting llama-server. Open WebUI configuration never needs to change.

```bash
# Current state
ls -la ~/models/qwen-active.gguf
# qwen-active.gguf -> /home/chuck/models/Qwen3.5-9B-Q6_K.gguf

# Switch to 27B Q3_K_M
ln -sf ~/models/qwen3.5-27b-q3_K_M.gguf ~/models/qwen-active.gguf

# Switch to 9B Q4_K_M (lower VRAM)
ln -sf ~/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf ~/models/qwen-active.gguf

# Switch back to 9B Q6_K (primary)
ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf
```

### VRAM Configurations

| Config | Model | KV Cache | Context | Total VRAM | Headroom | Status |
|---|---|---|---|---|---|---|
| A — Fallback | Q4_K_M 9B | q4_0 | 131K | ~10.7 GB | ~5.3 GB | Available |
| B — Will spill | Q6_K 9B | q8_0 | 131K | ~16.0 GB | ~0 GB | Avoid |
| C — Primary | Q6_K 9B | q4_0 | 131K | ~14.5 GB | ~1.5 GB | Active |
| D — Comfortable | Q6_K 9B | q4_0 | 32K | ~8.7 GB | ~7.3 GB | Use for non-coding |
| E — Large model | Q3_K_M 27B | q4_0 | 32K | ~14.0 GB | ~2.0 GB | Use for complex tasks |

**Config C (Active):** Q6_K at 131K context with q4_0 KV cache sits at ~14.5GB (84% VRAM). Confirmed fully on GPU — `load_tensors: offloaded 33/33 layers to GPU`. The 1.5GB headroom is tight but sufficient for coding sessions up to ~75K tokens. Monitor with `watch -n 2 "rocm-smi --showmeminfo vram | grep Used"` during long sessions.

> **Why Q6_K over Q4_K_M?** Q6_K delivers meaningfully better output quality — sharper reasoning, more accurate code, better instruction following — at only 1.5GB additional VRAM over Q4_K_M. The quality improvement is particularly noticeable in coding and multi-step reasoning tasks. The tradeoff is reduced VRAM headroom at 131K context.

> **Why not q8_0 KV cache?** At 131K context, q8_0 KV cache consumes an additional ~3GB versus q4_0, pushing total VRAM to the ceiling (~16GB) with effectively zero headroom. q4_0 KV cache at this context size is the correct choice. If context is reduced to 32K, q8_0 becomes viable and improves attention fidelity in long multi-turn sessions.

---

## Features

### Phase 1 — Complete

- GPU-accelerated inference via ROCm on AMD RX 6800 XT
- OpenAI-compatible API at `http://192.168.1.59:8080/v1`
- Full chat UI with conversation history, system prompts, and model switching
- Live web search augmentation via self-hosted SearXNG
- Dual-model setup — switch between 9B (fast) and 27B (capable) via symlink
- Accessible from any device on the local network

### Phase 2 — Complete

- Hybrid BM25 + semantic vector search with Reciprocal Rank Fusion
- 2–3TB document corpus support with tiered on-disk HNSW indexing (docs_hot + docs_cold)
- Universal document parsing: PDF, DOCX, PPTX, XLSX, EPUB, email, HTML
- EPUB chapter-aware extraction with per-chapter metadata via ebooklib
- Incremental ingestion — drop files via SFTP from Mac, indexed automatically via file watcher
- Symlink-based document storage (`~/documents/`) — starts on NVMe, migrates to dedicated SATA drive with a single `ln -sf`
- RAG retrieval integrated into Open WebUI via Pipelines filter — every chat query searches the knowledge base
- Pipelines server registered as an OpenAI API connection (not a separate Pipelines URL)

### Phase 3 — Planned

- On-demand document generation: ask for a DOCX or PPTX, get a file
- Pandoc + LibreOffice conversion pipeline

---

## Quick Start

### Prerequisites

- Ubuntu 22.04 LTS (Jammy) — not 24.04, ROCm repos require Jammy
- AMD ROCm 6.3 installed
- Docker CE and Docker Compose v2
- llama.cpp built from source with HIP backend
- [The blog post](https://chucktsocanos.com/#blog/building-private-ai-server-part1)
- [The build document](https://chucktsocanos.com/downloads/ubuntu-ai-setup-procedure.docx)

### 1. Clone this repository

```bash
git clone https://github.com/chucklezt/chuckai.git
cd chuckai
```

### 2. Copy configs to home directory

```bash
cp configs/docker-compose.yml ~/docker-compose.yml
cp configs/start-llama-qwen.sh ~/start-llama-qwen.sh
mkdir -p ~/searxng
cp configs/searxng-settings.yml ~/searxng/settings.yml
chmod +x ~/start-llama-qwen.sh
```

### 3. Download models

```bash
mkdir -p ~/models
pip3 install huggingface_hub

# Primary model — Q6_K (recommended)
huggingface-cli download unsloth/Qwen3.5-9B-GGUF Qwen3.5-9B-Q6_K.gguf \
  --local-dir /home/$USER/models/

# Fallback model — Q4_K_M (lower VRAM)
huggingface-cli download bartowski/Qwen_Qwen3.5-9B-Instruct-GGUF \
  Qwen_Qwen3.5-9B-Instruct-Q4_K_M.gguf \
  --local-dir /home/$USER/models/
```

### 4. Create the active model symlink

```bash
# Point to Q6_K as primary
ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf
```

### 5. Start llama-server

```bash
bash ~/start-llama-qwen.sh &
sleep 15 && curl -s http://localhost:8080/health
# Expected: {"status":"ok"}
```

### 6. Start Docker services

```bash
cd ~ && docker compose up -d
sleep 10 && curl -s http://localhost:3000/api/version
# Expected: {"version":"0.8.12"}
```

### 7. Configure web search

Open `http://192.168.1.59:3000` → Admin Panel → Settings → Web Search:
- Enable Web Search: **ON**
- Engine: **SearXNG**
- URL: `http://localhost:8081/search?q=<query>`
- Save

The globe icon will appear in the chat input bar. Click it to enable web-augmented responses.

### 8. Set up RAG ingestion

```bash
# Create document directories
mkdir -p ~/documents/inbox ~/documents/inbox_priority

# Start Ollama and pull the embedding model
sudo systemctl enable ollama && sudo systemctl start ollama
ollama pull nomic-embed-text

# Create Python venv and install dependencies
cd ~/chuckai
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r ingest/requirements.txt

# Start the file watcher (processes existing files, then watches for new ones)
.venv/bin/python -m ingest.watcher
```

Drop files into `~/documents/inbox_priority/` (queried first) or `~/documents/inbox/` (fallback archive). Supported formats: PDF, DOCX, PPTX, XLSX, EPUB, HTML, TXT, Markdown, CSV, JSON.

### 9. Verify Pipelines connection

The Pipelines server (RAG filter) is started automatically by `docker compose up -d`. The connection to Open WebUI is configured via environment variables in `docker-compose.yml`:

```yaml
- OPENAI_API_BASE_URLS=http://localhost:8080/v1;http://localhost:9099
- OPENAI_API_KEYS=dummy;0p3n-w3bu!
```

**Important:** The Pipelines server must be registered as a second OpenAI API connection using the semicolon-separated `OPENAI_API_BASE_URLS` and `OPENAI_API_KEYS` variables. Do NOT use `PIPELINES_URLS` or `PIPELINES_API_KEY` — Open WebUI v0.8.12 ignores these and the Admin Panel will show "Pipelines Not Detected." The default Pipelines API key is `0p3n-w3bu!`.

Verify in the Admin Panel → Settings → Pipelines — you should see the "RAG Retrieval" filter listed.

---

## Service Management

### Start and stop llama-server

```bash
# Start
bash ~/start-llama-qwen.sh &

# Stop
pkill -9 llama-server

# Check status
curl -s http://localhost:8080/health
pgrep -fa llama-server
```

### Switching models via symlink

```bash
# Switch to 27B — complex reasoning tasks
pkill -9 llama-server
ln -sf ~/models/qwen3.5-27b-q3_K_M.gguf ~/models/qwen-active.gguf
sleep 3 && bash ~/start-llama-qwen.sh &

# Switch to 9B Q6_K — primary (coding, chat, RAG)
pkill -9 llama-server
ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf
sleep 3 && bash ~/start-llama-qwen.sh &

# Switch to 9B Q4_K_M — lowest VRAM, fastest load
pkill -9 llama-server
ln -sf ~/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf ~/models/qwen-active.gguf
sleep 3 && bash ~/start-llama-qwen.sh &

# Check which model is currently active
ls -la ~/models/qwen-active.gguf

# Confirm what llama-server loaded
curl -s http://localhost:8080/v1/models | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"
```

### Convenience aliases

Add to `~/.bashrc`:

```bash
alias model-9b-q6='pkill -9 llama-server; sleep 3; \
  ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf; \
  bash ~/start-llama-qwen.sh & echo "Starting 9B Q6_K..."'

alias model-9b-q4='pkill -9 llama-server; sleep 3; \
  ln -sf ~/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf ~/models/qwen-active.gguf; \
  bash ~/start-llama-qwen.sh & echo "Starting 9B Q4_K_M..."'

alias model-27b='pkill -9 llama-server; sleep 3; \
  ln -sf ~/models/qwen3.5-27b-q3_K_M.gguf ~/models/qwen-active.gguf; \
  bash ~/start-llama-qwen.sh & echo "Starting 27B Q3_K_M..."'

alias model-status='ls -la ~/models/qwen-active.gguf && \
  curl -s http://localhost:8080/v1/models | python3 -c \
  "import sys,json; print(json.load(sys.stdin)[\"data\"][0][\"id\"])"'
```

Apply changes:

```bash
source ~/.bashrc
```

### Docker services

```bash
docker compose up -d        # start all services
docker compose down         # stop all services
docker compose restart      # restart all services
docker compose ps           # check status
docker compose logs -f      # watch logs
```

### Open WebUI backup and rollback

Open WebUI was upgraded from v0.5.20 to v0.8.12 on 2026-04-01. Local backups were created before the upgrade:

| Backup | Location | Contents |
|---|---|---|
| v0.5.20 container image | `open-webui-backup:v0.5.20` | Full container snapshot via `docker commit` |
| v0.5.20 data | `~/open-webui-backup-v0.5.20/data/` | webui.db, cache, uploads, vector_db |
| v0.8.12 container image | `open-webui-backup:v0.8.12` | Post-upgrade container snapshot |
| Persistent data volume | `chuck_open-webui` | Named Docker volume, survives container recreation |

**Roll back to v0.5.20:**

```bash
# 1. Stop current container
cd ~ && docker compose down

# 2. Edit ~/docker-compose.yml — change the image line:
#    image: ghcr.io/open-webui/open-webui:latest
#    to:
#    image: open-webui-backup:v0.5.20

# 3. Restore the v0.5.20 data backup into the named volume
docker run --rm \
  -v chuck_open-webui:/data \
  -v ~/open-webui-backup-v0.5.20/data:/backup \
  alpine sh -c "rm -rf /data/* && cp -a /backup/. /data/"

# 4. Start with the old version
docker compose up -d

# 5. Verify
curl -s http://localhost:3000/api/version
# Expected: {"version":"0.5.20"}
```

**Roll back to v0.8.12 (if a future `:latest` breaks):**

```bash
cd ~ && docker compose down
# Edit ~/docker-compose.yml — change image to: open-webui-backup:v0.8.12
docker compose up -d
```

### Full stack health check

```bash
echo "=== llama.cpp ===" && curl -s http://localhost:8080/health
echo "=== Active model ===" && ls -la ~/models/qwen-active.gguf
echo "=== Open WebUI ===" && curl -s http://localhost:3000/api/version
echo "=== SearXNG ===" && curl -s "http://localhost:8081/search?q=test&format=json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK - {len(d[\"results\"])} results')"
echo "=== Docker ===" && docker compose ps
echo "=== GPU ===" && rocm-smi --showmeminfo vram | grep -E "Used|Total"
```

### GPU monitoring

```bash
rocm-smi                                              # current state
watch -n 1 rocm-smi                                   # live refresh
watch -n 2 "rocm-smi --showmeminfo vram | grep Used"  # VRAM only
grep "offload" ~/llama.log | head -5                  # confirm GPU layers at startup
```

---

## Port Reference

| Port | Service | Status |
|---|---|---|
| 8080 | llama-server — OpenAI API | Active |
| 3000 | Open WebUI | Active |
| 8081 | SearXNG | Active |
| 11434 | Ollama (embeddings, CPU) | Active |
| 6333 | Qdrant REST | Active |
| 6334 | Qdrant gRPC | Active |
| 9998 | Apache Tika | Active |
| 9099 | Open WebUI Pipelines (RAG filter) | Active |

---

## Roadmap

### Phase 2 — RAG Stack ✓
Qdrant on-disk vector database supporting 2–3TB of documents (~75–150M vectors). Hybrid BM25 sparse + semantic dense search with Reciprocal Rank Fusion. Universal document ingestion via Apache Tika and ebooklib. Incremental loading via file watcher — drop files into `~/documents/inbox/` or `~/documents/inbox_priority/` and they're indexed automatically. RAG retrieval wired into Open WebUI via a Pipelines filter that intercepts every chat query.

### Phase 3 — Document Output
On-demand generation of Word documents, PowerPoint presentations, and PDFs from model output. Pandoc + LibreOffice conversion triggered by natural language requests in chat.

### Future
- Image generation with Flux.1 on ROCm
- Voice interface
- Homelab network architecture (Tailscale, Cloudflare Tunnel)
- GCP hybrid mode — local inference, cloud-scale RAG index

---

## Related Projects

| Project | Description |
|---|---|
| [enterprise-rag-gcp](https://github.com/chucklezt/enterprise-rag-gcp) | The cloud-native counterpart — same RAG capability on GCP with Vertex AI, Gemini, Cloud Run, and Terraform. ~$1.36/month at demo scale. |

---

## Author

**Chuck Tsocanos**
Technology Executive · AI Strategist · Cloud Transformation Leader

30+ years of enterprise technology leadership including IBM, Kyndryl, Accenture, Grid Dynamics, Slalom, and Vervint (President & Chief Consulting Officer). Specializes in enterprise AI strategy, cloud architecture, and Fortune 100 technology transformation.

- Website: [chucktsocanos.com](https://chucktsocanos.com)
- LinkedIn: [linkedin.com/in/chucktsocanos](https://linkedin.com/in/chucktsocanos)

---

*Built with Claude Code and Claude.*
