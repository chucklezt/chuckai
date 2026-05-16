# CLAUDE.md — ChuckAI Private AI Server

This file is read automatically by Claude Code at the start of every session. It contains everything you need to work safely and effectively in this repository.

---

## Recent Major Change — May 2026: GPU upgrade AMD → NVIDIA

**Current hardware: RTX 3090 (24GB, CUDA 13.2). Prior hardware: RX 6800 XT (16GB, ROCm 6.3).**
**Current primary model: Qwen3.6-35B-A3B-UD-Q4_K_XL — 143 t/s generation, ~21GB VRAM. Benchmarked May 2026.**

The full ChuckAI stack (Phase 1 inference, Phase 2 RAG, Phase 3 Pipelines integration) was originally designed, built, and validated for 14 months on the RX 6800 XT under ROCm. In May 2026 the GPU was swapped to an RTX 3090 and llama.cpp was rebuilt with `-DGGML_CUDA=ON`. Everything else in the stack is hardware-agnostic and carried over unchanged in principle — but one configuration error during the migration produced an instructive failure worth understanding before touching anything.

**The lesson: vendor-specific configuration can silently become a no-op when hardware changes.** The Ollama systemd override that forces embeddings to CPU was written with `HIP_VISIBLE_DEVICES=-1` and `ROCR_VISIBLE_DEVICES=-1` — both ROCm-only env vars. Under CUDA they have no effect. Ollama happily loaded `nomic-embed-text:v1.5` onto the 3090, contended with llama-server's Qwen inference for VRAM and compute, and Pipelines' 5-second embed timeout fired on every chat request. RAG broke silently — zero chunks retrieved, no context injected, model answered from training data. Everything else in the diagnostic output looked healthy.

**The current override covers both vendor families.** Whenever modifying GPU-adjacent configuration, prefer setting variables for both vendors rather than relying on the active one — it costs nothing and protects future swaps. See `configs/ollama.override.conf` and the "Ollama CPU override" entry in the troubleshooting table.

**AMD knowledge is preserved**, not deleted, because it stays relevant: customer AMD deployments, future GPU swaps, Strix Halo / MI300X / RDNA 4 evaluations, and the original blog post audience. See the [AMD Build Reference](#amd-build-reference--rx-6800-xt-rocm-63) section.

---

## Project Overview

ChuckAI is a self-hosted, GPU-accelerated AI inference and RAG (Retrieval-Augmented Generation) stack running on bare metal Ubuntu 22.04. It is designed and operated by Chuck Tsocanos — technology executive, AI strategist, and cloud transformation leader. This project serves two purposes: a working personal AI infrastructure and a portfolio demonstration of sovereign AI architecture for enterprise consulting conversations.

The stack is intentionally positioned as the on-premises counterpart to the GCP-native enterprise RAG system in the `enterprise-rag-gcp` repository. Together they demonstrate the full enterprise decision space: cloud-native scale vs. data-sovereign private inference.

---

## Hardware

| Component | Spec |
|---|---|
| Hostname | chuckai |
| IP | 192.168.1.59 (static via netplan) |
| User | chuck |
| CPU | Intel i7-10700 — 8C/16T |
| **GPU (current)** | **NVIDIA RTX 3090 — 24GB GDDR6X (CUDA, driver 595.58.03, CUDA 13.2)** |
| GPU (prior) | AMD RX 6800 XT — 16GB GDDR6 (RDNA 2, gfx1030, ROCm 6.3) |
| RAM | 64GB DDR4 |
| Storage | 4TB NVMe SSD |
| OS | Ubuntu 22.04.5 LTS (Jammy) |

---

## Confirmed Software Versions (May 2026)

| Component | Version |
|---|---|
| llama.cpp | CUDA build (`-DGGML_CUDA=ON`), rebuilt for RTX 3090 |
| Open WebUI | v0.8.12 (via `:latest` tag — backup images preserved) |
| SearXNG | 2026.3.18-3810dc9d1 |
| Docker CE | 29.3.0 |
| Docker Compose | v5.1.0 |
| Ollama | 0.18.2 (running — `nomic-embed-text:v1.5` for RAG embeddings, **CPU only** via systemd override) |
| Open WebUI Pipelines | main (`ghcr.io/open-webui/pipelines:main`) |
| NVIDIA driver | 595.58.03 |
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
│   ├── docker-compose.yml      # Open WebUI + SearXNG + Qdrant + Tika + Pipelines
│   ├── ollama.override.conf    # Forces Ollama to CPU (both CUDA and HIP)
│   ├── start-llama-qwen.sh     # llama-server startup — CUDA build, Qwen 3.5 9B
│   ├── start-llama-27b.sh      # llama-server startup — Qwen 3.5 27B Q3
│   └── searxng-settings.yml    # SearXNG configuration
├── ingest/                     # RAG ingestion service
│   ├── __init__.py
│   ├── requirements.txt
│   ├── config.py               # Central configuration constants
│   ├── watcher.py              # Watchdog file monitor for ~/documents/
│   ├── extractor.py            # Apache Tika wrapper + EPUB handler
│   ├── chunker.py              # Recursive character text splitter
│   ├── bm25_vectorizer.py      # Sparse BM25 token weights
│   └── embedder.py             # Dense + sparse upsert to Qdrant
├── pipelines/                  # Open WebUI pipeline plugins
│   └── rag_pipeline.py         # Hybrid BM25 + semantic RAG retrieval filter
├── scripts/                    # Utility and maintenance scripts
│   ├── healthcheck.sh          # Full stack health check
│   ├── startup.sh              # Sequenced full-stack start/restart with health checks
│   └── warmup.sh               # Prime cold services after reboot
└── docs/                       # Architecture and reference documentation
```

---

## Current Working State

### Phase 1 — COMPLETE ✓ (on CUDA)

- **llama.cpp** serving **Qwen3.6-35B-A3B-UD-Q4_K_XL** (primary — 143 t/s, ~21GB VRAM, MoE 3B active params) on port 8080 via RTX 3090 (CUDA). 9B models available as fallback via symlink
- **Open WebUI** v0.8.12 on port 3000 — chat, conversation history, model switching
- **SearXNG** on port 8081 — web-augmented responses via globe icon in chat
- **Web search** configured via Admin Panel UI (not env vars)
- **Model switching** via `~/models/qwen-active.gguf` symlink — 35B-A3B MoE, 9B Q4_K_M, or 9B Q6_K

### Phase 2 — COMPLETE ✓

- **Qdrant** vector database on port 6333 — on-disk HNSW, on-disk payload
- **Apache Tika** document parsing on port 9998
- **Ollama** embeddings via `nomic-embed-text:v1.5` on port 11434 (**CPU only** via systemd override — see below)
- **Python ingestion service** with watchdog file monitor (`cd ~/chuckai && .venv/bin/python -m ingest.watcher`)
- **Hybrid BM25 + semantic search** with RRF re-ranking via Qdrant
- **EPUB support** via ebooklib + BeautifulSoup4 (per-chapter extraction)
- **Tiered collections:** `docs_hot` (priority, queried first) + `docs_cold` (archive fallback)
- **Document storage** at `~/documents/inbox/` and `~/documents/inbox_priority/` — symlink-ready for SATA migration
- **RAG pipeline** integrated into Open WebUI via Pipelines filter on port 9099
- **Source citations** — inline chapter references in responses plus a Sources footer via pipeline outlet
- **Tuned retrieval** — 1500-char chunks, top_k=10, EPUB boilerplate filtering
- **Pipeline timing logs** — embed, hot search, cold fallback, and total retrieval latency logged per query (visible in `docker logs pipelines`)
- **Validated** with *Microservices Patterns* EPUB (895 chunks, 35s ingestion) — model cites specific chapters and passages

### Performance Tuning — COMPLETE ✓ (origin: 2026-04-01 on AMD; principles carry to NVIDIA)

The performance work below is architectural — properties of Qwen 3.5 and llama.cpp, not of the GPU vendor. All flags carried forward unchanged on the CUDA build.

- **RAG retrieval is fast** — 28-96ms total (embed ~28-69ms warm, Qdrant search ~3ms). Not a bottleneck.
- **Generation speed** — benchmarked on RTX 3090 (May 2026). Qwen3.6-35B-A3B Q4_K_XL (MoE, ~3B active params) achieves **143 t/s** at ~21GB VRAM — faster than any dense 9B tested (117 t/s Q4_K_M, 98 t/s Q6_K). MoE architecture means only ~3B parameters activate per forward pass, delivering 35B-quality reasoning at sub-10B inference cost. This is now the primary model. AMD baseline was ~49 tok/s on Q6_K 9B
- **Prompt cache was the bottleneck** — Qwen 3.5's hybrid Mamba/attention architecture invalidates KV cache on every request. llama-server was writing cache entries (growing to 1.3+ GB) then discarding them. Cache save time escalated from 40ms to 160 seconds over a session, blocking between requests. Fixed with `--no-cache-prompt`
- **Idle CPU spin** — llama-server busy-waits at 100% on one core without `--poll 0`. Fixed
- **Cold start latency** — first Ollama embed after reboot takes ~750ms vs ~28ms warm. Fixed with `scripts/warmup.sh`
- **Ollama can become unresponsive** — observed Ollama embed hanging after llama-server restarts. Root cause was GPU contention. Permanent fix is the CPU override below
- **Pipelines filter can disconnect** — after restarting llama-server, Open WebUI may stop routing through the Pipelines filter. Fix: `docker compose restart pipelines open-webui`. Better: use `scripts/startup.sh`

### RAG Retrieval Tuning — COMPLETE ✓

- **RRF scores are rank-based, not relevance-based** — Reciprocal Rank Fusion always returns positional scores (0.500 for rank 1, 0.333 for rank 2, etc.) regardless of actual semantic similarity. Every query matched something above threshold. Fixed by using **dense cosine similarity** for threshold filtering (via Qdrant `score_threshold`) and RRF only for re-ranking results that pass
- **Relevance threshold** — set to 0.50 cosine similarity. Unrelated queries (sports, general knowledge) score below this against technical documents and return 0 chunks. Related queries score 0.53–0.71 and retrieve correctly
- **Single slot request cancellation** — Open WebUI sends title generation requests alongside chat prompts. With `-np 1`, the title request cancelled the active chat generation mid-stream, producing empty responses. Originally fixed by setting `-np 2`; current fix is the pipeline inlet `### Task:` filter that drops title-gen prompts before they reach llama-server, allowing `-np 1` again
- **Conversation history contamination** — Open WebUI packs conversation history into a single user message. A 2000-char message containing prior assistant responses about microservices would match microservices chunks regardless of the actual question. Fixed by extracting only the last line when query exceeds 500 chars
- **Title generation polluting RAG** — Open WebUI's `### Task:` title/tag generation prompts were being embedded and searched unnecessarily. Fixed by skipping these in the pipeline inlet

### Ollama CPU Override — CRITICAL

This is the single most failure-prone piece of configuration in the stack, and it changed during the GPU migration.

**Required override** (`/etc/systemd/system/ollama.service.d/override.conf`):

```ini
[Service]
# NVIDIA (current hardware)
Environment="CUDA_VISIBLE_DEVICES="
Environment="OLLAMA_NUM_GPU=0"
# AMD ROCm (legacy / future swap protection)
Environment="HIP_VISIBLE_DEVICES=-1"
Environment="ROCR_VISIBLE_DEVICES=-1"
```

After modifying:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Why all four variables:** Setting only the active vendor's variable creates a hidden failure mode — when the GPU is swapped to a different vendor, the override silently becomes a no-op, Ollama loads the embed model onto the GPU, contention with llama-server causes Pipelines embed timeouts, RAG silently breaks. This was the actual root cause of the May 2026 "RAG isn't working after the 3090 upgrade" incident. The four-variable form costs nothing and protects against the failure.

**Verification:**
```bash
# Should show ONLY llama-server, no ollama
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv

# Should return in < 1 second with HTTP 200
time curl -s http://localhost:11434/api/embeddings \
  -d '{"model":"nomic-embed-text:v1.5","prompt":"test"}' \
  -o /dev/null -w "HTTP: %{http_code}  time: %{time_total}s\n"
```

---

## llama-server Flag Reference

Current startup command runs in a tmux session named `llama` via `~/start-llama-qwen.sh`. Full flag set:

**Required — Qwen architecture:**

| Flag | Why required |
|---|---|
| `--no-cache-prompt` | Qwen 3.5 hybrid Mamba/attention invalidates KV cache every request; without it, cache saves escalate to 160s |
| `--jinja` | Required for Qwen 3.5 chat template handling |
| `-rea off` | Suppresses `<think>` tags that break JSON stream parsing |
| `--ctx-checkpoints 0` | Disables 50–87MB checkpoint saves that block responses |
| `--poll 0` | Eliminates 100% idle CPU spin on one core |

**Serving:**

| Flag | Value | Notes |
|---|---|---|
| `-m` | `~/models/qwen-active.gguf` | Symlink — model switch = repoint + restart |
| `--ctx-size` | `131072` | 128K context |
| `--n-gpu-layers` | `99` | Full GPU offload to RTX 3090 |
| `--host` | `0.0.0.0` | Accessible from LAN, not just localhost |
| `--port` | `8080` | OpenAI-compatible API |
| `-np` | `1` | Single parallel slot. Pipeline filter blocks `### Task:` title-gen prompts before they reach llama-server, so single-slot cancellation is no longer an issue |
| `-fa` | `on` | Flash Attention — better performance at long context |
| `--cache-type-k` | `q4_0` | KV cache quantization (K) |
| `--cache-type-v` | `q4_0` | KV cache quantization (V) |

**Sampling:**

| Flag | Value |
|---|---|
| `--temp` | `0.6` |
| `--top-p` | `0.95` |
| `--top-k` | `20` |
| `--min-p` | `0.00` |

---

## VRAM Reference (RTX 3090, 24GB)

| Config | Model | KV Cache | Context | VRAM | Gen (tg128) | Status |
|---|---|---|---|---|---|---|
| **Primary** | **Q4_K_XL 35B-A3B MoE** | q4_0 | 131K | ~21 GB | **143 t/s** | **Active** |
| A — Speed fallback | Q4_K_M 9B | q4_0 | 131K | ~10.7 GB | 117 t/s | Available |
| B — Quality fallback | Q6_K 9B | q4_0 | 131K | ~14.5 GB | 98 t/s | Available |
| C — Large model | Q3_K_M 27B | q4_0 | 32K | ~14 GB | 38 t/s | Available |
| D — Large model long ctx | Q3_K_M 27B | q8_0 | 64K | ~17 GB | 38 t/s | Available |
| — Skip | Q6_K 27B (any) | — | — | ~21 GB | 33 t/s | Not recommended |

**Model selection analysis:**

- **35B-A3B MoE (primary):** MoE activates only ~3B parameters per forward pass — 35B quality at 143 t/s, faster than any dense 9B model. This is the MoE architecture working exactly as designed. Requires ~21GB; not viable on the 16GB AMD build.
- **9B Q4_K_M (speed fallback):** 117 t/s — faster than Q6_K (98 t/s) with minimal quality difference. Preferred 9B option when raw speed matters.
- **Dense 27B models:** All cluster at 38-40 t/s regardless of quantization level — memory bandwidth is the bottleneck, not compute. Q4 to Q6 on a 27B costs 7 t/s for marginal quality gain. Not worth it.
- **Q6_K 27B — skip:** Most VRAM (~21GB, same as the 35B-A3B), slowest generation (33 t/s), worst value of any config tested. Use Q4 27B if you need a 27B, or just use the 35B-A3B instead.

### Benchmark Results — RTX 3090 (May 2026)

| Model | File Size | Prefill (pp512) | Generation (tg128) | VRAM | Notes |
|---|---|---|---|---|---|
| **Qwen3.6-35B-A3B Q4_K_XL** | 20.8 GB | 3272 t/s | **143 t/s** | ~21 GB | **Primary — MoE beats dense 9B** |
| Qwen3.5-9B Q4_K_M | 5.5 GB | 4407 t/s | 117 t/s | ~6 GB | Speed fallback |
| Qwen3.5-9B Q6_K | 6.9 GB | 4043 t/s | 98 t/s | ~7 GB | Quality fallback |
| Qwen3.6-27B Q4_K_XL | 16.4 GB | 1419 t/s | 40 t/s | ~17 GB | BW-bound |
| Qwen3.6-27B Q4_K_M | 16.3 GB | 1402 t/s | 40 t/s | ~16 GB | BW-bound |
| Qwen3.5-27B Q3_K_M | 12.4 GB | 1326 t/s | 38 t/s | ~13 GB | BW-bound |
| Qwen3.6-27B Q6_K | 21.0 GB | 1311 t/s | 33 t/s | ~21 GB | **Skip — worst value** |

---

## llama.cpp Build Instructions (CUDA)

```bash
cd ~/llama.cpp
git pull
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
```

Verify GPU is detected:
```bash
./build/bin/llama-server --version 2>&1 | head -5
# Must show: found 1 CUDA devices: NVIDIA GeForce RTX 3090
```

If you see CPU fallback or zero CUDA devices, check: NVIDIA driver loaded (`nvidia-smi`), CUDA toolkit on PATH, and `nvcc --version` returns a sensible version.

For the AMD build instructions, see [AMD Build Reference](#amd-build-reference--rx-6800-xt-rocm-63).

---

## Common Commands

### llama-server lifecycle

```bash
# Start (creates tmux session "llama"; no-op if already running)
bash ~/start-llama-qwen.sh

# Attach to watch output / logs
tmux attach -t llama
# Detach without killing: Ctrl-b  d

# Stop
tmux kill-session -t llama
# or just kill the process (leaves empty tmux session):
pkill -9 llama-server

# Check
curl -s http://localhost:8080/health
curl -s http://localhost:8080/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])"

# Tail log
tail -f ~/llama.log
```

### Convenience aliases (in `~/.bashrc`)

```bash
alias model-35b='tmux kill-session -t llama 2>/dev/null; sleep 2; ln -sf ~/models/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ~/models/qwen-active.gguf; bash ~/start-llama-qwen.sh && echo "Starting 35B-A3B MoE..."'
alias model-9b='tmux kill-session -t llama 2>/dev/null; sleep 2; ln -sf ~/models/Qwen3.5-9B-Q6_K.gguf ~/models/qwen-active.gguf; bash ~/start-llama-qwen.sh && echo "Starting 9B..."'
alias model-27b='tmux kill-session -t llama 2>/dev/null; sleep 2; ln -sf ~/models/qwen3.5-27b-q3_K_M.gguf ~/models/qwen-active.gguf; bash ~/start-llama-qwen.sh && echo "Starting 27B..."'
alias model-status='curl -s http://localhost:8080/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)[\"data\"][0][\"id\"])"'
```

### Full stack management

```bash
bash ~/chuckai/scripts/startup.sh   # Sequenced start with health checks (USE THIS)
bash ~/chuckai/scripts/healthcheck.sh
docker compose ps
docker logs open-webui
docker logs pipelines --tail 50
```

### GPU monitoring (NVIDIA)

```bash
nvidia-smi
watch -n 1 nvidia-smi
nvidia-smi --query-gpu=memory.used,memory.free --format=csv -l 2
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv  # Should show only llama-server
```

---

## Phase 2 RAG — Design Reference

**Vector DB:** Qdrant with on-disk HNSW — required for 2-3TB corpus (~75-150M vectors). Configure `hnsw_index.on_disk: true` and `storage.on_disk_payload: true` from day one. Do not attempt in-memory indexing at this scale.

**Embeddings:** Ollama running `nomic-embed-text:v1.5` on **CPU** (port 11434). Forced to CPU via systemd override covering both vendor families (see "Ollama CPU Override" above). On CPU: ~19ms warm, ~400ms cold start. 768-dim vectors.

**Search strategy:** Hybrid BM25 sparse + semantic dense. Pure semantic search misses exact-match queries on technical documents. Both vector types stored in the same Qdrant collection. **Cosine similarity (0.50 threshold) for relevance filtering, RRF only for re-ranking the results that pass** — RRF scores are rank-based and don't reflect relevance, so they can't be used as a threshold.

**Tiered collections:**
- `docs_hot` — priority documents, queried first
- `docs_cold` — full archive, queried only as fallback when hot tier returns < 3 results

**EPUB handling:** Route `.epub` files through `ebooklib` + `BeautifulSoup4`, NOT Tika. Tika flattens EPUBs into a single blob. ebooklib extracts per-chapter with title/author/chapter metadata. Install: `pip install ebooklib==0.18 beautifulsoup4==4.12.3`.

**Document storage:** Documents live at `~/documents/` on the NVMe, with a symlink-based migration path for future SATA expansion:
```bash
mv ~/documents/* /mnt/sata/documents/
ln -sf /mnt/sata/documents ~/documents
```
All ingestion code, SFTP config, and file watchers reference `~/documents/` and never need to change.

**Document ingestion:** SFTP from Mac via Finder (`sftp://chuck@192.168.1.59`) or Cyberduck. Drop files to `~/documents/inbox_priority/` (hot tier) or `~/documents/inbox/` (cold tier).

**Pipelines registration:** Pipelines is registered as a second OpenAI API connection via:
```yaml
- OPENAI_API_BASE_URLS=http://localhost:8080/v1;http://localhost:9099
- OPENAI_API_KEYS=dummy;0p3n-w3bu!
```
Do NOT use `PIPELINES_URLS` — Open WebUI v0.8.12 ignores that env var.

**Abstraction principle:** Implement embeddings, vector store, and LLM calls behind simple interfaces from the start. This makes porting to GCP (Vertex AI embeddings, Vertex AI Vector Search, Gemini) a module swap rather than a rewrite.

---

## Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---|---|---|
| RAG returns no context, model answers from training only | Ollama on GPU, Pipelines embed times out at 5s | Apply CPU override covering both vendors; verify with `nvidia-smi --query-compute-apps` |
| `nvidia-smi` shows ollama process on GPU | CPU override missing or vendor-specific | Override must include `CUDA_VISIBLE_DEVICES=""` and `OLLAMA_NUM_GPU=0` |
| llama-server 100% CPU at idle | Busy-wait polling | Add `--poll 0` to startup script |
| Multi-turn chat gets progressively slower | Prompt cache invalidated each request | Add `--no-cache-prompt` (required for Qwen 3.5) |
| Slow first query after reboot | Cold caches | Run `bash ~/chuckai/scripts/warmup.sh` |
| Ollama embed hangs (>5s in Pipelines logs) | GPU contention | CPU override |
| RAG not triggering after restart | Pipelines filter disconnected | `docker compose restart pipelines open-webui` or use `scripts/startup.sh` |
| "Expecting value: line 1 column 1" | Qwen think tags in stream | Confirm `-rea off` and `--jinja` in startup script |
| "Model not found :latest" | `OLLAMA_BASE_URL` env var set on Open WebUI | Use `OPENAI_API_BASE_URLS` instead |
| "Open WebUI Backend Required" | Browser cache mismatch | Cmd+Shift+R or private window |
| SearXNG crashes immediately | Missing secret_key | Add secret_key to `~/searxng/settings.yml` |
| Globe icon not visible | Web search not enabled | Admin Panel → Settings → Web Search → ON → Save |
| Web search hangs | Web search env vars set | Remove from docker-compose, configure via UI only |
| GPU not detected (AMD legacy) | Missing HSA override | `export HSA_OVERRIDE_GFX_VERSION=10.3.0` |
| llama.cpp falls back to CPU (AMD legacy) | Wrong cmake flag | Use `-DGGML_HIP=ON` not `-DGGML_ROCM=ON` |
| llama.cpp falls back to CPU (NVIDIA) | Wrong cmake flag or missing CUDA | Use `-DGGML_CUDA=ON`; verify with `--version` startup banner |
| Static IP reverts on reboot | cloud-init overwriting netplan | Add `network: {config: disabled}` to cloud-init |
| Only 100GB disk visible | LVM not extended | `sudo lvextend -l +100%FREE` then `resize2fs` |
| "Pipelines Not Detected" in UI | `PIPELINES_URLS` env var used | Add pipelines URL to `OPENAI_API_BASE_URLS` |
| Pipelines returns 401 | Missing API key | Use `0p3n-w3bu!` in `OPENAI_API_KEYS` |
| Chat returns empty/hangs | Title gen cancels chat with `-np 1` | Pipeline inlet filters `### Task:` prompts before they reach llama-server — verify pipeline is running and registered |
| RAG injects irrelevant context | RRF rank scores don't reflect relevance | Use dense cosine similarity for `score_threshold` |
| RAG matches wrong content on follow-up | Conversation history embedded as query | Pipeline extracts last line only when query > 500 chars |
| Pipelines health check returns 403 | `/models` endpoint requires auth | Include `Authorization: Bearer 0p3n-w3bu!` header |
| Services fail after reboot | Wrong startup order | Run `bash ~/chuckai/scripts/startup.sh` |

---

## AMD Build Reference — RX 6800 XT, ROCm 6.3

Preserved for future AMD work — customer environments, hardware re-evaluation, Strix Halo / MI300X / RDNA 4 architectures, and the original blog post audience. This is the configuration that built Phases 1 and 2 over 14 months.

### Hardware (prior)

| Component | Spec |
|---|---|
| GPU | AMD RX 6800 XT — 16GB GDDR6 |
| Architecture | RDNA 2 |
| GPU target | gfx1030 |
| Driver stack | ROCm 6.3.0 |
| Required OS | Ubuntu 22.04 LTS (Jammy) — **not** 24.04 |

### Critical flags and gotchas (AMD)

**llama.cpp build command:**
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

**Critical: `-DGGML_HIP=ON`, not `-DGGML_ROCM=ON`.** The wrong flag causes a silent CPU-only fallback. The build succeeds, llama-server runs, inference works — at 1–2 tok/s instead of ~49. The only way to catch it is checking the `--version` startup banner.

**Verification:**
```bash
./build/bin/llama-server --version 2>&1 | head -3
# Must show: found 1 ROCm devices: AMD Radeon RX 6800 XT, gfx1030
```

**Other AMD-specific gotchas:**

| Gotcha | Detail |
|---|---|
| Ubuntu version | ROCm 6.3 APT repo only provides Jammy (22.04) packages. Noble (24.04) silently fails. Stick to Jammy |
| GCC version | HIP build requires GCC 12 (`g++-12`) due to bundled clang header dependencies. Ubuntu 22.04 default is GCC 11. Install: `sudo apt install g++-12` |
| GFX override | RX 6800 XT requires `export HSA_OVERRIDE_GFX_VERSION=10.3.0` in shell env and `start-llama-qwen.sh` or ROCm refuses to load |
| Ollama CPU override (AMD-only form) | `HIP_VISIBLE_DEVICES=-1` + `ROCR_VISIBLE_DEVICES=-1`. Both needed. This was the override that became a no-op when the GPU was swapped to NVIDIA — the current override includes both vendor families |
| OC gives nothing | RX 6800 XT generation speed at these model sizes is memory-bandwidth-bound, not compute-bound. GPU OC provides no measurable gain |

### AMD VRAM table (16GB)

| Config | Model | KV Cache | Context | Total VRAM | Status |
|---|---|---|---|---|---|
| A — Fallback | Q4_K_M 9B | q4_0 | 131K | ~10.7 GB | Available |
| B — Will spill | Q6_K 9B | q8_0 | 131K | ~16 GB | **Avoid** |
| C — Primary | Q6_K 9B | q4_0 | 131K | ~14.5 GB | Was Active |
| D — Comfortable | Q6_K 9B | q4_0 | 32K | ~8.7 GB | Use for non-coding |
| E — Large model | Q3_K_M 27B | q4_0 | 32K | ~14.0 GB | Use for complex tasks |

### AMD monitoring commands

```bash
rocm-smi                                              # current state
watch -n 1 rocm-smi                                   # live refresh
watch -n 2 "rocm-smi --showmeminfo vram | grep Used"  # VRAM only
grep "offload" ~/llama.log | head -5                  # confirm GPU layers
```

### AMD performance baseline

For reference when comparing to NVIDIA results:

- Generation speed: ~49 tok/s on Q6_K 9B
- RAG retrieval: 28-96ms total (embed ~28-69ms warm, Qdrant search ~3ms)
- Cold start: ~750ms first embed vs ~28ms warm
- Memory bandwidth-bound, not compute-bound

---

## Operating Principles

When working on this repo, follow these in order:

1. **Use `scripts/startup.sh`, not `docker compose up -d` directly.** Open WebUI must discover the Pipelines filter at startup. Plain compose start order is undefined and the filter silently fails to register.

2. **Configure GPU-adjacent overrides for both vendor families, not just the current one.** The May 2026 RAG outage was caused by a vendor-specific override silently becoming a no-op after a GPU swap. Cost is zero, protection is permanent.

3. **Use the symlink pattern for any configuration that might be swapped.** `qwen-active.gguf`, `~/documents/`, and similar indirection makes hardware/model/storage migrations a single command.

4. **Back up before rebuilds.** `docker commit` Open WebUI containers, copy llama-server binaries before recompiling. The `open-webui-backup:v0.5.20` image saved the v0.8.12 upgrade from being a one-way trip.

5. **Read the Pipelines logs when RAG misbehaves.** They are the single most informative source of ground truth — they show whether the filter is being invoked, whether the embed succeeded, how many chunks came back, and how long each step took. `docker logs pipelines --follow` while reproducing the issue resolves most RAG questions in one observation.

6. **Preserve AMD knowledge.** Even on CUDA hardware today, the AMD build remains relevant for customer engagements, hardware re-evaluation, and the original blog post audience. The [AMD Build Reference](#amd-build-reference--rx-6800-xt-rocm-63) section is not legacy clutter — it's institutional knowledge.
