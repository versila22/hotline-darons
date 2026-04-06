"""Entry point du bot Telegram Hotline Darons.

Handlers :
- /start  : Message d'accueil chaleureux
- /aide   : Aide et commandes disponibles
- /reset  : Réinitialisation du contexte utilisateur
- /status : Vérification que le bot est opérationnel
- photo   : Stockage en SQLite + accusé de réception
- voice   : Diagnostic Gemini multimodal
- text    : Diagnostic Gemini texte
"""

import asyncio
import logging
import sys
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
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

_MAX_TELEGRAM_MESSAGE_LEN = 2000

# ── Helpers ───────────────────────────────────────────────────────────────────


def _quick_actions_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ C'est réglé", callback_data="resolved")],
            [InlineKeyboardButton("❓ Autre question", callback_data="question")],
            [InlineKeyboardButton("👤 Parler à un humain", callback_data="escalate")],
        ]
    )


def _paginate_text(text: str, max_len: int = _MAX_TELEGRAM_MESSAGE_LEN) -> list[str]:
    """Découpe un texte long en messages Telegram raisonnables."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_len:
        split_at = remaining.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = max_len

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _store_pending_pages(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, pages: list[str]
) -> str:
    token = uuid.uuid4().hex[:12]
    pending_pages = context.user_data.setdefault("pending_pages", {})
    pending_pages[token] = {"user_id": user_id, "pages": pages}
    return token


async def _send_answer_with_ui(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    answer: str,
    *,
    status_msg=None,
) -> None:
    """Envoie une réponse avec pagination éventuelle et boutons rapides."""
    pages = _paginate_text(answer)
    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0

    if len(pages) == 1:
        if status_msg:
            await status_msg.edit_text(answer, reply_markup=_quick_actions_markup())
        else:
            await message.reply_text(answer, reply_markup=_quick_actions_markup())
        return

    token = _store_pending_pages(context, user_id, pages[1:])
    first_markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Suite →", callback_data=f"next:{token}")],
            [InlineKeyboardButton("👤 Parler à un humain", callback_data="escalate")],
        ]
    )

    first_page = f"{pages[0]}\n\n(1/{len(pages)})"
    if status_msg:
        await status_msg.edit_text(first_page, reply_markup=first_markup)
    else:
        await message.reply_text(first_page, reply_markup=first_markup)


async def _trigger_manual_escalation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    summary: str,
) -> bool:
    user = update.effective_user
    if not user:
        return False

    user_info = {
        "id": user.id,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "username": user.username or "",
    }
    photo_bytes = _store.get_photo(user.id)
    return await escalate(
        bot=context.bot,
        user_info=user_info,
        summary=summary,
        photo_bytes=photo_bytes,
    )


# ── Handlers ──────────────────────────────────────────────────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /start — message d'accueil avec actions rapides."""
    welcome_text = (
        "👋 Bonjour ! Je suis l'assistant de la *Hotline Darons*.\n\n"
        "Je suis là pour vous aider avec les défis du quotidien avec les aînés.\n\n"
        "💬 Décrivez simplement votre situation et je vous accompagne.\n"
        "📸 Vous pouvez aussi envoyer une photo si c'est utile.\n\n"
        "_Pour parler à un humain, tapez /aide_"
    )
    keyboard = [
        [InlineKeyboardButton("🆘 Besoin d'aide urgente", callback_data="urgent")],
        [InlineKeyboardButton("💬 Poser une question", callback_data="question")],
        [InlineKeyboardButton("👤 Parler à un humain", callback_data="escalate")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /status — vérification de santé."""
    rag_status = "✅" if _rag.is_loaded else "⚠️ base de connaissances non chargée"
    await update.message.reply_text(
        f"✅ Je suis opérationnel !\n"
        f"📚 Base de connaissances : {rag_status}\n\n"
        "Envoie-moi une photo ou un message vocal si tu as un souci."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /aide — aide utilisateur."""
    await update.message.reply_text(
        "🧭 *Aide Hotline Darons*\n\n"
        "Tu peux :\n"
        "• décrire ton problème avec un message\n"
        "• envoyer une photo 📸\n"
        "• envoyer un message vocal 🎤\n\n"
        "Commandes disponibles :\n"
        "/start — voir l'accueil\n"
        "/aide — afficher cette aide\n"
        "/reset — effacer notre conversation et repartir à zéro\n"
        "/status — vérifier que le bot fonctionne\n\n"
        "Si c'est urgent ou si tu préfères, je peux aussi prévenir un humain 👤",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("👤 Parler à un humain", callback_data="escalate")]]
        ),
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /reset — purge la session utilisateur."""
    user_id = update.effective_user.id
    _store.clear_session(user_id)
    context.user_data.pop("pending_pages", None)
    await update.message.reply_text(
        "🧹 C'est remis à zéro. On repart sur une conversation toute neuve !"
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestionnaire des boutons inline."""
    query = update.callback_query
    await query.answer()

    if query.data == "urgent":
        await query.message.reply_text(
            "🆘 Je comprends que c'est urgent. Décrivez la situation..."
        )
        escalated = await _trigger_manual_escalation(
            update,
            context,
            summary="L'utilisateur a indiqué via le bouton que la situation est urgente.",
        )
        if escalated:
            await query.message.reply_text(
                "👤 J'ai aussi prévenu un humain pour accélérer la prise en charge."
            )

    elif query.data == "question":
        await query.message.reply_text("💬 Quelle est votre question ?")

    elif query.data == "escalate":
        escalated = await _trigger_manual_escalation(
            update,
            context,
            summary="L'utilisateur a demandé à parler à un humain.",
        )
        if escalated:
            await query.message.reply_text(
                "👤 Je vous mets en contact avec un humain..."
            )
        else:
            await query.message.reply_text(
                "⚠️ Je n'ai pas réussi à prévenir un humain tout de suite, mais vous pouvez quand même continuer à me décrire la situation."
            )

    elif query.data == "resolved":
        await query.message.reply_text(
            "✨ Super, content que ce soit réglé ! Si besoin, je suis là pour une autre question."
        )

    elif query.data and query.data.startswith("next:"):
        token = query.data.split(":", 1)[1]
        pending_pages = context.user_data.get("pending_pages", {})
        entry = pending_pages.get(token)
        current_user_id = update.effective_user.id if update.effective_user else None

        if (
            not entry
            or not entry.get("pages")
            or entry.get("user_id") != current_user_id
        ):
            await query.message.reply_text(
                "Je n'ai plus la suite sous la main. Tu peux me redemander si besoin 🙂"
            )
            return

        next_page = entry["pages"].pop(0)
        remaining_count = len(entry["pages"])

        if remaining_count:
            markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Suite →", callback_data=f"next:{token}")],
                    [InlineKeyboardButton("👤 Parler à un humain", callback_data="escalate")],
                ]
            )
        else:
            pending_pages.pop(token, None)
            markup = _quick_actions_markup()

        suffix = (
            f"\n\n(Suite, encore {remaining_count} message(s))"
            if remaining_count
            else "\n\n(Fin de la réponse)"
        )
        await query.message.reply_text(next_page + suffix, reply_markup=markup)


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
        escalation_summary = (
            ai_response.escalation_reason
            or "Problème nécessitant une intervention humaine"
        )

        await escalate(
            bot=context.bot,
            user_info=user_info,
            summary=escalation_summary,
            photo_bytes=photo_bytes,
        )

        await _send_answer_with_ui(
            update,
            context,
            f"{answer}\n\n📲 J'ai prévenu Jay, il va te contacter très bientôt !",
            status_msg=status_msg,
        )
    else:
        await _send_answer_with_ui(
            update,
            context,
            answer,
            status_msg=status_msg,
        )

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

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("aide", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CallbackQueryHandler(button_callback))
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
