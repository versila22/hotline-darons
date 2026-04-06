"""Tests unitaires pour bot/escalation.py."""

import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.escalation import _format_user_name, escalate


def test_format_user_name_prefers_full_name_and_username():
    user_info = {
        "id": 42,
        "first_name": "Jeanne",
        "last_name": "Dupont",
        "username": "jdupont",
    }

    assert _format_user_name(user_info) == "Jeanne Dupont (@jdupont)"


def test_escalate_sends_message_when_no_photo():
    bot = AsyncMock()

    with patch("bot.escalation.ESCALATION_CHAT_ID", 123456):
        result = __import__("asyncio").run(
            escalate(
                bot=bot,
                user_info={"id": 7, "first_name": "Paul", "username": "paulie"},
                summary="Blocage total du téléphone.",
            )
        )

    assert result is True
    bot.send_message.assert_awaited_once()
    args = bot.send_message.await_args.kwargs
    assert args["chat_id"] == 123456
    assert "Blocage total du téléphone" in args["text"]
