"""File watcher for document ingestion pipeline.

Monitors ~/documents/inbox/ and ~/documents/inbox_priority/ for new files.
Files in inbox_priority go to docs_hot, files in inbox go to docs_cold.

Usage:
    cd ~/chuckai && .venv/bin/python -m ingest.watcher
"""

import logging
import os
import sys
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .chunker import chunk_sections
from .config import COLLECTION_COLD, COLLECTION_HOT, INBOX_DIR, INBOX_PRIORITY_DIR
from .embedder import embed_and_upsert, ensure_collections
from .extractor import extract, supported_extensions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


class IngestHandler(FileSystemEventHandler):
    def __init__(self, collection: str):
        self.collection = collection
        self.extensions = supported_extensions()

    def on_created(self, event):
        if event.is_directory:
            return
        self._process(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        self._process(event.dest_path)

    def _process(self, file_path: str):
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.extensions:
            log.debug(f"Skipping unsupported file: {file_path}")
            return

        # Wait for file to finish writing
        _wait_for_stable(file_path)

        log.info(f"Processing: {file_path} -> {self.collection}")
        try:
            sections = extract(file_path)
            if not sections:
                log.warning(f"No text extracted from {file_path}")
                return

            chunks = chunk_sections(sections)
            log.info(f"Extracted {len(sections)} sections, {len(chunks)} chunks")

            embed_and_upsert(chunks, self.collection)
            log.info(f"Done: {file_path} ({len(chunks)} chunks -> {self.collection})")

        except Exception:
            log.exception(f"Failed to process {file_path}")


def _wait_for_stable(path: str, interval: float = 1.0, checks: int = 3):
    """Wait until file size stops changing (upload complete)."""
    prev_size = -1
    stable = 0
    while stable < checks:
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        if size == prev_size:
            stable += 1
        else:
            stable = 0
            prev_size = size
        time.sleep(interval)


def ingest_existing():
    """Process any files already sitting in the inbox directories."""
    for directory, collection in [
        (INBOX_PRIORITY_DIR, COLLECTION_HOT),
        (INBOX_DIR, COLLECTION_COLD),
    ]:
        if not os.path.isdir(directory):
            continue
        extensions = supported_extensions()
        for filename in sorted(os.listdir(directory)):
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions:
                file_path = os.path.join(directory, filename)
                log.info(f"Ingesting existing file: {file_path}")
                handler = IngestHandler(collection)
                handler._process(file_path)


def main():
    ensure_collections()

    # Process any files already in the inboxes
    ingest_existing()

    # Watch for new files
    observer = Observer()
    observer.schedule(
        IngestHandler(COLLECTION_HOT), INBOX_PRIORITY_DIR, recursive=False
    )
    observer.schedule(
        IngestHandler(COLLECTION_COLD), INBOX_DIR, recursive=False
    )
    observer.start()
    log.info(f"Watching {INBOX_PRIORITY_DIR} -> {COLLECTION_HOT}")
    log.info(f"Watching {INBOX_DIR} -> {COLLECTION_COLD}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
