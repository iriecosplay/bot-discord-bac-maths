import os
import zipfile
import urllib.request

import config


def preparer_donnees():
    """Si DATA_DIR existe déjà et contient des fichiers, ne fait rien
    (cas du développement local, ou volume déjà rempli sur Railway).
    Sinon, télécharge le zip pointé par DATA_ZIP_URL et l'extrait au bon
    endroit. Le zip doit contenir le dossier 'Exercices_Bac_Maths/' à sa
    racine (créé avec : zip -r data.zip Exercices_Bac_Maths/)."""

    if os.path.isdir(config.DATA_DIR) and os.listdir(config.DATA_DIR):
        print(f"[setup_data] Données déjà présentes dans {config.DATA_DIR}.")
        return

    if not config.DATA_ZIP_URL:
        print(f"[setup_data] Aucune donnée trouvée dans {config.DATA_DIR} et DATA_ZIP_URL n'est pas défini.")
        return

    print(f"[setup_data] Téléchargement depuis {config.DATA_ZIP_URL} ...")
    zip_path = "/tmp/exercices_data.zip"
    urllib.request.urlretrieve(config.DATA_ZIP_URL, zip_path)

    dossier_parent = os.path.dirname(config.DATA_DIR.rstrip("/")) or "."
    os.makedirs(dossier_parent, exist_ok=True)

    print("[setup_data] Extraction en cours (peut prendre quelques minutes pour 600 Mo)...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dossier_parent)

    os.remove(zip_path)
    print("[setup_data] Terminé.")
