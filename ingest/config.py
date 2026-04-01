"""Central configuration for the ingestion pipeline."""

import os

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_HOT = "docs_hot"
COLLECTION_COLD = "docs_cold"

# Ollama embeddings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

# Tika
TIKA_URL = os.getenv("TIKA_URL", "http://localhost:9998")

# Chunking
CHUNK_SIZE = 500  # characters
CHUNK_OVERLAP = 50

# BM25 sparse vector
BM25_K1 = 1.2
BM25_B = 0.75
HASH_SPACE = 2**24  # 16M buckets for token hashing

# Document paths
DOCUMENTS_DIR = os.path.expanduser("~/documents")
INBOX_DIR = os.path.join(DOCUMENTS_DIR, "inbox")
INBOX_PRIORITY_DIR = os.path.join(DOCUMENTS_DIR, "inbox_priority")

# Supported file types routed to Tika
TIKA_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".txt", ".md", ".csv", ".json"}
EPUB_EXTENSION = ".epub"
