"""Document text extraction via Apache Tika and ebooklib."""

import os
import warnings
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import ebooklib
from ebooklib import epub

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from .config import TIKA_URL, TIKA_EXTENSIONS, EPUB_EXTENSION


def extract(file_path: str) -> list[dict]:
    """Extract text and metadata from a document.

    Returns a list of sections, each with keys:
        - text: extracted text content
        - metadata: dict with source, and format-specific fields
          (page_number, chapter_title, chapter_index, book_title, etc.)
    """
    ext = os.path.splitext(file_path)[1].lower()
    source = os.path.basename(file_path)

    if ext == EPUB_EXTENSION:
        return _extract_epub(file_path, source)
    elif ext in TIKA_EXTENSIONS:
        return _extract_tika(file_path, source)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _extract_tika(file_path: str, source: str) -> list[dict]:
    """Extract text via Apache Tika HTTP API."""
    with open(file_path, "rb") as f:
        resp = requests.put(
            f"{TIKA_URL}/tika",
            data=f,
            headers={"Accept": "text/plain"},
            timeout=120,
        )
    resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        return []

    return [{"text": text, "metadata": {"source": source}}]


def _extract_epub(file_path: str, source: str) -> list[dict]:
    """Extract per-chapter text from EPUB via ebooklib + BeautifulSoup."""
    book = epub.read_epub(file_path, options={"ignore_ncx": True})
    book_title = book.get_metadata("DC", "title")
    book_title = book_title[0][0] if book_title else source

    # Boilerplate section titles to skip
    skip_titles = {
        "copyright", "dedication", "table of contents", "contents",
        "brief table of contents", "about the cover", "about the cover illustration",
        "title page", "front matter", "half title", "also by",
    }

    sections = []
    for i, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
        soup = BeautifulSoup(item.get_content(), "lxml")
        text = soup.get_text(separator="\n", strip=True)
        if not text or len(text) < 50:
            continue

        # Try to extract chapter title from first heading
        heading = soup.find(["h1", "h2", "h3"])
        chapter_title = heading.get_text(strip=True) if heading else f"Section {i}"

        # Skip boilerplate sections
        if chapter_title.lower().strip() in skip_titles:
            continue

        sections.append({
            "text": text,
            "metadata": {
                "source": source,
                "book_title": book_title,
                "chapter_title": chapter_title,
                "chapter_index": i,
                "source_file": item.get_name(),
            },
        })

    return sections


def supported_extensions() -> set[str]:
    """Return all supported file extensions."""
    return TIKA_EXTENSIONS | {EPUB_EXTENSION}
