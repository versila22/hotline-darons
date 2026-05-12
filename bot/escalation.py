"""Module d'escalade — forward les alertes vers Jerome.

Quand le bot ne peut pas résoudre un problème ou détecte une situation critique,
il envoie un résumé formaté à ESCALATION_CHAT_ID (le Telegram ID de Jerome).
"""

import io
import logging
from datetime import datetime, timezone
import sqlite3

from telegram import Bot
from telegram.constants import ParseMode

from .config import ESCALATION_CHAT_ID
from bot import config

logger = logging.getLogger(__name__)


def _save_escalation_to_db(user_info: dict, summary: str, has_photo: bool) -> None:
    """Enregistre l'escalade dans la base SQLite pour le dashboard."""
    try:
        conn = sqlite3.connect(config.DB_PATH, isolation_level=None)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                summary TEXT NOT NULL,
                has_photo BOOLEAN NOT NULL DEFAULT 0
            )
        ''')
        
        now_iso = datetime.now(timezone.utc).isoformat()
        user_id = user_info.get("id", 0)
        user_name = _format_user_name(user_info)
        
        conn.execute('''
            INSERT INTO escalations (timestamp, user_id, user_name, summary, has_photo)
            VALUES (?, ?, ?, ?, ?)
        ''', (now_iso, user_id, user_name, summary, has_photo))
        
        conn.close()
    except Exception as exc:
        logger.error("Failed to save escalation to DB: %s", exc)


async def escalate(
    bot: Bot,
    user_info: dict,
    summary: str,
    photo_bytes: bytes | None = None,
) -> bool:
    """Envoie une alerte d'escalade à Jerome.

    Args:
        bot: Instance du bot Telegram.
        user_info: Informations sur l'utilisateur (id, first_name, last_name, username).
        summary: Résumé du problème (fourni par Gemini ou construit manuellement).
        photo_bytes: Photo associée au problème (optionnel).

    Returns:
        True si l'envoi a réussi, False sinon.
    """
    if not ESCALATION_CHAT_ID:
        logger.error("ESCALATION_CHAT_ID not configured — cannot escalate")
        return False

    name = _format_user_name(user_info)
    timestamp = datetime.now().strftime("%d/%m/%Y à %H:%M")

    message_text = (
        f"🚨 *Escalade Hotline Darons*\n"
        f"👤 Parent : {name}\n"
        f"📋 Résumé : {summary}\n"
        f"🕐 {timestamp}"
    )

    # Log to database for Streamlit Dashboard
    _save_escalation_to_db(user_info, summary, bool(photo_bytes))

    try:
        if photo_bytes:
            await bot.send_photo(
                chat_id=ESCALATION_CHAT_ID,
                photo=io.BytesIO(photo_bytes),
                caption=message_text,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await bot.send_message(
                chat_id=ESCALATION_CHAT_ID,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN,
            )

        logger.info("Escalation sent to %d for user %s", ESCALATION_CHAT_ID, name)
        return True

    except Exception as exc:
        logger.error("Failed to send escalation: %s", exc)
        return False


def _format_user_name(user_info: dict) -> str:
    """Formate le nom d'un utilisateur Telegram en chaîne lisible."""
    first = user_info.get("first_name", "")
    last = user_info.get("last_name", "")
    username = user_info.get("username", "")
    user_id = user_info.get("id", "?")

    full_name = f"{first} {last}".strip() or username or f"Utilisateur #{user_id}"
    if username:
        return f"{full_name} (@{username})"
    return full_name
