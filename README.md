# Bot Discord — Exercices de Bac Maths

## 1. Créer l'application Discord

1. Va sur https://discord.com/developers/applications → **New Application**.
2. Onglet **Bot** → **Reset Token** → copie le token (tu en auras besoin comme `DISCORD_TOKEN`).
3. Aucun "Privileged Gateway Intent" n'est nécessaire (le bot ne lit pas le contenu des messages, il ne réagit qu'aux clics de boutons).
4. Onglet **OAuth2 → URL Generator** :
   - Scopes : `bot`
   - Permissions : `Manage Channels`, `Manage Roles`, `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `View Channels`
5. Ouvre l'URL générée, invite le bot sur ton serveur (ID `1487179769236689068`).
6. **Important** : dans les paramètres du serveur → Rôles, monte le rôle du bot au-dessus des rôles qu'il doit pouvoir gérer, sinon il ne pourra pas créer de salons avec permissions personnalisées correctement positionnés.

## 2. Installation locale (pour tester avant de déployer)

```bash
git clone <ton-repo>
cd <ton-repo>
python -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

Place ton dossier `Exercices_Bac_Maths/` (déjà généré par `classement_bac_maths.py`) directement à côté de `bot.py`.

Crée un fichier `.env` (ou exporte la variable directement) :
```bash
export DISCORD_TOKEN="ton_token_ici"
```

Lance le bot :
```bash
python bot.py
```

Si tout fonctionne, le message avec les boutons apparaît automatiquement dans le salon `1512035664961736724`.

## 3. Régénérer les exercices en version paginée (recommandé avant déploiement)

La v3 de `classement_bac_maths.py` sauvegarde chaque page séparément (`enonce_1.png`, `enonce_2.png`...) au lieu d'une seule image collée, ce qui permet la pagination dans Discord. **Si tu as déjà un dossier `Exercices_Bac_Maths` généré avec l'ancienne version**, le bot fonctionnera quand même (il détecte automatiquement l'ancien format en repli), mais sans bouton de pagination pour ces exercices-là.

Pour tout régénérer proprement en version paginée :
```bash
rm -rf Exercices_Bac_Maths
python classement_bac_maths.py
```

## 4. Héberger les 600 Mo de données (sans les mettre dans Git)

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

## 5. Déployer sur Railway

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

## 6. Mettre à jour les données plus tard

Si tu ajoutes de nouveaux PDF/exercices : régénère localement, re-zippe, upload une nouvelle release GitHub (nouvelle URL), mets à jour `DATA_ZIP_URL` sur Railway, puis **supprime manuellement le contenu du volume** (Railway ne le fait pas seul) avant de redéployer — sinon le bot croira que les données sont déjà là et gardera l'ancienne version.

## Notes sur les choix faits

- **Catégorie des salons privés** : Discord n'autorise pas d'imbriquer une catégorie dans une autre. Le bot crée donc une nouvelle catégorie `📝 Sessions d'exercices` positionnée juste *après* la catégorie `1497318460600881284` dans la liste, mais pas "dedans".
- **Un seul salon actif par utilisateur**, fermé uniquement via le bouton "✅ Terminer la session" (pas d'expiration automatique).
- **`A_classer` est exclu** des menus élèves — c'est le dossier de repli du classificateur pour les exercices non identifiés, réservé à ta relecture manuelle.
- **Résilience aux redémarrages** : le menu principal et les boutons de confirmation de signalement (salon de logs) sont des vues persistantes, ils survivent à un redémarrage du bot. En revanche, si le bot redémarre pendant qu'un élève a un exercice ouvert, les boutons de cet exercice précis (pagination, corrigé, signaler, terminer) cessent de répondre — l'élève peut relancer un exercice depuis le menu, et toi supprimer le salon orphelin à la main si besoin.
