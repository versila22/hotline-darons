# 🤖 Hotline Darons

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://www.python.org/)
[![Gemini 2.5 Flash](https://img.shields.io/badge/Gemini-2.5%20Flash-orange?logo=google)](https://deepmind.google/technologies/gemini/)
[![Telegram Bot](https://img.shields.io/badge/Telegram%20Bot%20API-21%2B-2CA5E0?logo=telegram)](https://core.telegram.org/bots/api)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/tests-38%2F38%20passing-brightgreen?logo=pytest)](tests/)
[![License](https://img.shields.io/badge/License-Personal%20Use-lightgrey)](LICENSE)

> **Bot Telegram IA multimodal pour le support technique parental — propulsé par Gemini 2.5 Flash.**

Fini les appels paniqués à 22h pour "la télé qui s'allume plus". **Hotline Darons** répond en quelques secondes, en français simple, avec une patience infinie. Il analyse les photos d'écran, comprend les messages vocaux, et escalade vers vous seulement quand c'est vraiment nécessaire.

---

## 🎯 Compétences démontrées

| Domaine | Implémentation |
|---------|---------------|
| **LLM / Multimodal** | Gemini 2.5 Flash — texte, image, audio natif |
| **RAG familial** | Embedding Google + cosine search sur knowledge base `.md` + `.pdf` |
| **Bot Telegram** | Handlers async, gestion de session, file d'attente photo→question |
| **Sécurité IA** | Filtre PII (IBAN, CB, mots de passe) sur texte et images |
| **Escalade intelligente** | Détection de niveau de complexité → transfert à l'humain |
| **Tests** | 38/38 tests pytest — session store, PII filter, escalade |
| **DevOps** | Docker Compose, variables d'environnement, SQLite persistant |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Telegram (parents)                     │
│              📸 Photo  🎤 Vocal  ✍️ Texte               │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    bot/main.py                           │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │session_store│  │  pii_filter  │  │  escalation   │  │
│  │  (SQLite)   │  │  (sécurité)  │  │  (→ Jerome)   │  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │
             ┌──────────┴──────────┐
             │                     │
             ▼                     ▼
┌────────────────────┐   ┌────────────────────┐
│    bot/rag.py      │   │  bot/ai_engine.py  │
│  Knowledge Base    │──▶│  Gemini 2.5 Flash  │
│  text-embedding    │   │  Multimodal        │
│  004 (Google)      │   │  JSON structuré    │
└────────────────────┘   └────────────────────┘
```

---

## Quick Start

### Prérequis

- Docker + Docker Compose
- Un token bot Telegram (via [@BotFather](https://t.me/BotFather))
- Une clé API Google AI ([aistudio.google.com](https://aistudio.google.com/app/apikey))
- Votre Telegram user ID (via [@userinfobot](https://t.me/userinfobot))

### Déploiement en 3 commandes

```bash
# 1. Cloner et configurer
cp .env.example .env
nano .env  # Remplir TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, ESCALATION_CHAT_ID

# 2. Personnaliser la base de connaissances (optionnel mais recommandé)
nano knowledge/famille_jacq.md

# 3. Lancer
docker-compose up -d
```

Le bot est actif ! Envoyez `/start` depuis Telegram.

---

## Configuration

### Variables d'environnement (`.env`)

| Variable | Description | Obligatoire |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram (via @BotFather) | ✅ |
| `GEMINI_API_KEY` | Clé API Google AI Studio | ✅ |
| `ESCALATION_CHAT_ID` | Votre Telegram user ID (pour recevoir les alertes) | ✅ |
| `KNOWLEDGE_DIR` | Chemin vers le dossier knowledge | Non (défaut: `/app/knowledge`) |
| `DB_PATH` | Chemin vers la base SQLite | Non (défaut: `/app/data/hotline_darons.db`) |

### Obtenir votre Telegram ID

Envoyez `/start` à [@userinfobot](https://t.me/userinfobot) sur Telegram — il vous donne votre ID numérique.

---

## Personnalisation de la Knowledge Base

Éditez `knowledge/famille_jacq.md` pour adapter le bot à votre famille :

```markdown
## Télévision
- Modèle : Samsung UE55TU7125
- Box IPTV : Freebox Player
...
```

**Nouveau !** Ajoutez des fichiers PDF (modes d'emploi, manuels) :

```bash
# Ajouter des manuels PDF
cp ~/Downloads/manuel_tv.pdf knowledge/
cp ~/Downloads/guide_freebox.pdf knowledge/

# Redémarrer le bot pour recharger la base
docker-compose restart
```

Le bot recharge automatiquement la base au démarrage. Voir [`knowledge/README.md`](knowledge/README.md) pour le guide complet.

**Support PDF** :
- ✅ Extraction automatique du texte
- ✅ Pagination (chaque page est un chunk)
- ✅ Compatible avec tous les fichiers PDF
- ⚠️ Nécessite `PyPDF2>=3.0.0` (inclus dans requirements.txt)

---

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| 📸 **Photo d'écran** | Analyse l'image + attend votre description vocale/texte |
| 🎤 **Message vocal** | Transcrit et analyse l'audio directement (Gemini natif) |
| ✍️ **Texte** | Répond aux questions écrites |
| 🔒 **Filtre PII** | Bloque automatiquement les données bancaires / mots de passe |
| 📚 **RAG familial** | Utilise la config de votre famille pour des réponses précises |
| 🚨 **Escalade** | Vous alerte sur Telegram si le problème dépasse le niveau 1 |
| 💾 **Contexte SQLite** | Lie une photo à la question qui suit (jusqu'à 5 min) |

---

## Développement

### Lancer en local (sans Docker)

```bash
# Installer les dépendances
pip install -r requirements.txt

# Configurer
cp .env.example .env && nano .env

# Lancer
python -m bot.main
```

### Tests

```bash
pytest tests/ -v
```

---

## Sécurité

- ✅ **Zéro rétention** : les photos sont supprimées après utilisation (5 min max)
- ✅ **Filtre PII** : détection d'IBAN, numéros de CB, mots de passe sur les images et dans le texte
- ✅ **Pas de conseils bancaires** : escalade systématique pour tout ce qui touche aux finances
- ✅ **Secrets en env vars** : aucun secret dans le code ou les fichiers versionnés

---

## Roadmap

- [ ] Support WhatsApp (Twilio / Meta API)
- [ ] Interface d'administration web pour mettre à jour la knowledge base
- [ ] Résumé hebdomadaire des problèmes résolus
- [ ] Support multi-familles (configuration par utilisateur autorisé)
- [ ] Intégration Mem0 pour une mémoire long-terme par utilisateur
- [ ] Monitoring / alertes (Uptime Robot, Sentry)

---

## Licence

Projet personnel — utilisation libre dans un contexte familial.
