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
│              Open WebUI v0.5.20  (port 3000)             │
│         Chat UI · Web Search · Model Switching           │
└──────┬──────────────────┬──────────────────┬────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────┐  ┌─────────────────┐  ┌────────────────┐
│ llama-server│  │    SearXNG      │  │  Pipelines     │
│  port 8080  │  │   port 8081     │  │  port 9099     │
│             │  │                 │  │  (Phase 3)     │
│ Qwen 3.5 9B │  │ Web-augmented   │  │                │
│ or 27B      │  │ search          │  │                │
│ AMD RX 6800 │  │                 │  │                │
│ XT (ROCm)   │  │                 │  │                │
└─────────────┘  └─────────────────┘  └────────────────┘
       │
       ▼  (Phase 2 — RAG Stack)
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
| Chat UI | Open WebUI | v0.5.20 | Full-featured chat interface |
| Web Search | SearXNG | 2026.3.18 | Self-hosted web search augmentation |
| Containers | Docker CE | 29.3.0 | Hosts WebUI and SearXNG |
| Embeddings | Ollama + nomic-embed-text | 0.18.2 | RAG embeddings on CPU (Phase 2) |
| Vector DB | Qdrant | latest | On-disk HNSW vector search (Phase 2) |
| Doc Parser | Apache Tika | latest-full | Universal document extraction (Phase 2) |

---

## Models

| Model | Quantization | VRAM | Speed | Context |
|---|---|---|---|---|
| Qwen3.5 9B (primary) | Q4_K_M | ~7 GB | 40–60 t/s | 131K configured |
| Qwen3.5 27B (custom) | Q3_K_M | ~13 GB | 15–20 t/s | 32K configured |

The 27B model was custom-quantized using llama.cpp's quantize tool — the standard Q4_K_M release is 17GB and spills beyond the 16GB VRAM ceiling. The Q3_K_M variant fits at 13GB with 3GB headroom.

### VRAM configurations

| Config | Model | KV Cache | Context | Total VRAM | Headroom |
|---|---|---|---|---|---|
| A — Current | Q4_K_M | q4_0 | 128K | 10.65 GB | 5.35 GB |
| B — Will spill | Q6_K | q8_0 | 128K | 15.95 GB | ~0 GB |
| C — Recommended | Q6_K | q8_0 | 32K | 8.70 GB | 7.30 GB |

Config C delivers a better model (Q6_K vs Q4_K_M) at higher KV cache precision (q8_0 vs q4_0) using *less* VRAM than the current setup — the single tradeoff is reducing context from 128K to 32K tokens.

---

## Features

### Phase 1 — Complete

- GPU-accelerated inference via ROCm on AMD RX 6800 XT
- OpenAI-compatible API at `http://192.168.1.59:8080/v1`
- Full chat UI with conversation history, system prompts, and model switching
- Live web search augmentation via self-hosted SearXNG
- Dual-model setup — switch between 9B (fast) and 27B (capable) with a single command
- Accessible from any device on the local network

### Phase 2 — In Development

- Hybrid BM25 + semantic vector search with Reciprocal Rank Fusion
- 2–3TB document corpus support with tiered on-disk HNSW indexing
- Universal document parsing: PDF, DOCX, PPTX, XLSX, EPUB, email, HTML
- EPUB chapter-aware extraction with per-chapter metadata
- Incremental ingestion — drop files via SFTP from Mac, indexed automatically
- Metadata-filtered retrieval by author, title, chapter, document type

### Phase 3 — Planned

- On-demand document generation: ask for a DOCX or PPTX, get a file
- Pandoc + LibreOffice conversion pipeline
- Open WebUI Pipelines middleware

---

## Quick Start

### Prerequisites

- Ubuntu 22.04 LTS (Jammy) — not 24.04, ROCm repos require Jammy
- AMD ROCm 6.3 installed
- Docker CE and Docker Compose v2
- llama.cpp built from source with HIP backend

### 1. Clone this repository

```bash
git clone https://github.com/chucklezt/chuckai.git
cd chuckai
```

### 2. Copy configs to home directory

```bash
cp configs/docker-compose.yml ~/docker-compose.yml
cp configs/start-llama-qwe359.sh ~/start-llama-qwe359.sh
cp configs/start-llama-27b.sh ~/start-llama-27b.sh
mkdir -p ~/searxng
cp configs/searxng-settings.yml ~/searxng/settings.yml
chmod +x ~/start-llama-*.sh
```

### 3. Download a model

```bash
mkdir -p ~/models
pip3 install huggingface_hub
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
  repo_id='bartowski/Qwen_Qwen3.5-9B-Instruct-GGUF',
  local_dir='/home/$USER/models/qwen3.5-9b',
  allow_patterns=['*Q4_K_M*']
)
"
```

### 4. Start llama-server

```bash
bash ~/start-llama-qwe359.sh &
sleep 15 && curl -s http://localhost:8080/health
# Expected: {"status":"ok"}
```

### 5. Start Docker services

```bash
cd ~ && docker compose up -d
sleep 10 && curl -s http://localhost:3000/api/version
# Expected: {"version":"0.5.20"}
```

### 6. Configure web search

Open `http://192.168.1.59:3000` → Admin Panel → Settings → Web Search:
- Enable Web Search: **ON**
- Engine: **SearXNG**
- URL: `http://localhost:8081/search?q=<query>`
- Save

The globe icon will appear in the chat input bar. Click it to enable web-augmented responses.

---

## Service Management

### Model switching

```bash
# Switch to 27B model
pkill -9 llama-server && sleep 3 && bash ~/start-llama-27b.sh &

# Switch back to 9B
pkill -9 llama-server && sleep 3 && bash ~/start-llama-qwe359.sh &

# Check which model is loaded
curl -s http://localhost:8080/v1/models | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"
```

### Convenience aliases

Add to `~/.bashrc`:

```bash
alias model-9b='pkill -9 llama-server; sleep 3; bash ~/start-llama-qwe359.sh & echo "Starting 9B..."'
alias model-27b='pkill -9 llama-server; sleep 3; bash ~/start-llama-27b.sh & echo "Starting 27B..."'
alias model-status='curl -s http://localhost:8080/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)[\"data\"][0][\"id\"])"'
```

### Full stack health check

```bash
echo "=== llama.cpp ===" && curl -s http://localhost:8080/health
echo "=== Open WebUI ===" && curl -s http://localhost:3000/api/version
echo "=== SearXNG ===" && curl -s "http://localhost:8081/search?q=test&format=json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK - {len(d[\"results\"])} results')"
echo "=== Docker ===" && docker compose ps
echo "=== GPU ===" && rocm-smi --showtemp 2>/dev/null | grep -E "GPU|Temp"
```

### GPU monitoring

```bash
rocm-smi               # current state
watch -n 1 rocm-smi    # live refresh
```

---

## Port Reference

| Port | Service | Status |
|---|---|---|
| 8080 | llama-server — OpenAI API | Active |
| 3000 | Open WebUI | Active |
| 8081 | SearXNG | Active |
| 11434 | Ollama (embeddings, CPU) | Phase 2 |
| 6333 | Qdrant REST | Phase 2 |
| 6334 | Qdrant gRPC | Phase 2 |
| 9998 | Apache Tika | Phase 2 |
| 9099 | Open WebUI Pipelines | Phase 3 |

---

## Roadmap

### Phase 2 — RAG Stack
Qdrant on-disk vector database supporting 2–3TB of documents (~75–150M vectors). Hybrid BM25 sparse + semantic dense search with Reciprocal Rank Fusion. Universal document ingestion via Apache Tika and ebooklib. Incremental loading — start with a small corpus and grow without re-indexing.

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
