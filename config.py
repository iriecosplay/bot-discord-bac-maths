import os

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

# Dossier contenant les exercices classés. En local : le dossier généré
# par classement_bac_maths.py, à côté du bot. Sur Railway : un chemin sur
# le volume persistant (ex: /data/Exercices_Bac_Maths), voir README.md.
DATA_DIR = os.environ.get("DATA_DIR", "Exercices_Bac_Maths")

# URL de téléchargement (release GitHub) du zip contenant le dossier de
# données. Utilisé uniquement si DATA_DIR est vide/absent au démarrage
# (voir setup_data.py). Laisser vide en local si le dossier existe déjà.
DATA_ZIP_URL = os.environ.get("DATA_ZIP_URL", "")

# --- IDs Discord ---
GUILD_ID = 1487179769236689068
SALON_INTERFACE_ID = 1512035664961736724
CATEGORIE_PARENTE_ID = 1497318460600881284
SALON_LOGS_ID = 1502792129859162214
ROLE_CONFIRMATION_ID = 1553422672069656648

# Nom de la catégorie créée par le bot pour les salons privés. Discord ne
# permet pas d'imbriquer une catégorie DANS une autre : cette catégorie
# est donc positionnée juste APRÈS CATEGORIE_PARENTE_ID dans la liste des
# salons, pas "dedans".
NOM_CATEGORIE_SESSIONS = "📝 Sessions d'exercices"

_dossier_etat = os.path.dirname(DATA_DIR.rstrip("/")) or "."
FICHIER_SESSIONS = os.path.join(_dossier_etat, "active_sessions.json")
FICHIER_SIGNALEMENTS = os.path.join(_dossier_etat, "signalements.json")
FICHIER_MENU = os.path.join(_dossier_etat, "menu_state.json")
