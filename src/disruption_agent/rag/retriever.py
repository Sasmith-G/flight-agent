"""RAG layer over fare rules and passenger-rights documents.

Documents are split into section-level chunks (## headings) and ranked with BM25.
BM25 was chosen deliberately for this corpus: policy documents are small, keyword-dense
and legally precise, where lexical matching is accurate, deterministic, and auditable.
The `PolicyRetriever` interface is the seam where a vector store (e.g. ChromaDB +
embeddings) plugs in for larger, semantically diverse corpora.
"""

from __future__ import annotations

import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from ..models import PolicyPassage

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _chunk_markdown(source: str, text: str) -> list[tuple[str, str]]:
    """Split a markdown document into (source#section, section_text) chunks."""
    chunks: list[tuple[str, str]] = []
    current_title = source
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if current_lines:
                chunks.append((current_title, "\n".join(current_lines).strip()))
                current_lines = []
            current_title = f"{source} — {line.lstrip('# ').strip()}"
        else:
            current_lines.append(line)
    if current_lines:
        chunks.append((current_title, "\n".join(current_lines).strip()))
    return [(t, c) for t, c in chunks if c]


class PolicyRetriever:
    def __init__(self, docs_dir: str | Path):
        self.docs_dir = Path(docs_dir)
        self._sources: list[str] = []
        self._chunks: list[str] = []
        for path in sorted(self.docs_dir.glob("*.md")):
            for title, chunk in _chunk_markdown(path.stem, path.read_text()):
                self._sources.append(title)
                self._chunks.append(chunk)
        if not self._chunks:
            raise FileNotFoundError(f"No policy documents found in {self.docs_dir}")
        self._index = BM25Okapi([_tokenize(c) for c in self._chunks])

    def retrieve(self, query: str, top_k: int = 3) -> list[PolicyPassage]:
        scores = self._index.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [
            PolicyPassage(source=self._sources[i], text=self._chunks[i], score=float(scores[i]))
            for i in ranked
            if scores[i] > 0
        ]
