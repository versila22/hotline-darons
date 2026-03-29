"""Configuration centralisée — toutes les env vars et constantes."""

import os
from pathlib import Path


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# ── Escalade ──────────────────────────────────────────────────────────────────
# ID Telegram de Jerome (destinataire des alertes d'escalade)
ESCALATION_CHAT_ID: int = int(os.environ.get("ESCALATION_CHAT_ID", "0"))

# ── Chemins ───────────────────────────────────────────────────────────────────
KNOWLEDGE_DIR: Path = Path(os.environ.get("KNOWLEDGE_DIR", "/app/knowledge"))
DB_PATH: str = os.environ.get("DB_PATH", "/app/data/hotline_darons.db")

# ── Constantes métier ─────────────────────────────────────────────────────────
CONTEXT_EXPIRATION_MINUTES: int = 5
MAX_PHOTO_SIZE_MB: int = 10

# ── Modèles ───────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = "gemini-2.5-flash"
EMBEDDING_MODEL: str = "text-embedding-004"
