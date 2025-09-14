# ingest/utils.py
import re
from typing import List

def clean_text(text: str) -> str:
    # Normalize whitespace, remove weird control chars
    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Chunk by words (approx chunk_size words). Returns list of chunks with overlap.
    chunk_size and overlap are in words, not tokens — simple and robust.
    """
    words = text.split()
    chunks = []
    i = 0
    n = len(words)
    while i < n:
        j = i + chunk_size
        chunk = " ".join(words[i: j])
        chunks.append(chunk)
        i = j - overlap
    return [clean_text(c) for c in chunks if len(c.strip()) > 0]
