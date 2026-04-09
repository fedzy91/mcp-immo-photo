# MCP Retouche Photo Immobilière — Guy Hoquet Mennecy

Serveur MCP calibré sur 10 paires avant/après réelles.

## Déploiement rapide (Render.com — gratuit)

1. Créer un compte sur https://render.com
2. "New Web Service" → connecter ce dépôt GitHub
3. Runtime: Docker → Deploy
4. Copier l'URL (ex: https://mcp-immo-photo.onrender.com)

## Connexion dans Claude.ai

Paramètres → Connecteurs → Ajouter un serveur MCP
URL: https://votre-url.onrender.com/mcp

## Outils disponibles

| Outil | Description |
|-------|-------------|
| `retouch_photo` | Retouche automatique par profil pièce |
| `analyze_room` | Analyse et recommandations |
| `list_profiles` | Liste tous les profils |

## Profils calibrés

- salon_salle_manger, cuisine, chambre_parentale
- salon_sejour, facade_exterieure, jardin
- chambre_ado, chambre_enfant, chambre_bebe

## Paramètres appris (10 paires avant/après)

| Profil | Luminosité | Saturation | Température |
|--------|-----------|------------|-------------|
| salon | +8% | -25% | -8 |
| cuisine | +10% | -22% | -8 |
| chambre parentale | +6% | -18% | -11 |
| chambre ado | +32% | -30% | -20 |
| chambre enfant | +18% | -28% | -8 |
| façade | +16% | -22% | -5 |
| jardin | +20% | +5% | -2 |
