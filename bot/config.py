"""Configuration centralisée — toutes les env vars et constantes."""

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_KNOWLEDGE_DIR = _PROJECT_ROOT / "knowledge"
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "hotline_darons.db"


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# ── Escalade ──────────────────────────────────────────────────────────────────
# ID Telegram de Jerome (destinataire des alertes d'escalade)
ESCALATION_CHAT_ID: int = int(os.environ.get("ESCALATION_CHAT_ID", "0"))

# ── Chemins ───────────────────────────────────────────────────────────────────
KNOWLEDGE_DIR: Path = Path(os.environ.get("KNOWLEDGE_DIR", str(_DEFAULT_KNOWLEDGE_DIR)))
DB_PATH: str = os.environ.get("DB_PATH", str(_DEFAULT_DB_PATH))

# ── Constantes métier ─────────────────────────────────────────────────────────
CONTEXT_EXPIRATION_MINUTES: int = 5
MAX_PHOTO_SIZE_MB: int = 10

# ── Modèles ───────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = "gemini-2.5-flash"
EMBEDDING_MODEL: str = "models/gemini-embedding-001"
