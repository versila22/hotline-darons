"""Persistance des sessions utilisateur en SQLite.

Remplace le dict mémoire du POC par un store durable avec auto-purge.
"""

import json
import logging
import sqlite3
import time as _time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import DB_PATH, CONTEXT_EXPIRATION_MINUTES

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    user_id       INTEGER NOT NULL,
    photo_bytes   BLOB,
    photo_ts      REAL,
    conv_history  TEXT    NOT NULL DEFAULT '[]',
    PRIMARY KEY (user_id)
);
"""


def _now_ts() -> float:
    """Retourne le timestamp UTC courant (float)."""
    return _time.time()


def _expiry_ts() -> float:
    """Retourne le timestamp d'expiration (maintenant - N minutes)."""
    return _now_ts() - CONTEXT_EXPIRATION_MINUTES * 60


class SessionStore:
    """Store SQLite pour le contexte par utilisateur.

    Une seule ligne par user_id. Les photos sont purgées après
    CONTEXT_EXPIRATION_MINUTES minutes. L'historique de conversation
    conserve les N derniers échanges.
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Crée la table si elle n'existe pas encore."""
        conn = self._connect()
        try:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── Photos ────────────────────────────────────────────────────────────────

    def save_photo(self, user_id: int, photo_bytes: bytes) -> None:
        """Persiste une photo (BLOB) associée à un utilisateur."""
        now = _now_ts()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO sessions (user_id, photo_bytes, photo_ts)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    photo_bytes = excluded.photo_bytes,
                    photo_ts    = excluded.photo_ts
                """,
                (user_id, photo_bytes, now),
            )
        finally:
            conn.close()
        logger.debug("Photo saved for user %d", user_id)

    def get_photo(self, user_id: int) -> Optional[bytes]:
        """Retourne la photo si elle n'est pas expirée, sinon None.

        Purge automatiquement la photo si elle est trop ancienne.
        """
        expiry = _expiry_ts()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT photo_bytes, photo_ts FROM sessions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()

        if row is None or row["photo_bytes"] is None:
            return None

        if row["photo_ts"] < expiry:
            logger.info("Photo expired for user %d — purging", user_id)
            self._clear_photo(user_id)
            return None

        # Purge après lecture (one-shot)
        self._clear_photo(user_id)
        return bytes(row["photo_bytes"])

    def _clear_photo(self, user_id: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE sessions SET photo_bytes = NULL, photo_ts = NULL WHERE user_id = ?",
                (user_id,),
            )
        finally:
            conn.close()

    def clear_expired(self) -> int:
        """Supprime toutes les photos expirées. Retourne le nombre de lignes nettoyées."""
        cutoff = _expiry_ts()
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                UPDATE sessions
                SET photo_bytes = NULL, photo_ts = NULL
                WHERE photo_ts IS NOT NULL AND photo_ts < ?
                """,
                (cutoff,),
            )
            count = cursor.rowcount
        finally:
            conn.close()
        if count:
            logger.info("Purged expired photos for %d sessions", count)
        return count

    # ── Historique de conversation ────────────────────────────────────────────

    def save_message(self, user_id: int, role: str, content: str) -> None:
        """Ajoute un message à l'historique de l'utilisateur.

        Args:
            user_id: Identifiant Telegram de l'utilisateur.
            role: "user" ou "assistant".
            content: Texte du message.
        """
        conn = self._connect()
        try:
            # Ensure row exists
            conn.execute(
                "INSERT OR IGNORE INTO sessions (user_id) VALUES (?)", (user_id,)
            )
            row = conn.execute(
                "SELECT conv_history FROM sessions WHERE user_id = ?", (user_id,)
            ).fetchone()

            history: list = json.loads(row["conv_history"]) if row else []
            history.append(
                {
                    "role": role,
                    "content": content,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )

            conn.execute(
                "UPDATE sessions SET conv_history = ? WHERE user_id = ?",
                (json.dumps(history, ensure_ascii=False), user_id),
            )
        finally:
            conn.close()

    def get_history(self, user_id: int, limit: int = 5) -> list[dict]:
        """Retourne les `limit` derniers messages de l'historique.

        Args:
            user_id: Identifiant Telegram.
            limit: Nombre maximum de messages à retourner.

        Returns:
            Liste de dicts {"role": str, "content": str, "ts": str}.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT conv_history FROM sessions WHERE user_id = ?", (user_id,)
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return []

        history: list = json.loads(row["conv_history"])
        return history[-limit:]
