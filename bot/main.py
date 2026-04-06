"""Entry point du bot Telegram Hotline Darons.

Handlers :
- /start  : Message d'accueil chaleureux
- /status : Vérification que le bot est opérationnel
- photo   : Stockage en SQLite + accusé de réception
- voice   : Diagnostic Gemini multimodal
- text    : Diagnostic Gemini texte
"""

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .ai_engine import AIEngine
from .config import (
    DB_PATH,
    KNOWLEDGE_DIR,
    MAX_PHOTO_SIZE_MB,
    TELEGRAM_BOT_TOKEN,
)
from .escalation import escalate
from .pii_filter import detect_pii_in_text, should_block_image
from .rag import RAGEngine
from .session_store import SessionStore

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Singletons partagés ───────────────────────────────────────────────────────

_store = SessionStore(DB_PATH)
_rag = RAGEngine(KNOWLEDGE_DIR)
_ai = AIEngine()

# ── Handlers ──────────────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start — message d'accueil."""
    first_name = update.effective_user.first_name if update.effective_user else "toi"
    await update.message.reply_text(
        f"👋 Coucou {first_name} ! Je suis l'assistant de Jay.\n\n"
        "Si tu as un souci avec la télé 📺, l'ordinateur 💻 ou le téléphone 📱, "
        "je suis là pour t'aider !\n\n"
        "Tu peux :\n"
        "• M'envoyer une 📸 photo de l'écran\n"
        "• Me laisser un 🎤 message vocal\n"
        "• M'écrire directement\n\n"
        "On va résoudre ça ensemble, pas de panique ! 😊"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /status — vérification de santé."""
    rag_status = "✅" if _rag.is_loaded else "⚠️ base de connaissances non chargée"
    await update.message.reply_text(
        f"✅ Je suis opérationnel !\n"
        f"📚 Base de connaissances : {rag_status}\n\n"
        "Envoie-moi une photo ou un message vocal si tu as un souci."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stocke la photo en SQLite et envoie un accusé de réception."""
    user_id = update.effective_user.id

    photo = update.message.photo[-1]  # Meilleure résolution disponible

    # Vérification taille
    file_size_mb = (photo.file_size or 0) / (1024 * 1024)
    if file_size_mb > MAX_PHOTO_SIZE_MB:
        await update.message.reply_text(
            f"⚠️ La photo est trop grande ({file_size_mb:.1f} Mo). "
            f"Je peux traiter des photos jusqu'à {MAX_PHOTO_SIZE_MB} Mo."
        )
        return

    try:
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        _store.save_photo(user_id, bytes(photo_bytes))
        logger.info("Photo saved for user %d (%d bytes)", user_id, len(photo_bytes))

        await update.message.reply_text(
            "📸 J'ai bien reçu la photo !\n"
            "Maintenant dis-moi ce qui ne va pas : "
            "envoie-moi un message vocal 🎤 ou écris-moi directement ✍️"
        )
    except Exception as exc:
        logger.error("Photo handling failed: %s", exc)
        await update.message.reply_text(
            "Oups, j'ai eu un petit souci avec la photo. Tu peux la renvoyer ?"
        )


async def handle_voice_or_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Traitement principal : RAG + Gemini + PII check + escalade éventuelle."""
    user_id = update.effective_user.id
    user = update.effective_user

    # Accusé de réception immédiat (bonne UX)
    status_msg = await update.message.reply_text(
        "Je regarde ça, donne-moi une seconde ⏳"
    )

    # ── Récupération de la photo en contexte ──────────────────────────────────
    photo_bytes = _store.get_photo(user_id)

    # ── Récupération de l'audio ou du texte ───────────────────────────────────
    audio_bytes: bytes | None = None
    text: str | None = None

    if update.message.voice:
        try:
            voice_file = await update.message.voice.get_file()
            audio_bytes = bytes(await voice_file.download_as_bytearray())
        except Exception as exc:
            logger.error("Failed to download voice: %s", exc)
            await status_msg.edit_text(
                "Oups, je n'ai pas pu récupérer le message vocal. Tu peux le renvoyer ?"
            )
            return

    elif update.message.text:
        text = update.message.text

        # PII check sur le texte entrant
        pii_found = detect_pii_in_text(text)
        if pii_found:
            logger.warning("PII detected in user message: %s", pii_found)
            await status_msg.edit_text(
                "⚠️ J'ai détecté des informations sensibles dans ton message "
                f"({', '.join(pii_found)}).\n\n"
                "Pour ta sécurité, je ne peux pas traiter ces données. "
                "Tu peux reformuler sans inclure ces informations confidentielles ?"
            )
            return

    # Sauvegarde du message utilisateur
    user_text_for_history = text or "[message vocal]"
    _store.save_message(user_id, "user", user_text_for_history)
    history = _store.get_history(user_id, limit=5)

    # ── RAG search ────────────────────────────────────────────────────────────
    rag_query = text or "problème technique"
    rag_context = _rag.search(rag_query, top_k=3) if _rag.is_loaded else []

    # ── Diagnostic Gemini ─────────────────────────────────────────────────────
    try:
        ai_response = await _ai.diagnose(
            text=text,
            audio_bytes=audio_bytes,
            photo_bytes=photo_bytes,
            rag_context=rag_context or None,
            history=history[:-1],  # Exclure le dernier message (déjà dans le prompt)
        )
    except Exception as exc:
        logger.error("AI diagnosis failed: %s", exc)
        await status_msg.edit_text(
            "Oups, j'ai eu un petit bug en réfléchissant. Tu peux répéter ?"
        )
        return

    answer = ai_response.answer

    # ── PII check sur la réponse ──────────────────────────────────────────────
    should_block, block_reason = should_block_image(answer)
    if should_block:
        logger.warning("PII detected in AI response: %s", block_reason)
        answer = (
            "⚠️ J'ai détecté des informations sensibles sur l'image. "
            "Pour ta sécurité, je ne peux pas analyser ce contenu.\n\n"
            "Si tu as besoin d'aide urgente, Jay va te contacter directement."
        )
        ai_response.needs_escalation = True
        ai_response.escalation_reason = f"PII détecté dans la réponse IA : {block_reason}"

    # Sauvegarde de la réponse
    _store.save_message(user_id, "assistant", answer)

    # ── Escalade ──────────────────────────────────────────────────────────────
    if ai_response.needs_escalation:
        user_info = {
            "id": user.id,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or "",
        }
        escalation_summary = ai_response.escalation_reason or "Problème nécessitant une intervention humaine"

        await escalate(
            bot=context.bot,
            user_info=user_info,
            summary=escalation_summary,
            photo_bytes=photo_bytes,
        )

        await status_msg.edit_text(
            f"{answer}\n\n"
            "📲 J'ai prévenu Jay, il va te contacter très bientôt !"
        )
    else:
        await status_msg.edit_text(answer)

    # Purge périodique des sessions expirées (fire and forget)
    asyncio.create_task(_async_cleanup())


async def _async_cleanup() -> None:
    """Purge les photos expirées en arrière-plan."""
    try:
        _store.clear_expired()
    except Exception as exc:
        logger.debug("Cleanup error (non-critical): %s", exc)


# ── Bootstrap ─────────────────────────────────────────────────────────────────


def main() -> None:
    """Point d'entrée principal du bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    # Chargement du RAG au démarrage
    try:
        logger.info("Loading RAG knowledge base from %s …", KNOWLEDGE_DIR)
        _rag.load()
    except Exception as exc:
        logger.warning("RAG loading failed (non-critical): %s", exc)

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(
        MessageHandler(
            filters.VOICE | (filters.TEXT & ~filters.COMMAND),
            handle_voice_or_text,
        )
    )

    logger.info("🤖 Hotline Darons bot started. Polling for updates…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
