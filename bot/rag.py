"""RAG familial — Knowledge Base avec embeddings Google text-embedding-004.

Charge les fichiers Markdown du dossier knowledge/, les découpe par sections (##),
calcule les embeddings en mémoire, et expose une fonction search() par cosine similarity.
"""

import logging
import re
from pathlib import Path

import numpy as np
from google import genai

from .config import EMBEDDING_MODEL, GEMINI_API_KEY, KNOWLEDGE_DIR

logger = logging.getLogger(__name__)


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
    # Split sur les titres H2 (##) tout en conservant le titre dans le chunk
    sections = re.split(r"(?m)^(?=## )", content)
    for section in sections:
        section = section.strip()
        if section:
            chunks.append({"text": section, "source": source})
    return chunks


class RAGEngine:
    """Moteur RAG en mémoire basé sur text-embedding-004.

    Usage::

        rag = RAGEngine()
        rag.load()
        results = rag.search("La TV ne s'allume pas", top_k=3)
    """

    def __init__(
        self,
        knowledge_dir: Path = KNOWLEDGE_DIR,
        api_key: str = GEMINI_API_KEY,
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._client = genai.Client(api_key=api_key)
        self._chunks: list[dict] = []          # {"text": str, "source": str}
        self._embeddings: list[np.ndarray] = []
        self._loaded = False

    # ── Chargement ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Charge tous les fichiers .md du dossier knowledge/ et calcule les embeddings."""
        md_files = sorted(self._knowledge_dir.glob("*.md"))
        if not md_files:
            logger.warning("No .md files found in %s", self._knowledge_dir)
            return

        all_chunks: list[dict] = []
        for md_path in md_files:
            try:
                content = md_path.read_text(encoding="utf-8")
                chunks = _split_markdown_by_headers(content, source=md_path.name)
                all_chunks.extend(chunks)
                logger.info("Loaded %d chunks from %s", len(chunks), md_path.name)
            except Exception as exc:
                logger.error("Failed to read %s: %s", md_path, exc)

        if not all_chunks:
            logger.warning("No chunks to embed.")
            return

        texts = [c["text"] for c in all_chunks]
        embeddings = self._embed_batch(texts)

        self._chunks = all_chunks
        self._embeddings = embeddings
        self._loaded = True
        logger.info("RAG loaded: %d chunks, %d embeddings", len(self._chunks), len(self._embeddings))

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed une liste de textes via text-embedding-004."""
        embeddings: list[np.ndarray] = []
        for text in texts:
            try:
                response = self._client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=text,
                )
                vec = np.array(response.embeddings[0].values, dtype=np.float32)
                embeddings.append(vec)
            except Exception as exc:
                logger.error("Embedding failed for chunk: %s", exc)
                embeddings.append(np.zeros(768, dtype=np.float32))
        return embeddings

    # ── Recherche ─────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> list[str]:
        """Retourne les top_k chunks les plus pertinents pour la requête.

        Args:
            query: Question ou problème décrit par l'utilisateur.
            top_k: Nombre de chunks à retourner.

        Returns:
            Liste de textes triés par pertinence décroissante.
        """
        if not self._loaded or not self._chunks:
            logger.debug("RAG not loaded or empty — skipping search")
            return []

        try:
            response = self._client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=query,
            )
            query_vec = np.array(response.embeddings[0].values, dtype=np.float32)
        except Exception as exc:
            logger.error("Failed to embed query: %s", exc)
            return []

        scores = [
            _cosine_similarity(query_vec, emb) for emb in self._embeddings
        ]

        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        results = [self._chunks[i]["text"] for i in top_indices if scores[i] > 0.0]
        logger.debug("RAG search returned %d results (top score: %.3f)", len(results), max(scores) if scores else 0)
        return results

    @property
    def is_loaded(self) -> bool:
        """True si le RAG a été chargé avec succès."""
        return self._loaded
