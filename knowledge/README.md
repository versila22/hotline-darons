# Knowledge Base — Comment personnaliser ?

Ce dossier contient la base de connaissances chargée par le bot au démarrage.
**Tous les fichiers `.md` et `.pdf` sont automatiquement indexés.**

## 🆕 Nouveau : Support PDF !

Vous pouvez maintenant ajouter des fichiers PDF (modes d'emploi, manuels techniques) :

```bash
# Exemple : ajouter des manuels
cp ~/Downloads/manuel_tv_samsung.pdf knowledge/
cp ~/Downloads/guide_freebox.pdf knowledge/
```

Le bot extraira automatiquement le texte de chaque page PDF et l'indexera dans la base RAG.

## Structure recommandée

Chaque fichier Markdown doit être structuré avec des titres `##` (H2) — ils définissent les chunks de recherche.

```markdown
# Titre du document

## Section 1
Contenu de la section...

## Section 2
Contenu de la section...
```

**Pour les PDF** : Pas besoin de formatage spécial. Le bot extrait le texte page par page.

## Comment modifier

1. Éditer `famille_jacq.md` (ou créer un nouveau fichier `.md` ou `.pdf`)
2. Remplacer les `[À remplir]` par les vraies informations
3. Relancer le bot (il recharge la base au démarrage)

## Bonnes pratiques

- **Sois précis** : "Box Freebox Delta" vaut mieux que "la box"
- **Décris les problèmes du point de vue de l'utilisateur** : "la télé ne s'allume pas" plutôt que "problème d'alimentation"
- **Garde les sections courtes** : une section = un sujet = un appareil ou une catégorie de problèmes
- **Ne mets jamais de vrais mots de passe** dans les fichiers de knowledge — même chiffrés

## Ajouter un nouvel appareil

Crée une nouvelle section dans `famille_jacq.md` :

```markdown
## Tablette

- Modèle : iPad Air 2022
- Code d'accès : (conservé séparément, ne pas noter ici)
- Chargeur : USB-C, 20W minimum recommandé

### Problèmes fréquents (Tablette)
- "La tablette ne s'allume pas" → Brancher le chargeur 30 minutes avant de réessayer
```

## Sécurité

⚠️ **Ne jamais noter dans ces fichiers :**
- Mots de passe réels
- Codes PIN bancaires
- Numéros de carte bancaire
- IBAN

Ces informations ne doivent jamais transiter par le bot.
