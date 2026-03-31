#!/bin/bash
export HSA_OVERRIDE_GFX_VERSION=10.3.0
cd /home/chuck/llama.cpp

./build/bin/llama-server \
  -m /home/chuck/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf \
  --ctx-size 131072 \
  --n-gpu-layers 99 \
  --cache-type-k q4_0 \
  --cache-type-v q4_0 \
  -fa on \
  -np 1 \
  --temp 1.0 \
  --top-p 0.95 \
  --top-k 20 \
  --min-p 0.00 \
  --host 0.0.0.0 \
  --port 8080 \
  --jinja \
  -rea off > ~/llama.log 2>&1
