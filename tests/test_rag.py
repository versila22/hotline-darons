"""Tests unitaires pour bot/rag.py."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.rag import RAGEngine


class TestRAGEngine:
    def test_rag_query_returns_relevant_context(self, tmp_path):
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "famille_jacq.md").write_text(
            """# Base familiale

## Télévision
La télé Samsung du salon redémarre en maintenant power 5 secondes.

## Internet
La Livebox 5 redémarre en débranchant l'alimentation 30 secondes.
""",
            encoding="utf-8",
        )

        rag = RAGEngine(knowledge_dir=knowledge_dir, api_key="test")

        vectors = {
            "## Télévision\nLa télé Samsung du salon redémarre en maintenant power 5 secondes.": np.array([1.0, 0.0], dtype=np.float32),
            "## Internet\nLa Livebox 5 redémarre en débranchant l'alimentation 30 secondes.": np.array([0.0, 1.0], dtype=np.float32),
            "Comment redémarrer la box internet ?": np.array([0.0, 1.0], dtype=np.float32),
        }
        rag._embed_text = lambda text: vectors.get(text, np.zeros(2, dtype=np.float32))

        rag.load()
        results = rag.search("Comment redémarrer la box internet ?", top_k=1)

        assert len(results) == 1
        assert "Livebox 5" in results[0]
        assert (knowledge_dir.parent / "data" / "embeddings_cache.npy").exists()

    def test_rag_handles_empty_knowledge_base(self, tmp_path):
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()

        rag = RAGEngine(knowledge_dir=knowledge_dir, api_key="test")
        rag.load()

        assert rag.is_loaded is False
        assert rag.search("La télé ne marche plus") == []
