import os
import json
import random

# Mêmes valeurs que le dictionnaire REGIONS du script de classement.
# Triées du plus long au plus court pour que "Centres_Etrangers" ne soit
# jamais masqué par un préfixe plus court.
REGIONS_CONNUES = sorted([
    "Centres_Etrangers", "Amerique_Nord", "Amerique_Sud", "Polynesie",
    "Metropole", "Caledonie", "Antilles", "Guyane", "Reunion", "Mayotte",
    "Liban", "Asie",
], key=len, reverse=True)

# Dossier réservé aux exercices non classifiés automatiquement : on ne le
# propose jamais aux élèves, il attend une reclassification manuelle.
CHAPITRES_EXCLUS = {"A_classer"}
FICHIERS_IGNORES = {"rapport_classification.jsonl"}


def _parse_region(nom_dossier_exo):
    """Le dossier d'un exercice s'appelle '{annee}_{Region}[...]_Exo_{n}_v{k}'.
    On retrouve la région en cherchant, juste après l'année, laquelle des
    régions connues correspond au début du reste du nom."""
    parts = nom_dossier_exo.split("_", 1)
    if len(parts) < 2:
        return "Inconnu"
    reste = parts[1]
    for region in REGIONS_CONNUES:
        if reste.startswith(region):
            return region
    return "Inconnu"


class Exercice:
    __slots__ = ("chapitre", "chemin", "id", "annee", "region", "nb_pages_enonce", "nb_pages_corrige")

    def __init__(self, chapitre, chemin, infos):
        self.chapitre = chapitre
        self.chemin = chemin
        self.id = os.path.basename(chemin)
        self.annee = str(infos.get("annee", "Inconnue"))
        self.region = _parse_region(self.id)
        # Compat v2 : si nb_pages_* est absent, on suppose 1 page unique
        # (enonce.png) et un corrigé unique s'il existe.
        self.nb_pages_enonce = infos.get("nb_pages_enonce", 1)
        self.nb_pages_corrige = infos.get("nb_pages_corrige", 1 if infos.get("has_corrige") else 0)

    def chemin_page_enonce(self, n):
        chemin_numerote = os.path.join(self.chemin, f"enonce_{n}.png")
        if os.path.exists(chemin_numerote):
            return chemin_numerote
        return os.path.join(self.chemin, "enonce.png")  # compat v2

    def chemin_page_corrige(self, n):
        chemin_numerote = os.path.join(self.chemin, f"corrige_{n}.png")
        if os.path.exists(chemin_numerote):
            return chemin_numerote
        return os.path.join(self.chemin, "corrige.png")  # compat v2


class IndexExercices:
    def __init__(self, dossier_racine):
        self.dossier_racine = dossier_racine
        self.par_chapitre = {}
        self.tous = []
        self.charger()

    def charger(self):
        self.par_chapitre = {}
        self.tous = []
        if not os.path.isdir(self.dossier_racine):
            print(f"⚠️ Dossier de données introuvable : {self.dossier_racine}")
            return

        for chapitre in sorted(os.listdir(self.dossier_racine)):
            if chapitre in FICHIERS_IGNORES or chapitre in CHAPITRES_EXCLUS:
                continue
            chemin_chapitre = os.path.join(self.dossier_racine, chapitre)
            if not os.path.isdir(chemin_chapitre):
                continue

            exos = []
            for nom_exo in sorted(os.listdir(chemin_chapitre)):
                chemin_exo = os.path.join(chemin_chapitre, nom_exo)
                json_path = os.path.join(chemin_exo, "infos.json")
                if not os.path.exists(json_path):
                    continue
                try:
                    with open(json_path, encoding="utf-8") as f:
                        infos = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
                exos.append(Exercice(chapitre, chemin_exo, infos))

            if exos:
                self.par_chapitre[chapitre] = exos
                self.tous.extend(exos)

        print(f"[data_index] {len(self.tous)} exercice(s) chargés dans {len(self.par_chapitre)} chapitre(s).")

    def chapitres(self):
        return sorted(self.par_chapitre.keys())

    def annees(self):
        return sorted({e.annee for e in self.tous})

    def regions(self):
        return sorted({e.region for e in self.tous if e.region != "Inconnu"})

    def au_hasard(self, chapitre=None):
        pool = self.par_chapitre.get(chapitre, []) if chapitre else self.tous
        if not pool:
            return None
        return random.choice(pool)

    def trouver_par_chemin(self, chemin):
        for e in self.tous:
            if e.chemin == chemin:
                return e
        return None

    def deplacer_exercice(self, exercice, nouveau_chapitre):
        """Déplace physiquement le dossier de l'exercice vers un autre
        chapitre, met à jour infos.json puis recharge tout l'index."""
        nouveau_dossier_chapitre = os.path.join(self.dossier_racine, nouveau_chapitre)
        os.makedirs(nouveau_dossier_chapitre, exist_ok=True)
        nouveau_chemin = os.path.join(nouveau_dossier_chapitre, exercice.id)
        os.rename(exercice.chemin, nouveau_chemin)

        json_path = os.path.join(nouveau_chemin, "infos.json")
        with open(json_path, encoding="utf-8") as f:
            infos = json.load(f)
        infos["chapitres_detailles"] = [nouveau_chapitre]
        infos["classement"] = "reclasse_manuellement"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(infos, f, ensure_ascii=False, indent=4)

        self.charger()
