# ChuckAI — Private AI Infrastructure

**A production-grade, self-hosted AI inference and RAG stack running on bare metal Ubuntu 22.04 with NVIDIA GPU acceleration. Zero cloud dependency. Zero per-token cost. Full data sovereignty.**

> Designed and built by [Chuck Tsocanos](https://chucktsocanos.com) — Technology Executive, AI Strategist, Cloud Transformation Leader.

---

## What's New — May 2026

**GPU upgrade: AMD RX 6800 XT → NVIDIA RTX 3090 (24GB).** The original ChuckAI build ran on a 16GB RX 6800 XT (RDNA 2, gfx1030) under ROCm 6.3. After 14 months of production use that validated the full Phase 1/2/3 stack on AMD hardware, the system was upgraded to an RTX 3090 for the larger 24GB VRAM envelope and a smoother CUDA toolchain. The AMD-era build knowledge is preserved in detail in the [AMD Build Reference](#amd-build-reference--rx-6800-xt-rocm-63) appendix below — every flag, every workaround, every "why does this fail silently" lesson — because that knowledge stays relevant whenever AMD AI hardware reappears in the conversation (Strix Halo, MI300X, RDNA 4, ROCm 7, customer environments).

**Benchmark results drove a primary model change.** After running llama-bench across the full model collection on the 3090, the new primary is `Qwen3.6-35B-A3B-UD-Q4_K_XL` — a 35B Mixture-of-Experts model that activates only ~3B parameters per forward pass. It achieves **143 t/s generation** at ~21GB VRAM — faster than any dense 9B model tested — while delivering 35B-class reasoning quality. The 24GB 3090 is the minimum viable hardware; it would not have fit on the 16GB RX 6800 XT. Three insights from the benchmark run:

1. **MoE beats dense 9B.** 143 t/s at 35B quality vs. 117 t/s (9B Q4_K_M) or 98 t/s (9B Q6_K). The architecture working exactly as designed.
2. **For quick tasks, 9B Q4_K_M beats Q6_K.** 117 t/s vs. 98 t/s with minimal quality difference — Q4_K_M is the better 9B fallback.
3. **Dense 27B models are memory-bandwidth-bound.** All cluster at 38–40 t/s regardless of quantization level. Going Q4 → Q6 on any 27B costs 7 t/s for marginal quality gain. Q6_K 27B is the worst value in the collection: ~21GB VRAM (same as the 35B-A3B), slowest generation (33 t/s), no quality upside. Skip it.

| Model | File Size | Prefill (pp512) | Generation (tg128) | VRAM | Notes |
|---|---|---|---|---|---|
| **Qwen3.6-35B-A3B Q4_K_XL** | 20.8 GB | 3272 t/s | **143 t/s** | ~21 GB | **Primary** |
| Qwen3.5-9B Q4_K_M | 5.5 GB | 4407 t/s | 117 t/s | ~6 GB | Speed fallback |
| Qwen3.5-9B Q6_K | 6.9 GB | 4043 t/s | 98 t/s | ~7 GB | Quality fallback |
| Qwen3.6-27B Q4_K_XL | 16.4 GB | 1419 t/s | 40 t/s | ~17 GB | BW-bound |
| Qwen3.6-27B Q4_K_M | 16.3 GB | 1402 t/s | 40 t/s | ~16 GB | BW-bound |
| Qwen3.5-27B Q3_K_M | 12.4 GB | 1326 t/s | 38 t/s | ~13 GB | BW-bound |
| Qwen3.6-27B Q6_K | 21.0 GB | 1311 t/s | 33 t/s | ~21 GB | **Skip — worst value** |

The migration surfaced one significant gotcha worth calling out up front: **the systemd override that forces Ollama to CPU was vendor-specific to ROCm and silently became a no-op under CUDA.** Ollama loaded the embedding model onto the 3090, contended with llama-server for VRAM and compute, and Pipelines' 5-second embed timeout fired on every RAG request — silently breaking retrieval while everything else looked healthy. The fix and the diagnostic path are documented in the [Troubleshooting](#troubleshooting-quick-reference) section. The override now covers both vendor families so a future swap doesn't repeat the lesson.

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
│         Chat UI · Web Search · Pipelines RAG             │
└──────┬──────────────────┬──────────────────┬────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────┐  ┌─────────────────┐  ┌────────────────┐
│ llama-server│  │    SearXNG      │  │  Pipelines     │
│  port 8080  │  │   port 8081     │  │  port 9099     │
│             │  │                 │  │                │
│ qwen-active │  │ Web-augmented   │  │ rag_pipeline   │
│ (symlink)   │  │ search          │  │ Hybrid BM25 +  │
│ 35B-A3B MoE │  │                 │  │ semantic + RRF │
│ RTX 3090    │  │                 │  │                │
└─────────────┘  └─────────────────┘  └───────┬────────┘
                                              │
       ┌──────────────────────────────────────┘
       ▼  (RAG Stack)
┌─────────────┐  ┌─────────────────┐  ┌────────────────┐
│   Qdrant    │  │  Apache Tika    │  │    Ollama      │
│  port 6333  │  │   port 9998     │  │  port 11434    │
│             │  │                 │  │                │
│ Vector DB   │  │ Document parse  │  │ nomic-embed    │
│ On-disk HNSW│  │ PDF DOCX EPUB   │  │ text v1.5 CPU  │
│ 75-150M vec │  │ email HTML etc  │  │ 768-dim embed  │
└─────────────┘  └─────────────────┘  └────────────────┘
```

---

## Hardware

| Component | Spec | Notes |
|---|---|---|
| CPU | Intel i7-10700 — 8C/16T | Model loading, CPU-offloaded layers, CPU-bound Ollama embeddings |
| **GPU (current)** | **NVIDIA RTX 3090 — 24GB GDDR6X** | **Primary inference engine (CUDA 13.2, driver 595.58.03)** |
| GPU (prior) | AMD RX 6800 XT — 16GB GDDR6 | Original build; see [AMD Build Reference](#amd-build-reference--rx-6800-xt-rocm-63) |
| RAM | 64GB DDR4 | Headroom for large models + RAG services |
| Storage | 4TB NVMe SSD | Model collection + vector store + document corpus |
| OS | Ubuntu 22.04.5 LTS (Jammy) | Originally pinned for ROCm 6.3; retained on CUDA build for stability |
| Network | Static IP 192.168.1.59 | Set via netplan |

The 8GB additional VRAM on the 3090 lifts the ceiling on practical configurations. The "will spill" row from the AMD build table is now comfortably in range; see the updated [VRAM Configurations](#vram-configurations) table.

---

## Stack

| Component | Software | Version | Purpose |
|---|---|---|---|
| Inference | llama.cpp | latest (CUDA build) | GPU-accelerated LLM serving via CUDA |
| Chat UI | Open WebUI | v0.8.12 | Full-featured chat interface |
| Web Search | SearXNG | 2026.3.18 | Self-hosted web search augmentation |
| Containers | Docker CE | 29.3.0 | Hosts WebUI, SearXNG, Qdrant, Tika, Pipelines |
| Embeddings | Ollama + nomic-embed-text:v1.5 | 0.18.2 | RAG embeddings on **CPU** (forced via systemd override) |
| Vector DB | Qdrant | latest | On-disk HNSW vector search |
| Doc Parser | Apache Tika | latest-full | Universal document extraction |
| RAG Pipeline | Open WebUI Pipelines | main | Hybrid retrieval filter with cosine threshold + RRF re-rank |

---

## Models

### Model Files

| File | Quantization | Size | Gen Speed | Notes |
|---|---|---|---|---|
| `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | Q4_K_XL | 20.8 GB | **143 t/s** | **Primary** — MoE, ~3B active params, 35B quality. Faster than any dense 9B |
| `Qwen_Qwen3.5-9B-Q4_K_M.gguf` | Q4_K_M | 5.5 GB | 117 t/s | **Speed fallback** — fastest dense model, recommended 9B choice |
| `Qwen3.5-9B-Q6_K.gguf` | Q6_K | 6.9 GB | 98 t/s | Quality fallback — marginal gain over Q4_K_M at 19 t/s cost |
| `qwen3.5-27b-q3_K_M.gguf` | Q3_K_M | 12.4 GB | 38 t/s | Large model option — BW-bound like all dense 27B; Q4 quantization is the right pick |

### Active Model Symlink

llama-server loads `~/models/qwen-active.gguf` — a symlink that points to whichever model is currently active. Switching models requires only repointing the symlink and restarting llama-server. Open WebUI configuration never needs to change.

```bash
# Current state
ls -la ~/models/qwen-active.gguf

# Switch to 35B-A3B MoE Q4_K_XL (primary — 143 t/s, ~21GB)
ln -sf ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ~/models/qwen-active.gguf

# Switch to 9B Q4_K_M (low-VRAM fallback — ~6GB)
ln -sf ~/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf ~/models/qwen-active.gguf

# Switch to 9B Q6_K (quality fallback — ~7GB)
ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf

# Switch to 27B Q3_K_M (large model — ~13GB)
ln -sf ~/models/qwen3.5-27b-q3_K_M.gguf ~/models/qwen-active.gguf
```

### VRAM Configurations

Benchmarks on the 3090 selected a new primary model: Qwen3.6-35B-A3B-UD-Q4_K_XL, a Mixture-of-Experts model that activates only ~3B parameters per forward pass despite 35B total — yielding 35B-quality reasoning at 143 t/s, faster than any dense 9B model tested. The AMD-era table is retained in the [appendix](#amd-build-reference--rx-6800-xt-rocm-63) for historical reference.

| Config | Model | KV Cache | Context | VRAM | Gen Speed | Status |
|---|---|---|---|---|---|---|
| **Primary** | **Q4_K_XL 35B-A3B MoE** | q4_0 | 131K | ~21 GB | **143 t/s** | **Active** |
| A — Speed fallback | Q4_K_M 9B | q4_0 | 131K | ~10.7 GB | 117 t/s | Available |
| B — Quality fallback | Q6_K 9B | q4_0 | 131K | ~14.5 GB | 98 t/s | Available |
| C — Large model | Q3_K_M 27B | q4_0 | 32K | ~14 GB | 38 t/s | Available |
| D — Large model long ctx | Q3_K_M 27B | q8_0 | 64K | ~17 GB | 38 t/s | Available |
| — | Q6_K 27B (any) | — | — | ~21 GB | 33 t/s | **Not recommended** |

**Model selection notes:**
- **35B-A3B MoE** is primary — 35B quality, 143 t/s. Faster than any dense 9B because MoE activates ~3B parameters per token. Requires ~21GB.
- **9B Q4_K_M** is the recommended speed fallback — 117 t/s, beats Q6_K (98 t/s) with negligible quality loss.
- **Dense 27B models** are memory-bandwidth-bound: all deliver 38–40 t/s regardless of quantization. Q4 vs. Q6 on a 27B is not worth the 7 t/s cost.
- **Q6_K 27B** is the worst value in the collection — same ~21GB VRAM as the 35B-A3B, slowest generation (33 t/s). Skip it.

---

## Features

### Phase 1 — Complete

- GPU-accelerated inference via CUDA on RTX 3090
- OpenAI-compatible API at `http://192.168.1.59:8080/v1`
- Full chat UI with conversation history, system prompts, and model switching
- Live web search augmentation via self-hosted SearXNG
- Dual-model setup — switch between 9B and 27B via symlink
- Accessible from any device on the local network

### Phase 2 — Complete

- Hybrid BM25 + semantic vector search with Reciprocal Rank Fusion (for re-ranking) and dense cosine similarity (for threshold filtering)
- 2–3TB document corpus support with tiered on-disk HNSW indexing (`docs_hot` + `docs_cold`)
- Universal document parsing: PDF, DOCX, PPTX, XLSX, EPUB, email, HTML
- EPUB chapter-aware extraction with per-chapter metadata via ebooklib
- Incremental ingestion — drop files via SFTP from Mac, indexed automatically via file watcher
- Symlink-based document storage (`~/documents/`) — starts on NVMe, migrates to dedicated SATA with a single `ln -sf`
- RAG retrieval integrated into Open WebUI via Pipelines filter — every chat query searches the knowledge base
- Pipelines server registered as an OpenAI API connection (not a separate Pipelines URL)
- Inline source citations and chapter references in model responses, with a Sources footer listing all retrieved documents
- Tuned retrieval: 1500-char chunks, top_k=10, boilerplate filtering — validated with *Microservices Patterns* by Chris Richardson (895 chunks, 35s ingestion)
- Pipeline timing logs for retrieval latency monitoring (embed, search, total per query)
- Sequenced startup script (`scripts/startup.sh`) with dependency ordering and health checks — ensures Pipelines is ready before Open WebUI starts
- Performance-tuned llama-server: `--no-cache-prompt`, `--poll 0`, `-np 1`, `--ctx-checkpoints 0`, `-fa on`, `--cache-type-k/v q4_0` (see [llama-server flags](#llama-server-flag-reference))
- **Ollama forced to CPU via systemd override (both CUDA and HIP variants)** — eliminates GPU contention with llama-server that caused Ollama embed calls to time out and silently break RAG
- Relevance filtering via dense cosine similarity scoring (not RRF rank scores) with 0.50 threshold — unrelated queries return zero chunks
- Response mode tags (`RAG`, `LLM`, `Web`) in every response footer for retrieval transparency
- Query isolation — only the user's latest message is embedded for RAG, preventing conversation history from contaminating retrieval
- Open WebUI internal tasks (title/tag generation) skip RAG pipeline entirely

### Phase 3 — Planned

- On-demand document generation: ask for a DOCX or PPTX, get a file
- Pandoc + LibreOffice conversion pipeline

---

## Quick Start

### Prerequisites

- Ubuntu 22.04 LTS (Jammy)
- NVIDIA driver 595+ with CUDA 13.x
- Docker CE and Docker Compose v2
- llama.cpp built from source with CUDA backend (`-DGGML_CUDA=ON`)
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

### 3. Install the Ollama CPU override (critical)

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null <<'EOF'
[Service]
# NVIDIA (current hardware)
Environment="CUDA_VISIBLE_DEVICES="
Environment="OLLAMA_NUM_GPU=0"
# AMD ROCm (legacy / future swap protection)
Environment="HIP_VISIBLE_DEVICES=-1"
Environment="ROCR_VISIBLE_DEVICES=-1"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Why both vendor families:** A vendor-specific override silently becomes a no-op when the GPU is swapped to a different vendor. Setting both prevents the failure mode that took down RAG during the 3090 migration.

### 4. Download models

```bash
mkdir -p ~/models
pip3 install huggingface_hub

# Primary model — Q6_K (recommended)
huggingface-cli download unsloth/Qwen3.5-9B-GGUF Qwen3.5-9B-Q6_K.gguf \
  --local-dir /home/$USER/models/

# Fallback model — Q4_K_M (lower VRAM, faster load)
huggingface-cli download bartowski/Qwen_Qwen3.5-9B-Instruct-GGUF \
  Qwen_Qwen3.5-9B-Instruct-Q4_K_M.gguf \
  --local-dir /home/$USER/models/
```

### 5. Create the active model symlink

```bash
ln -sf ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ~/models/qwen-active.gguf
```

### 6. Start the full stack

```bash
bash ~/chuckai/scripts/startup.sh
```

**Always use the startup script, never plain `docker compose up -d`.** Open WebUI discovers the Pipelines RAG filter at startup. If Open WebUI starts before Pipelines is ready, RAG silently stops working — the filter is not retried.

**Startup sequence:**

| Step | Service | Why this order |
|---|---|---|
| 1 | Kill everything | Clean slate — kill llama-server, docker compose down |
| 2 | Ollama (systemd) | Needed by Pipelines for embeddings |
| 3 | llama-server | GPU inference. Wait for model load (up to 60s) |
| 4 | Qdrant, Tika, SearXNG | Infrastructure for RAG and web search |
| 5 | Warmup (Ollama, Qdrant, llama-server) | Prime cold caches with auto-retry if Ollama hangs |
| 6 | Pipelines | RAG filter. Needs warm Ollama + ready Qdrant |
| 7 | Open WebUI | Must discover Pipelines filter on startup |

### 7. Configure web search

Open `http://192.168.1.59:3000` → Admin Panel → Settings → Web Search:
- Enable Web Search: **ON**
- Engine: **SearXNG**
- URL: `http://localhost:8081/search?q=<query>`
- Save

The globe icon will appear in the chat input bar. Click it to enable web-augmented responses.

### 8. Set up RAG ingestion

```bash
mkdir -p ~/documents/inbox ~/documents/inbox_priority

sudo systemctl enable ollama && sudo systemctl start ollama
ollama pull nomic-embed-text:v1.5

cd ~/chuckai
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r ingest/requirements.txt

.venv/bin/python -m ingest.watcher
```

Drop files into `~/documents/inbox_priority/` (queried first) or `~/documents/inbox/` (fallback archive). Supported formats: PDF, DOCX, PPTX, XLSX, EPUB, HTML, TXT, Markdown, CSV, JSON.

### 9. Verify Pipelines connection

The Pipelines server is started automatically by `docker compose up -d`. The connection to Open WebUI is configured via environment variables in `docker-compose.yml`:

```yaml
- OPENAI_API_BASE_URLS=http://localhost:8080/v1;http://localhost:9099
- OPENAI_API_KEYS=dummy;0p3n-w3bu!
```

**Important:** The Pipelines server must be registered as a second OpenAI API connection using the semicolon-separated `OPENAI_API_BASE_URLS` and `OPENAI_API_KEYS` variables. Do NOT use `PIPELINES_URLS` or `PIPELINES_API_KEY` — Open WebUI v0.8.12 ignores these and the Admin Panel will show "Pipelines Not Detected." The default Pipelines API key is `0p3n-w3bu!`.

Verify in Admin Panel → Settings → Pipelines — you should see the "RAG Retrieval" filter listed.

---

## llama-server Flag Reference

llama-server runs in a **tmux session** named `llama` via `~/start-llama-qwen.sh`. The script creates the session if it doesn't exist; if it's already running it prints the attach command and exits.

**Required — Qwen architecture (removing any causes a documented failure):**

| Flag | Why it's required |
|---|---|
| `--no-cache-prompt` | Qwen 3.5's hybrid Mamba/attention architecture invalidates KV cache on every request. Without this, cache save time escalates to 160 seconds |
| `--jinja` | Required for Qwen 3.5 chat template handling |
| `-rea off` | Suppresses `<think>` tags that break JSON stream parsing in Pipelines |
| `--ctx-checkpoints 0` | Disables 50–87 MB checkpoint saves that block responses |
| `--poll 0` | Eliminates 100% idle CPU spin on one core |

**Serving and performance:**

| Flag | Value | Notes |
|---|---|---|
| `-m` | `~/models/qwen-active.gguf` | Symlink — model switching requires no config changes |
| `--ctx-size` | `131072` | 128K context window |
| `--n-gpu-layers` | `99` | Full offload to RTX 3090 |
| `--host` | `0.0.0.0` | Accessible from LAN |
| `--port` | `8080` | OpenAI-compatible API |
| `-np` | `1` | Single parallel slot. Pipeline filter skips `### Task:` title-gen prompts, so they never compete for the slot |
| `-fa` | `on` | Flash Attention — performance improvement at long context |
| `--cache-type-k` | `q4_0` | KV cache quantization (K) — matches VRAM table |
| `--cache-type-v` | `q4_0` | KV cache quantization (V) |

**Sampling:**

| Flag | Value |
|---|---|
| `--temp` | `0.6` |
| `--top-p` | `0.95` |
| `--top-k` | `20` |
| `--min-p` | `0.00` |

---

## Service Management

### Start and stop llama-server

```bash
# Start (creates tmux session "llama"; no-op if already running)
bash ~/start-llama-qwen.sh

# Attach to watch output
tmux attach -t llama
# Detach without killing: Ctrl-b  d

# Stop (kills session and process)
tmux kill-session -t llama

# Check status
curl -s http://localhost:8080/health
pgrep -fa llama-server

# Tail log
tail -f ~/llama.log
```

### Switching models via symlink

```bash
# Switch to 35B-A3B MoE Q4_K_XL — primary (143 t/s, ~21GB)
tmux kill-session -t llama 2>/dev/null; sleep 2
ln -sf ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ~/models/qwen-active.gguf
bash ~/start-llama-qwen.sh

# Switch to 9B Q4_K_M — speed fallback (~6GB, 117 t/s)
tmux kill-session -t llama 2>/dev/null; sleep 2
ln -sf ~/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf ~/models/qwen-active.gguf
bash ~/start-llama-qwen.sh

# Switch to 9B Q6_K — quality fallback (~7GB, 98 t/s)
tmux kill-session -t llama 2>/dev/null; sleep 2
ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf
bash ~/start-llama-qwen.sh

# Switch to 27B Q3_K_M — large model option (~13GB)
tmux kill-session -t llama 2>/dev/null; sleep 2
ln -sf ~/models/qwen3.5-27b-q3_K_M.gguf ~/models/qwen-active.gguf
bash ~/start-llama-qwen.sh

# Confirm what llama-server loaded
curl -s http://localhost:8080/v1/models | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"
```

### Full stack start / restart

```bash
bash ~/chuckai/scripts/startup.sh
```

Kills everything, then starts services in dependency order with health checks. Safe to run on a fresh boot or against a running stack.

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
cd ~ && docker compose down
# Edit ~/docker-compose.yml — change image to: open-webui-backup:v0.5.20
docker run --rm \
  -v chuck_open-webui:/data \
  -v ~/open-webui-backup-v0.5.20/data:/backup \
  alpine sh -c "rm -rf /data/* && cp -a /backup/. /data/"
docker compose up -d
curl -s http://localhost:3000/api/version  # Expected: {"version":"0.5.20"}
```

### Full stack health check

```bash
echo "=== llama.cpp ===" && curl -s http://localhost:8080/health
echo "=== Active model ===" && ls -la ~/models/qwen-active.gguf
echo "=== Open WebUI ===" && curl -s http://localhost:3000/api/version
echo "=== SearXNG ===" && curl -s "http://localhost:8081/search?q=test&format=json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK - {len(d[\"results\"])} results')"
echo "=== Qdrant ===" && curl -s http://localhost:6333/collections | python3 -m json.tool
echo "=== Pipelines ===" && curl -s -H "Authorization: Bearer 0p3n-w3bu!" \
  http://localhost:9099/models | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(f'OK - {[m[\"name\"] for m in d[\"data\"]]}')"
echo "=== Docker ===" && docker compose ps
echo "=== GPU ===" && nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv
echo "=== Ollama on CPU? ===" && nvidia-smi --query-compute-apps=pid,process_name --format=csv \
  | grep -i ollama && echo "WARNING: Ollama is on GPU" || echo "OK - Ollama is CPU-only"
```

### GPU monitoring

```bash
nvidia-smi                                          # current state
watch -n 1 nvidia-smi                               # live refresh
nvidia-smi --query-gpu=memory.used,memory.free \
  --format=csv -l 2                                 # VRAM only, every 2s
```

---

## Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---|---|---|
| RAG silently returns no context, model answers from training data only | Ollama embedding model loaded onto GPU, contending with llama-server, Pipelines embed times out at 5s | Apply CPU override (Quick Start step 3). Verify with `nvidia-smi` — only llama-server should be listed |
| `nvidia-smi` shows ollama process on GPU | CPU override missing or vendor-specific (only ROCm vars set) | Override must include `CUDA_VISIBLE_DEVICES=""` and `OLLAMA_NUM_GPU=0` — see Quick Start step 3 |
| llama-server 100% CPU at idle | Busy-wait polling | Add `--poll 0` to startup script |
| Multi-turn chat gets progressively slower | Prompt cache growing, saves take 40–160s | Add `--no-cache-prompt` (required for Qwen 3.5 hybrid arch) |
| Slow first query after reboot | Cold Ollama/Qdrant caches | Run `bash ~/chuckai/scripts/warmup.sh` after startup |
| Ollama embed hangs (>5s timeout in Pipelines logs) | GPU contention, see top row | CPU override |
| RAG not triggering after restart | Pipelines filter disconnected from Open WebUI | `docker compose restart pipelines open-webui` — or better, use `scripts/startup.sh` |
| "Expecting value: line 1 column 1" | Qwen think tags in stream | Confirm `-rea off` and `--jinja` in startup script |
| "Open WebUI Backend Required" | Browser cache mismatch | Cmd+Shift+R or open private window |
| SearXNG crashes immediately | Missing secret_key | Add secret_key to `~/searxng/settings.yml` |
| Globe icon not visible | Web search not enabled | Admin Panel → Settings → Web Search → ON → Save |
| Web search hangs, no response | Web search env vars set | Remove from docker-compose, configure via UI only |
| "Pipelines Not Detected" in UI | `PIPELINES_URLS` env var used | Add pipelines URL to `OPENAI_API_BASE_URLS` instead |
| Pipelines returns 401 | Missing API key | Use `0p3n-w3bu!` in `OPENAI_API_KEYS` |
| Chat prompt returns empty/hangs | Title generation cancels chat with `-np 1` | Pipeline inlet filters `### Task:` prompts — verify Pipelines is running and registered in Open WebUI |
| RAG injects irrelevant context | RRF rank scores don't reflect relevance | Use dense cosine similarity for threshold filtering (`score_threshold` in Qdrant query) |
| Services fail after reboot | Wrong startup order | Run `bash ~/chuckai/scripts/startup.sh` |
| `nvidia-smi` shows GPU at 23+ GB used | Could be normal (Q6_K + q8_0 + 131K) or contention | Check process list — only llama-server should appear |

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

### Phase 3 — Document Output
On-demand generation of Word documents, PowerPoint presentations, and PDFs from model output. Pandoc + LibreOffice conversion triggered by natural language requests in chat.

### Future
- Image generation with Flux.1
- Voice interface
- Homelab network architecture (Tailscale, Cloudflare Tunnel)
- GCP hybrid mode — local inference, cloud-scale RAG index

---

## AMD Build Reference — RX 6800 XT, ROCm 6.3

The original ChuckAI build ran on a 16GB RX 6800 XT under ROCm. Phase 1 and Phase 2 were both designed, built, and validated on this hardware over 14 months. This section preserves the AMD-specific knowledge that's still relevant when working with AMD AI hardware — whether revisiting this box on a swap, advising on customer AMD deployments, or evaluating Strix Halo / MI300X / RDNA 4 architectures.

### Hardware spec (prior)

| Component | Spec |
|---|---|
| GPU | AMD RX 6800 XT — 16GB GDDR6 |
| Architecture | RDNA 2 |
| GPU target | gfx1030 |
| Driver stack | ROCm 6.3.0 |
| Required OS | Ubuntu 22.04 LTS (Jammy) — **not** 24.04 |

### Critical flags and gotchas

**llama.cpp build command (AMD):**

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

**Critical flag:** `-DGGML_HIP=ON`, **not** `-DGGML_ROCM=ON`. The wrong flag causes a silent CPU-only fallback. The build succeeds, llama-server runs, inference works — at 1–2 tok/s instead of 50. The only way to catch it is checking the startup banner.

**Verify GPU is detected before trusting the build:**

```bash
./build/bin/llama-server --version 2>&1 | head -3
# Must show: found 1 ROCm devices: AMD Radeon RX 6800 XT, gfx1030
```

**Other AMD-specific gotchas:**

| Gotcha | Detail |
|---|---|
| Ubuntu version | ROCm 6.3 APT repo only provides Jammy (22.04) packages. Noble (24.04) silently fails with missing packages. Stick to Jammy |
| GCC version | The HIP build requires GCC 12 (`g++-12`) due to bundled clang header dependencies. Ubuntu 22.04 default is GCC 11. Install: `sudo apt install g++-12` |
| GFX override | RX 6800 XT requires `export HSA_OVERRIDE_GFX_VERSION=10.3.0` in shell env and `start-llama-qwen.sh`, or ROCm refuses to load |
| Ollama CPU override (legacy form) | The AMD-era override was `HIP_VISIBLE_DEVICES=-1` + `ROCR_VISIBLE_DEVICES=-1`. Both are needed — only one fails silently. Note: this is the override that became a no-op when the GPU was swapped to NVIDIA. The current override includes both vendor families |
| OC gives nothing | RX 6800 XT generation speed at these model sizes is memory-bandwidth-bound, not compute-bound. GPU overclocking provides no measurable improvement |

### AMD VRAM table (16GB)

This was the working configuration table on the RX 6800 XT, kept here for reference:

| Config | Model | KV Cache | Context | Total VRAM | Status |
|---|---|---|---|---|---|
| A — Fallback | Q4_K_M 9B | q4_0 | 131K | ~10.7 GB | Available |
| B — Will spill | Q6_K 9B | q8_0 | 131K | ~16 GB | **Avoid** |
| C — Primary | Q6_K 9B | q4_0 | 131K | ~14.5 GB | Active |
| D — Comfortable | Q6_K 9B | q4_0 | 32K | ~8.7 GB | Use for non-coding |
| E — Large model | Q3_K_M 27B | q4_0 | 32K | ~14.0 GB | Use for complex tasks |

### AMD-era monitoring commands

If revisiting AMD hardware, the equivalent of `nvidia-smi`:

```bash
rocm-smi                                              # current state
watch -n 1 rocm-smi                                   # live refresh
watch -n 2 "rocm-smi --showmeminfo vram | grep Used"  # VRAM only
grep "offload" ~/llama.log | head -5                  # confirm GPU layers
```

### AMD performance characterization

For reference when comparing to NVIDIA results:

- Generation speed: ~49 tok/s on Q6_K 9B at any prompt size
- RAG retrieval: 28-96ms total (embed ~28-69ms warm, Qdrant search ~3ms)
- Cold start (first Ollama embed): ~750ms vs ~28ms warm
- Memory bandwidth-bound, not compute-bound

These numbers are the AMD baseline. The 3090 should improve on all of them.

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
