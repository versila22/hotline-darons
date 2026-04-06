"""Détection de données personnelles sensibles (PII).

Deux niveaux de contrôle :
1. `detect_pii_in_text` — regex sur du texte brut.
2. `should_block_image` — analyse la description retournée par Gemini pour voir
   si des données sensibles ont été lues sur l'image.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Patterns regex ────────────────────────────────────────────────────────────

# IBAN France (FR76 suivi de chiffres/espaces, longueur variable)
_IBAN_RE = re.compile(
    r"\bFR\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{2,3}\b",
    re.IGNORECASE,
)

# Numéro de carte bancaire : 4 groupes de 4 chiffres (avec espaces ou tirets)
_CB_RE = re.compile(
    r"\b(?:\d{4}[\s\-]){3}\d{4}\b"
)

# Mots de passe / codes secrets
_PASSWORD_RE = re.compile(
    r"(mot\s+de\s+passe|password|code\s+secret|code\s+pin)\s*[:=]?\s*\d{4,}",
    re.IGNORECASE,
)

# Trigger words seuls (sans les chiffres suivants — pour la détection dans les descriptions)
_SENSITIVE_WORDS_RE = re.compile(
    r"\b(mot\s+de\s+passe|password|code\s+secret|code\s+pin|iban|solde|numéro\s+de\s+carte)\b",
    re.IGNORECASE,
)

# ── API publique ──────────────────────────────────────────────────────────────


def detect_pii_in_text(text: str) -> list[str]:
    """Détecte les PII dans un texte brut.

    Args:
        text: Texte à analyser.

    Returns:
        Liste des types de PII détectés (peut être vide).

    Example::

        >>> detect_pii_in_text("Mon IBAN est FR76 1234 5678 9012 3456 7890 123")
        ['IBAN']
    """
    found: list[str] = []

    if _IBAN_RE.search(text):
        found.append("IBAN")
        logger.warning("PII detected: IBAN in text")

    if _CB_RE.search(text):
        found.append("Numéro de carte bancaire")
        logger.warning("PII detected: credit card number in text")

    if _PASSWORD_RE.search(text):
        found.append("Mot de passe / code secret")
        logger.warning("PII detected: password/PIN in text")

    return found


def should_block_image(gemini_description: str) -> tuple[bool, str]:
    """Analyse la description Gemini d'une image pour détecter des données sensibles.

    Si Gemini a lu des informations sensibles sur l'image, on bloque la réponse
    et on renvoie un message de sécurité.

    Args:
        gemini_description: Texte retourné par Gemini après analyse de l'image.

    Returns:
        Tuple (should_block: bool, reason: str).
        Si should_block est True, reason contient le motif.

    Example::

        >>> should_block_image("Je vois un IBAN FR76... et un solde bancaire.")
        (True, 'Données bancaires détectées sur l\\'image')
    """
    desc_lower = gemini_description.lower()

    # PII explicitement mentionnés dans la réponse Gemini
    pii_found = detect_pii_in_text(gemini_description)
    if pii_found:
        reason = f"Données sensibles détectées dans la réponse : {', '.join(pii_found)}"
        return True, reason

    # Mots-clés sensibles dans la description (même sans regex complets)
    if _SENSITIVE_WORDS_RE.search(gemini_description):
        return True, "Données potentiellement sensibles mentionnées sur l'image"

    # Signaux d'alerte bancaire
    banking_signals = [
        "application bancaire",
        "virement",
        "compte bancaire",
        "relevé de compte",
        "carte bancaire",
        "coordonnées bancaires",
    ]
    for signal in banking_signals:
        if signal in desc_lower:
            return True, f"Contenu bancaire détecté sur l'image ({signal})"

    return False, ""
