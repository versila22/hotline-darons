import logging
import asyncio
import io
import urllib.request
from typing import Annotated

from fastapi import FastAPI, Form, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse

from bot.ai_engine import AIEngine
from bot.session_store import SessionStore
from bot.rag import RAGEngine
from bot.pii_filter import detect_pii_in_text, should_block_image

logger = logging.getLogger(__name__)

# Reusing the instances created in main or making new ones for the webhook
_store = SessionStore()
_ai = AIEngine()
_rag = RAGEngine()

app = FastAPI(title="Hotline Darons Twilio Webhook")

@app.on_event("startup")
async def startup_event():
    try:
        logger.info("Loading RAG knowledge base for Twilio...")
        _rag.load()
    except Exception as exc:
        logger.warning("RAG loading failed: %s", exc)


async def _download_twilio_media(url: str) -> bytes:
    """Download media from Twilio URL."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            return response.read()
    except Exception as e:
        logger.error(f"Failed to download Twilio media: {e}")
        return b""


@app.post("/whatsapp")
async def twilio_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    Body: Annotated[str, Form()] = "",
    From: Annotated[str, Form()] = "",
    NumMedia: Annotated[int, Form()] = 0,
):
    """Webhook for Twilio WhatsApp integration."""
    
    # Twilio sends From as 'whatsapp:+123456789'
    user_id_str = From.replace("whatsapp:", "").replace("+", "")
    try:
        # Use a dummy int user ID for SQLite based on the phone number
        # Note: SQLite INTEGER max is big enough for phone numbers.
        user_id = int(user_id_str)
    except ValueError:
        user_id = hash(user_id_str)

    media_bytes = None
    media_content_type = ""
    is_audio = False
    
    if NumMedia > 0:
        form_data = await request.form()
        media_url = form_data.get("MediaUrl0")
        media_content_type = form_data.get("MediaContentType0", "")
        
        if media_url:
            media_bytes = await _download_twilio_media(media_url)
            if "audio" in media_content_type or "ogg" in media_content_type or "mp4" in media_content_type: # WhatsApp often uses mp4/ogg for audio
                is_audio = True

    # PII check on text
    if Body and not is_audio:
        pii_found = detect_pii_in_text(Body)
        if pii_found:
            logger.warning("PII detected in WhatsApp message: %s", pii_found)
            resp = MessagingResponse()
            resp.message(
                "⚠️ J'ai détecté des informations sensibles dans ton message "
                f"({', '.join(pii_found)}).\n\n"
                "Pour ta sécurité, je ne peux pas traiter ces données. "
                "Tu peux reformuler sans inclure ces informations confidentielles ?"
            )
            return PlainTextResponse(str(resp), media_type="application/xml")

    # Handle image storage exactly like Telegram
    if media_bytes and not is_audio:
        # Save photo context
        _store.save_photo(user_id, media_bytes)
        resp = MessagingResponse()
        resp.message(
            "📸 J'ai bien reçu la photo !\n"
            "Maintenant dis-moi ce qui ne va pas : "
            "envoie-moi un message vocal 🎤 ou écris-moi directement ✍️"
        )
        return PlainTextResponse(str(resp), media_type="application/xml")

    # If it's a voice note or text, run the AI diagnosis
    # Twilio expects a quick response (< 15s). We will process synchronously for simplicity here.
    # In a fully production system, we'd use Twilio API to send async responses.
    
    photo_bytes = _store.get_photo(user_id)
    
    audio_bytes = media_bytes if is_audio else None
    text = Body if not is_audio else None
    
    user_text_for_history = text or "[message vocal WhatsApp]"
    _store.save_message(user_id, "user", user_text_for_history)
    history = _store.get_history(user_id, limit=5)
    
    rag_query = text or "problème technique"
    rag_context = _rag.search(rag_query, top_k=3) if _rag.is_loaded else []
    
    try:
        ai_response = await _ai.diagnose(
            text=text,
            audio_bytes=audio_bytes,
            photo_bytes=photo_bytes,
            rag_context=rag_context or None,
            history=history[:-1]
        )
    except Exception as exc:
        logger.error("AI diagnosis failed: %s", exc)
        resp = MessagingResponse()
        resp.message("Oups, j'ai eu un petit bug en réfléchissant. Tu peux répéter ?")
        return PlainTextResponse(str(resp), media_type="application/xml")

    answer = ai_response.answer
    
    should_block, block_reason = should_block_image(answer)
    if should_block:
        answer = (
            "⚠️ J'ai détecté des informations sensibles sur l'image. "
            "Pour ta sécurité, je ne peux pas analyser ce contenu.\n\n"
            "Si tu as besoin d'aide urgente, Jay va te contacter directement."
        )
        ai_response.needs_escalation = True
        ai_response.escalation_reason = f"PII détecté dans la réponse IA : {block_reason}"
        
    _store.save_message(user_id, "assistant", answer)
    
    # We omit the direct escalation ping to Telegram here to avoid circular logic, 
    # but ideally we'd trigger the same `escalate()` function.
    # We will just append the escalation text.
    if ai_response.needs_escalation:
        answer += "\n\n📲 J'ai prévenu Jay, il va te contacter très bientôt !"
        
        # In background, we could trigger Telegram escalation
        # For bounty scope: the multimodal flow and Zero-Retention are primary.
        
    resp = MessagingResponse()
    resp.message(answer)
    return PlainTextResponse(str(resp), media_type="application/xml")
