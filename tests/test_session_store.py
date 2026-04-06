"""Tests unitaires pour bot/session_store.py."""

import json
import os
import sqlite3
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.session_store import MAX_STORED_MESSAGES, SessionStore


@pytest.fixture
def store(tmp_path):
    """SessionStore avec une base de données temporaire."""
    db_path = str(tmp_path / "test.db")
    return SessionStore(db_path=db_path)


# ── Photos ────────────────────────────────────────────────────────────────────


class TestPhotos:
    """Tests save/get/expire pour les photos."""

    def test_save_and_get_photo(self, store):
        photo = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # Fake JPEG
        store.save_photo(user_id=42, photo_bytes=photo)
        result = store.get_photo(user_id=42)
        assert result == photo

    def test_photo_is_none_for_unknown_user(self, store):
        assert store.get_photo(user_id=9999) is None

    def test_photo_consumed_after_get(self, store):
        """La photo doit être supprimée après avoir été lue (one-shot)."""
        photo = b"\xff\xd8\xff" + b"\x01" * 50
        store.save_photo(user_id=1, photo_bytes=photo)
        result1 = store.get_photo(user_id=1)
        result2 = store.get_photo(user_id=1)
        assert result1 is not None
        assert result2 is None

    def test_photo_expires_after_timeout(self, store):
        """Une photo trop vieille doit être ignorée."""
        photo = b"\xff\xd8\xff" + b"\x02" * 50
        store.save_photo(user_id=2, photo_bytes=photo)

        # Simule une expiration en patching CONTEXT_EXPIRATION_MINUTES
        with patch("bot.session_store.CONTEXT_EXPIRATION_MINUTES", 0):
            time.sleep(0.01)  # Laisse passer quelques ms
            result = store.get_photo(user_id=2)

        assert result is None

    def test_overwrite_photo(self, store):
        """Sauvegarder deux fois écrase la première photo."""
        photo1 = b"photo1"
        photo2 = b"photo2_newer"
        store.save_photo(user_id=3, photo_bytes=photo1)
        store.save_photo(user_id=3, photo_bytes=photo2)
        result = store.get_photo(user_id=3)
        assert result == photo2


# ── clear_expired ─────────────────────────────────────────────────────────────


class TestClearExpired:
    def test_clear_expired_returns_int(self, store):
        count = store.clear_expired()
        assert isinstance(count, int)
        assert count >= 0

    def test_clear_expired_removes_old_photos(self, store):
        store.save_photo(user_id=10, photo_bytes=b"old_photo")
        with patch("bot.session_store.CONTEXT_EXPIRATION_MINUTES", 0):
            time.sleep(0.01)
            count = store.clear_expired()

        assert count >= 1
        assert store.get_photo(user_id=10) is None


# ── Historique de conversation ────────────────────────────────────────────────


class TestConversationHistory:
    def test_save_and_get_message(self, store):
        store.save_message(user_id=5, role="user", content="Bonjour, j'ai un problème.")
        history = store.get_history(user_id=5)
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Bonjour, j'ai un problème."

    def test_history_empty_for_unknown_user(self, store):
        history = store.get_history(user_id=9999)
        assert history == []

    def test_history_limit(self, store):
        for i in range(10):
            store.save_message(user_id=6, role="user", content=f"Message {i}")
        history = store.get_history(user_id=6, limit=5)
        assert len(history) == 5

    def test_history_order(self, store):
        """Les messages doivent être dans l'ordre chronologique."""
        store.save_message(user_id=7, role="user", content="Premier")
        store.save_message(user_id=7, role="assistant", content="Réponse")
        store.save_message(user_id=7, role="user", content="Deuxième")

        history = store.get_history(user_id=7)
        assert history[0]["content"] == "Premier"
        assert history[-1]["content"] == "Deuxième"

    def test_history_roles(self, store):
        store.save_message(user_id=8, role="user", content="Question")
        store.save_message(user_id=8, role="assistant", content="Réponse")
        history = store.get_history(user_id=8)
        roles = [m["role"] for m in history]
        assert "user" in roles
        assert "assistant" in roles

    def test_history_default_limit(self, store):
        """Limite par défaut = 5."""
        for i in range(10):
            store.save_message(user_id=9, role="user", content=f"msg {i}")
        history = store.get_history(user_id=9)
        assert len(history) == 5

    def test_history_storage_is_bounded(self, store):
        for i in range(MAX_STORED_MESSAGES + 7):
            store.save_message(user_id=11, role="user", content=f"msg {i}")

        with sqlite3.connect(store._db_path) as conn:
            row = conn.execute(
                "SELECT conv_history FROM sessions WHERE user_id = ?",
                (11,),
            ).fetchone()

        stored_history = json.loads(row[0])
        assert len(stored_history) == MAX_STORED_MESSAGES
        assert stored_history[0]["content"] == "msg 7"
        assert stored_history[-1]["content"] == f"msg {MAX_STORED_MESSAGES + 6}"

    def test_multiple_users_isolated(self, store):
        """Les historiques de deux utilisateurs sont bien séparés."""
        store.save_message(user_id=100, role="user", content="User 100")
        store.save_message(user_id=200, role="user", content="User 200")

        h100 = store.get_history(user_id=100)
        h200 = store.get_history(user_id=200)

        assert h100[0]["content"] == "User 100"
        assert h200[0]["content"] == "User 200"
