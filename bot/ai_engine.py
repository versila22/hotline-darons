"""Cerveau IA — encapsule Gemini 2.5 Flash multimodal.

Expose une méthode diagnose() qui accepte texte, audio et/ou photo,
injecte le contexte RAG, et retourne une AIResponse structurée
(incluant la détection d'escalade via JSON structuré).
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from .config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── Prompt système ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_BASE = """Tu es l'assistant technique de niveau 1 pour les parents de Jerome (Jay).

RÈGLES STRICTES :
1. Sois extrêmement patient, rassurant et bienveillant. Utilise des mots simples, jamais de jargon technique.
2. Réponds toujours de manière concise, étape par étape, avec des numéros (1., 2., 3.).
3. Si tu vois une information bancaire (IBAN, solde, numéro de carte) ou un mot de passe sur l'image, refuse immédiatement et indique que c'est pour leur sécurité.
4. NE JAMAIS donner de conseils sur les applications bancaires, les virements ou les placements.
5. Sois rassurant même si tu ne peux pas résoudre le problème : "Ne t'inquiète pas, Jay va s'en occuper."

FORMAT DE RÉPONSE OBLIGATOIRE — tu DOIS retourner un JSON valide, rien d'autre :
{
  "answer": "Ta réponse complète ici, en français, bienveillante et claire.",
  "escalate": false,
  "reason": ""
}

Mets escalate à true et remplis reason uniquement si :
- Le problème semble critique (panique, possible fraude, système totalement bloqué)
- La question concerne les finances, les banques ou les virements
- Tu ne peux vraiment pas aider sans informations supplémentaires urgentes
"""

_RAG_CONTEXT_TEMPLATE = """
CONTEXTE SPÉCIFIQUE DE LA FAMILLE (utilise ces informations en priorité) :
---
{rag_context}
---
"""


# ── Data models ───────────────────────────────────────────────────────────────


@dataclass
class AIResponse:
    """Réponse structurée de l'IA.

    Attributes:
        answer: Réponse textuelle à envoyer à l'utilisateur.
        needs_escalation: True si le problème doit être escaladé vers Jerome.
        escalation_reason: Motif de l'escalade (vide si pas d'escalade).
    """

    answer: str
    needs_escalation: bool = False
    escalation_reason: str = ""


# ── Moteur ────────────────────────────────────────────────────────────────────


class AIEngine:
    """Encapsule le client Gemini 2.5 Flash pour le diagnostic multimodal."""

    def __init__(self, api_key: str = GEMINI_API_KEY) -> None:
        self._client = genai.Client(api_key=api_key)

    async def diagnose(
        self,
        text: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        photo_bytes: Optional[bytes] = None,
        rag_context: Optional[list[str]] = None,
        history: Optional[list[dict]] = None,
    ) -> AIResponse:
        """Lance un diagnostic multimodal via Gemini.

        Args:
            text: Message texte de l'utilisateur.
            audio_bytes: Données audio brutes (OGG depuis Telegram).
            photo_bytes: Données image brutes (JPEG).
            rag_context: Liste de chunks issus du RAG à injecter dans le prompt.
            history: Historique de conversation [{role, content}].

        Returns:
            AIResponse avec la réponse et le flag d'escalade.
        """
        return await asyncio.to_thread(
            self._diagnose_sync,
            text,
            audio_bytes,
            photo_bytes,
            rag_context,
            history,
        )

    def _diagnose_sync(
        self,
        text: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        photo_bytes: Optional[bytes] = None,
        rag_context: Optional[list[str]] = None,
        history: Optional[list[dict]] = None,
    ) -> AIResponse:
        """Version synchrone exécutée dans un thread pour éviter de bloquer l'event loop."""
        system_prompt = _SYSTEM_PROMPT_BASE

        # Injection du contexte RAG
        if rag_context:
            combined = "\n\n".join(rag_context)
            system_prompt += _RAG_CONTEXT_TEMPLATE.format(rag_context=combined)

        contents: list = [types.Part.from_text(text=system_prompt)]

        # Historique de conversation (optionnel)
        if history:
            history_text = "\n".join(
                f"[{msg['role'].upper()}]: {msg['content']}" for msg in history
            )
            contents.append(
                types.Part.from_text(text=f"\nHistorique récent :\n{history_text}\n")
            )

        # Photo
        if photo_bytes:
            contents.append(
                types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg")
            )

        # Audio
        if audio_bytes:
            contents.append(
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")
            )

        # Texte utilisateur
        if text:
            contents.append(types.Part.from_text(text=text))

        if len(contents) == 1:
            # Rien à analyser
            return AIResponse(
                answer="Je n'ai pas reçu de message à analyser. Tu peux m'envoyer un texte, une note vocale ou une photo !",
                needs_escalation=False,
            )

        try:
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
            )
            raw = response.text.strip()
            return self._parse_response(raw)

        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            return AIResponse(
                answer="Oups, j'ai eu un petit bug en réfléchissant. Tu peux répéter ?",
                needs_escalation=False,
            )

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> AIResponse:
        """Parse la réponse JSON de Gemini.

        Tente d'extraire le JSON structuré. Si le parsing échoue,
        utilise le texte brut comme réponse sans escalade.
        """
        # Extrait un bloc JSON si Gemini a encapsulé dans des backticks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if json_match:
            raw = json_match.group(1)

        # Recherche d'un objet JSON direct
        obj_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if obj_match:
            raw = obj_match.group(0)

        try:
            data = json.loads(raw)
            answer = data.get("answer", "").strip()
            escalate = bool(data.get("escalate", False))
            reason = data.get("reason", "").strip()

            if not answer:
                raise ValueError("Empty answer field")

            return AIResponse(
                answer=answer,
                needs_escalation=escalate,
                escalation_reason=reason,
            )

        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse Gemini JSON response: %s — using raw text", exc)
            # Fallback : utiliser le texte brut
            return AIResponse(
                answer=raw or "Je n'ai pas pu analyser la situation. Peux-tu reformuler ?",
                needs_escalation=False,
            )
