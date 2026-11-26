# Bot Mathematic — bot unique du serveur

Ce bot remplace **les 3 anciens bots** du serveur. Tout ce qu'ils faisaient est maintenant fait par **un seul bot : celui des exercices de bac**.

| Ancien bot | Ce qu'il faisait | Où c'est maintenant |
|---|---|---|
| bot-discord-bac-maths | Exercices de bac (menu, salons privés, corrigés, signalements) | `cogs/exercices.py` |
| progressionbot | XP, niveaux et rôles d'activité, forum « résolu ? », giveaways, vocaux temporaires, dashboard de stats, aidant du mois, panneau d'infos/challenges | `cogs/progression/` + `cogs/serveur/bienvenue.py` |
| irie-bot (JavaScript) | Modération `+`, prison, warns, anti-raid, anti-spam, blacklist, tickets, avis, panneaux (classes, visibilité, couleurs, réseaux, dons, tag), discussions privées, salon vocal de stats, logs | `cogs/serveur/` + `cogs/moderation/` (réécrit en Python) |

## Le système de commandes

- **Chaque commande marche de 2 façons** : `+warn @membre raison` (ou `!warn`) **et** `/warn` avec l'autocomplétion Discord.
- **`/aide`** (ou `+aide`, `+help`) : menu par catégorie, qui n'affiche **que les commandes que la personne a le droit d'utiliser**.
- **Une seule hiérarchie de permissions** pour tout le bot (`noyau/permissions.py`) :
  `Membre → Junior Mod → Modérateur → PA Test → Staff → Saint → Owner`, plus le rôle indépendant **Perm Jail** (seul autorisé à emprisonner).
- **Erreurs gérées au même endroit** : usage affiché automatiquement, « membre introuvable », « permission refusée », anti-flood (4 s entre deux commandes `+`).

Catégories de `/aide` : 📝 Exercices · 📈 Progression · ℹ️ Infos · ⚖️ Sanctions · 🧹 Salons · 🎭 Rôles · 🔐 Administration.

## Organisation du code

```
bot.py                 point d'entrée : intents, MongoDB, chargement des modules, erreurs, anti-flood
config.py              token, données d'exercices, MongoDB, IDs du bot d'exos
noyau/
  ids.py               tous les IDs du serveur (rôles, salons…) repris d'irie-bot
  etat.py              état partagé + helpers (logs de modération, prison, warns, panneaux…)
  permissions.py       hiérarchie et décorateurs @niveau / @perm_jail / @administrateur
  xp.py                calcul XP / niveaux (ex utils.py de progressionbot)
cogs/
  exercices.py         📝 exercices de bac
  aide.py              ❓ /aide
  progression/         📈 xp, niveaux, profil, forum, mensuel, giveaways, dashboard, vocaux
  serveur/             🏠 securite, panneaux, avis, tickets, bienvenue
  moderation/          🛡️ infos, sanctions, salons, roles, administration
exercices/             index des exos, sessions, signalements, téléchargement des données
outils/                classement_bac_maths.py (génération des exercices, en local)
```

Pour ajouter une commande : l'écrire dans le bon fichier avec `@commands.hybrid_command(description=…, usage=…)` + `@niveau(MOD)` (par ex.). Elle apparaît toute seule en `+`, en `/` et dans `/aide`.

## ✅ Mise en route (à faire une fois)

### 1. Portail développeur Discord — bot des exercices
https://discord.com/developers/applications → l'application du **bot d'exercices** → onglet **Bot** :
- Active les **3 Privileged Gateway Intents** : `Presence Intent`, `Server Members Intent`, `Message Content Intent`.
  *(Sans eux le bot ne démarre pas : il en a besoin pour la modération, l'XP, l'anti-spam et les commandes `+`.)*

### 2. Permissions sur le serveur
- Donne au bot la permission **Administrateur** (le plus simple : il gère rôles, salons, bans, timeouts, logs d'audit…).
  Lien d'invitation : onglet **OAuth2 → URL Generator** → scopes `bot` + `applications.commands` → permission `Administrator`.
- **Paramètres du serveur → Rôles** : monte le rôle du bot **tout en haut** (au-dessus de Prison, des rôles de classe, couleurs, XP, staff…). Il ne peut gérer que les rôles en dessous du sien.

### 3. Railway
Dans le service du bot d'exercices → **Variables** :

| Variable | Valeur |
|---|---|
| `DISCORD_TOKEN` | (déjà là) token du bot d'exercices |
| `DATA_DIR`, `DATA_ZIP_URL` | (déjà là) données des exercices |
| `MONGODB_URI` | **copie la valeur `MONGODB_URI` du service progressionbot** (base de l'XP). Si absente, le bot utilise le cluster d'irie-bot. |
| `ANCIENS_BOTS_IDS` | *(facultatif)* ID du bot progressionbot, pour être sûr que ses vieux panneaux soient remplacés |

Puis **supprime (ou mets en pause) les services irie-bot et progressionbot** sur Railway : sinon deux bots répondraient en même temps.

### 4. Après le premier démarrage
- Le bot **reposte automatiquement** ses panneaux (classes, visibilité, couleurs, tickets, avis, réseaux, dons, tag, vocaux temporaires, infos/challenges) et **supprime ceux des anciens bots**, dont les boutons ne marcheraient plus.
- Tu peux ensuite **expulser irie-bot et progressionbot** du serveur.
- Les commandes `/` apparaissent tout de suite sur le serveur (synchronisées au démarrage).
- Toutes les données sont conservées : XP, warns, prison, avis, tickets, blacklist, reaction roles, discussions privées (mêmes bases MongoDB).

## Lancer en local

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DISCORD_TOKEN="ton_token"
python bot.py
```

## Données des exercices (600 Mo)

### A. Régénérer les exercices en version paginée (recommandé avant déploiement)

La v3 de `classement_bac_maths.py` sauvegarde chaque page séparément (`enonce_1.png`, `enonce_2.png`...) au lieu d'une seule image collée, ce qui permet la pagination dans Discord. **Si tu as déjà un dossier `Exercices_Bac_Maths` généré avec l'ancienne version**, le bot fonctionnera quand même (il détecte automatiquement l'ancien format en repli), mais sans bouton de pagination pour ces exercices-là.

Pour tout régénérer proprement en version paginée :
```bash
rm -rf Exercices_Bac_Maths
python outils/classement_bac_maths.py
```

### B. Héberger les 600 Mo de données (sans les mettre dans Git)

Git n'est pas fait pour stocker 600 Mo d'images. La méthode la plus simple et gratuite : une **Release GitHub** (jusqu'à 2 Go par fichier, même sur un dépôt public léger).

1. Zippe le dossier de données (le zip doit contenir le dossier lui-même à sa racine) :
   ```bash
   zip -r exercices_data.zip Exercices_Bac_Maths/
   ```
2. Crée ton dépôt GitHub pour le code du bot (sans le zip ni le dossier de données — `.gitignore` s'en occupe) :
   ```bash
   git init
   git add .
   git commit -m "Bot Discord - version initiale"
   git remote add origin <url_de_ton_repo>
   git push -u origin main
   ```
3. Sur GitHub → onglet **Releases** → **Create a new release** → glisse `exercices_data.zip` en tant qu'asset.
4. Publie la release, puis clique droit sur le lien de téléchargement de l'asset → **Copier l'adresse du lien**. C'est ton `DATA_ZIP_URL`.

### C. Volume Railway pour les exercices

1. Sur https://railway.app → **New Project** → **Deploy from GitHub repo** → sélectionne ton dépôt.
2. Railway détecte automatiquement `Procfile` et `requirements.txt`.
3. **Ajouter un volume persistant** (pour ne pas re-télécharger les 600 Mo à chaque redéploiement) :
   - Dans le service → onglet **Volumes** → **New Volume**
   - Mount path : `/data`
4. **Variables d'environnement** (onglet **Variables**) :
   | Nom | Valeur |
   |---|---|
   | `DISCORD_TOKEN` | ton token du bot |
   | `DATA_DIR` | `/data/Exercices_Bac_Maths` |
   | `DATA_ZIP_URL` | le lien copié à l'étape 4 |
5. Déploie. Au premier démarrage, les logs doivent afficher le téléchargement puis l'extraction (`[setup_data] ...`), suivi de `✅ Connecté en tant que ...`.
6. Aux redéploiements suivants, comme `/data/Exercices_Bac_Maths` existe déjà sur le volume, le téléchargement est sauté — démarrage quasi instantané.

### D. Mettre à jour les données plus tard

Si tu ajoutes de nouveaux PDF/exercices : régénère localement, re-zippe, upload une nouvelle release GitHub (nouvelle URL), mets à jour `DATA_ZIP_URL` sur Railway, puis **supprime manuellement le contenu du volume** (Railway ne le fait pas seul) avant de redéployer — sinon le bot croira que les données sont déjà là et gardera l'ancienne version.

### Notes (exercices)

- **Catégorie des salons privés** : Discord n'autorise pas d'imbriquer une catégorie dans une autre. Le bot crée donc une nouvelle catégorie `📝 Sessions d'exercices` positionnée juste *après* la catégorie `1497318460600881284` dans la liste, mais pas "dedans".
- **Un seul salon actif par utilisateur**, fermé uniquement via le bouton "✅ Terminer la session" (pas d'expiration automatique).
- **`A_classer` est exclu** des menus élèves — c'est le dossier de repli du classificateur pour les exercices non identifiés, réservé à ta relecture manuelle.
- **Résilience aux redémarrages** : le menu principal et les boutons de confirmation de signalement (salon de logs) sont des vues persistantes, ils survivent à un redémarrage du bot. En revanche, si le bot redémarre pendant qu'un élève a un exercice ouvert, les boutons de cet exercice précis (pagination, corrigé, signaler, terminer) cessent de répondre — l'élève peut relancer un exercice depuis le menu, et toi supprimer le salon orphelin à la main si besoin.
