"""Tests unitaires pour bot/pii_filter.py."""

import pytest
import sys
import os

# Permet d'importer le module sans package complet
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.pii_filter import detect_pii_in_text, should_block_image


# ── detect_pii_in_text ────────────────────────────────────────────────────────


class TestDetectPiiInText:
    """Tests de détection de PII dans du texte."""

    # ── IBAN ──────────────────────────────────────────────────────────────────

    def test_iban_detected(self):
        text = "Mon IBAN est FR76 1234 5678 9012 3456 7890 123"
        result = detect_pii_in_text(text)
        assert "IBAN" in result

    def test_iban_detected_no_spaces(self):
        text = "IBAN: FR7612345678901234567890123"
        result = detect_pii_in_text(text)
        assert "IBAN" in result

    def test_iban_not_detected_for_non_french(self):
        """Un IBAN allemand ne devrait pas déclencher le pattern FR."""
        text = "DE89 3704 0044 0532 0130 00"
        result = detect_pii_in_text(text)
        assert "IBAN" not in result

    def test_no_iban_in_normal_text(self):
        text = "La télévision ne s'allume pas quand j'appuie sur le bouton."
        result = detect_pii_in_text(text)
        assert "IBAN" not in result

    # ── Carte bancaire ────────────────────────────────────────────────────────

    def test_credit_card_detected(self):
        text = "Mon numéro de carte est 4532 1234 5678 9012"
        result = detect_pii_in_text(text)
        assert "Numéro de carte bancaire" in result

    def test_credit_card_detected_with_dashes(self):
        text = "4532-1234-5678-9012"
        result = detect_pii_in_text(text)
        assert "Numéro de carte bancaire" in result

    def test_no_credit_card_in_normal_text(self):
        text = "Le code wifi est sur la box."
        result = detect_pii_in_text(text)
        assert "Numéro de carte bancaire" not in result

    # ── Mots de passe ─────────────────────────────────────────────────────────

    def test_password_detected(self):
        text = "mon mot de passe: 123456"
        result = detect_pii_in_text(text)
        assert "Mot de passe / code secret" in result

    def test_password_en_detected(self):
        text = "password: 987654"
        result = detect_pii_in_text(text)
        assert "Mot de passe / code secret" in result

    def test_code_secret_detected(self):
        text = "code secret = 4567"
        result = detect_pii_in_text(text)
        assert "Mot de passe / code secret" in result

    def test_code_pin_detected(self):
        text = "code pin 1234"
        result = detect_pii_in_text(text)
        assert "Mot de passe / code secret" in result

    def test_no_password_in_normal_text(self):
        text = "Je n'arrive pas à me connecter à internet."
        result = detect_pii_in_text(text)
        assert "Mot de passe / code secret" not in result

    # ── Texte vide / edge cases ───────────────────────────────────────────────

    def test_empty_text(self):
        assert detect_pii_in_text("") == []

    def test_multiple_pii_detected(self):
        text = "IBAN: FR76 1234 5678 9012 3456 7890 123 et carte 4532 1234 5678 9012"
        result = detect_pii_in_text(text)
        assert "IBAN" in result
        assert "Numéro de carte bancaire" in result

    def test_returns_list(self):
        result = detect_pii_in_text("texte normal")
        assert isinstance(result, list)


# ── should_block_image ────────────────────────────────────────────────────────


class TestShouldBlockImage:
    """Tests de détection de PII dans les descriptions Gemini."""

    def test_block_on_iban_in_description(self):
        desc = "Sur l'image je vois un IBAN FR76 1234 5678 9012 3456 7890 123"
        should_block, reason = should_block_image(desc)
        assert should_block is True
        assert reason

    def test_block_on_banking_content(self):
        desc = "L'image montre une application bancaire avec un relevé de compte"
        should_block, reason = should_block_image(desc)
        assert should_block is True

    def test_block_on_password_keyword(self):
        desc = "Je vois un mot de passe écrit sur un papier"
        should_block, reason = should_block_image(desc)
        assert should_block is True

    def test_block_on_credit_card(self):
        desc = "Il y a un numéro de carte bancaire visible"
        should_block, reason = should_block_image(desc)
        assert should_block is True

    def test_no_block_on_safe_content(self):
        desc = "L'image montre l'écran de la télévision avec un message d'erreur E-01."
        should_block, reason = should_block_image(desc)
        assert should_block is False
        assert reason == ""

    def test_no_block_on_wifi_problem(self):
        desc = "L'utilisateur voit une page d'erreur de connexion internet sur son navigateur."
        should_block, reason = should_block_image(desc)
        assert should_block is False

    def test_block_returns_tuple(self):
        result = should_block_image("test")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_block_on_virement(self):
        desc = "Je vois une page de virement bancaire avec les coordonnées"
        should_block, reason = should_block_image(desc)
        assert should_block is True

    def test_no_block_empty_description(self):
        should_block, reason = should_block_image("")
        assert should_block is False
