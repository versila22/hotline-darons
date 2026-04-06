"""Tests unitaires pour bot/ai_engine.py."""

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.ai_engine import AIEngine


class TestAIEngine:
    def test_diagnose_returns_structured_response(self):
        engine = AIEngine(api_key="test")
        engine._client.models.generate_content = Mock(
            return_value=SimpleNamespace(
                text='{"answer": "1. Redémarre la box. 2. Attends 2 minutes.", "escalate": false, "reason": ""}'
            )
        )

        response = asyncio.run(
            engine.diagnose(
                text="Internet ne marche plus",
                rag_context=["## Internet\nLa box est une Livebox 5."],
                history=[{"role": "user", "content": "Bonjour"}],
            )
        )

        assert response.answer.startswith("1. Redémarre la box")
        assert response.needs_escalation is False
        assert response.escalation_reason == ""
        engine._client.models.generate_content.assert_called_once()

    def test_diagnose_handles_invalid_json(self):
        engine = AIEngine(api_key="test")
        engine._client.models.generate_content = Mock(
            return_value=SimpleNamespace(text="Ce n'est pas du JSON mais une réponse utile.")
        )

        response = asyncio.run(engine.diagnose(text="Mon écran est flou"))

        assert response.answer == "Ce n'est pas du JSON mais une réponse utile."
        assert response.needs_escalation is False
        assert response.escalation_reason == ""

    def test_escalation_detection(self):
        engine = AIEngine(api_key="test")
        engine._client.models.generate_content = Mock(
            return_value=SimpleNamespace(
                text='```json\n{"answer": "Ne touche à rien, Jay prend le relais.", "escalate": true, "reason": "Possible fraude bancaire."}\n```'
            )
        )

        response = asyncio.run(engine.diagnose(text="J'ai reçu un SMS de banque bizarre"))

        assert response.answer == "Ne touche à rien, Jay prend le relais."
        assert response.needs_escalation is True
        assert response.escalation_reason == "Possible fraude bancaire."
