FROM python:3.12-slim

# Métadonnées
LABEL maintainer="Jerome"
LABEL description="Hotline Darons — Bot Telegram d'assistance technique familiale"

# Répertoire de travail
WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python en premier (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY bot/ ./bot/
COPY knowledge/ ./knowledge/

# Créer le répertoire pour la base SQLite
RUN mkdir -p /app/data

# Variables d'environnement par défaut
ENV KNOWLEDGE_DIR=/app/knowledge
ENV DB_PATH=/app/data/hotline_darons.db
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Lancement du bot
CMD ["python", "-m", "bot.main"]
