"""RAG familial — Knowledge Base avec embeddings Google.

Charge les fichiers Markdown du dossier knowledge/, les découpe par sections (##),
calcule les embeddings en mémoire, et expose une fonction search() par cosine similarity.
Les embeddings sont mis en cache sur disque pour éviter de les recalculer à chaque boot.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
from google import genai

from .config import EMBEDDING_MODEL, GEMINI_API_KEY, KNOWLEDGE_DIR

logger = logging.getLogger(__name__)

_CACHE_FILENAME = "embeddings_cache.npy"
_CACHE_META_FILENAME = "embeddings_cache_meta.json"
_CACHE_CHUNKS_FILENAME = "embeddings_cache_chunks.json"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _split_markdown_by_headers(content: str, source: str) -> list[dict]:
    """Découpe un fichier Markdown en chunks par headers de niveau ## (H2).

    Chaque chunk est un dict {"text": str, "source": str}.
    """
    chunks: list[dict] = []
    sections = re.split(r"(?m)^(?=## )", content)
    for section in sections:
        section = section.strip()
        if section:
            chunks.append({"text": section, "source": source})
    return chunks


class RAGEngine:
    """Moteur RAG en mémoire basé sur Gemini embeddings."""

    def __init__(
        self,
        knowledge_dir: Path = KNOWLEDGE_DIR,
        api_key: str = GEMINI_API_KEY,
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._client = genai.Client(api_key=api_key)
        self._chunks: list[dict] = []
        self._embeddings: list[np.ndarray] = []
        self._loaded = False
        self._cache_dir = self._knowledge_dir.parent / "data"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self._cache_dir / _CACHE_FILENAME
        self._cache_meta_path = self._cache_dir / _CACHE_META_FILENAME
        self._cache_chunks_path = self._cache_dir / _CACHE_CHUNKS_FILENAME

    def load(self) -> None:
        """Charge tous les fichiers .md du dossier knowledge/ et calcule les embeddings."""
        md_files = sorted(self._knowledge_dir.glob("*.md"))
        if not md_files:
            logger.warning("No .md files found in %s", self._knowledge_dir)
            return

        all_chunks = self._load_chunks(md_files)
        if not all_chunks:
            logger.warning("No chunks to embed.")
            return

        knowledge_state = self._knowledge_state(md_files)
        cached = self._load_cache(knowledge_state)

        self._chunks = all_chunks
        if cached is not None and len(cached) == len(all_chunks):
            self._embeddings = cached
            self._loaded = True
            logger.info("RAG loaded from cache: %d chunks", len(self._chunks))
            return

        texts = [c["text"] for c in all_chunks]
        embeddings = self._embed_batch(texts)
        self._embeddings = embeddings
        self._loaded = True
        self._save_cache(knowledge_state, all_chunks, embeddings)
        logger.info("RAG loaded: %d chunks, %d embeddings", len(self._chunks), len(self._embeddings))

    def _load_chunks(self, md_files: list[Path]) -> list[dict]:
        all_chunks: list[dict] = []
        for md_path in md_files:
            try:
                content = md_path.read_text(encoding="utf-8")
                chunks = _split_markdown_by_headers(content, source=md_path.name)
                all_chunks.extend(chunks)
                logger.info("Loaded %d chunks from %s", len(chunks), md_path.name)
            except Exception as exc:
                logger.error("Failed to read %s: %s", md_path, exc)
        return all_chunks

    def _knowledge_state(self, md_files: list[Path]) -> dict[str, Any]:
        return {
            "files": [
                {
                    "name": path.name,
                    "mtime_ns": path.stat().st_mtime_ns,
                }
                for path in md_files
            ]
        }

    def _load_cache(self, knowledge_state: dict[str, Any]) -> list[np.ndarray] | None:
        if not (
            self._cache_path.exists()
            and self._cache_meta_path.exists()
            and self._cache_chunks_path.exists()
        ):
            return None

        try:
            meta = json.loads(self._cache_meta_path.read_text(encoding="utf-8"))
            cached_chunks = json.loads(self._cache_chunks_path.read_text(encoding="utf-8"))
            if meta.get("knowledge_state") != knowledge_state:
                logger.info("RAG cache invalidated: knowledge base changed")
                return None

            embeddings_array = np.load(self._cache_path)
            if len(cached_chunks) != len(embeddings_array):
                logger.warning("RAG cache invalid: chunk count mismatch")
                return None

            return [np.array(row, dtype=np.float32) for row in embeddings_array]
        except Exception as exc:
            logger.warning("Failed to load RAG cache: %s", exc)
            return None

    def _save_cache(
        self,
        knowledge_state: dict[str, Any],
        chunks: list[dict],
        embeddings: list[np.ndarray],
    ) -> None:
        try:
            np.save(self._cache_path, np.stack(embeddings).astype(np.float32))
            self._cache_meta_path.write_text(
                json.dumps({"knowledge_state": knowledge_state}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._cache_chunks_path.write_text(
                json.dumps(chunks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save RAG cache: %s", exc)

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed une liste de textes via Gemini embeddings."""
        embeddings: list[np.ndarray] = []
        for text in texts:
            embeddings.append(self._embed_text(text))
        return embeddings

    def _embed_text(self, text: str) -> np.ndarray:
        try:
            response = self._client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
            )
            return np.array(response.embeddings[0].values, dtype=np.float32)
        except Exception as exc:
            logger.error("Embedding failed for text: %s", exc)
            return np.zeros(768, dtype=np.float32)

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """Retourne les top_k chunks les plus pertinents pour la requête."""
        if not self._loaded or not self._chunks:
            logger.debug("RAG not loaded or empty — skipping search")
            return []

        query_vec = self._embed_text(query)
        if np.linalg.norm(query_vec) == 0:
            logger.debug("Query embedding is empty — returning no context")
            return []

        scores = [_cosine_similarity(query_vec, emb) for emb in self._embeddings]
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = [self._chunks[i]["text"] for i in top_indices if scores[i] > 0.0]
        logger.debug(
            "RAG search returned %d results (top score: %.3f)",
            len(results),
            max(scores) if scores else 0,
        )
        return results

    @property
    def is_loaded(self) -> bool:
        """True si le RAG a été chargé avec succès."""
        return self._loaded
