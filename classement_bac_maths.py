import os
import re
import json
import unicodedata
from collections import deque, Counter
import fitz  # PyMuPDF
from PIL import Image, ImageOps

# ==========================================
# CONFIGURATION
# ==========================================
#
# v3 — CE QUI CHANGE PAR RAPPORT À LA v2 :
#
# Le bot Discord a besoin de pouvoir paginer un exercice page par page
# (bouton "page suivante"/"page précédente"). L'ancienne version collait
# toutes les pages d'un exercice en UNE SEULE grande image verticale
# (render_exercise). Ce n'est plus le cas : render_exercise_pages()
# renvoie maintenant la liste des images (une par page réellement
# occupée par l'exercice), et chaque page est enregistrée séparément
# (enonce_1.png, enonce_2.png, ... / corrige_1.png, corrige_2.png, ...).
# Le nombre de pages est noté dans infos.json (nb_pages_enonce,
# nb_pages_corrige) pour que le bot sache combien de boutons afficher.
#
# ATTENTION : les exercices déjà classés avec la v2 (image unique
# enonce.png/corrige.png) NE SONT PAS reconvertis automatiquement — le
# script saute tout dossier où infos.json existe déjà. Pour les
# regénérer en version paginée, supprime leur dossier (ou tout le
# dossier Exercices_Bac_Maths) avant de relancer.
#
# Le reste (score pondéré par rareté du mot, stemming, bonus de
# cooccurrence, vérification par dominance, journal d'audit, détection
# des exercices, gestion des années/index, regroupement en gros
# dossiers) est inchangé par rapport à la v2.

# 1. Tes fichiers PDF locaux
CHEMINS_PDF = [
    "enonces/bac_2025.pdf",
    "enonces/bac_2024.pdf",
    "enonces/bac_2023.pdf",
    "enonces/bac_2022.pdf",
    "enonces/bac_2026.pdf",   # <-- traité en dernier automatiquement
]

# 2. Les pages d'index correspondantes (None = pas d'index)
PAGES_INDEX = [
    (95, 96),  # 2025 : pages affichées 96 et 97
    (-2, -1),  # 2024 : les 2 dernières pages du PDF, comme 2022
    (93,),     # 2023 : page affichée 94
    (-2, -1),  # 2022 : les 2 dernières pages du PDF
    None,      # 2026 : pas d'index -> classification automatique
]

DOSSIER_PRINCIPAL = "Exercices_Bac_Maths"

# Modèle du nom de tes fichiers de correction
MODELE_NOM_CORRIGE = "corrige/bac_{annee}.pdf"

# --- Dictionnaires pour l'analyse du contexte (région / sujet / mois) ---
REGIONS = {
    "métropole": "Metropole", "metropole": "Metropole",
    "polynésie": "Polynesie", "polynesie": "Polynesie",
    "centres étrangers": "Centres_Etrangers", "centres etrangers": "Centres_Etrangers",
    "asie": "Asie",
    "amérique du nord": "Amerique_Nord", "amerique du nord": "Amerique_Nord",
    "amérique du sud": "Amerique_Sud", "amerique du sud": "Amerique_Sud",
    "nouvelle-calédonie": "Caledonie", "nouvelle caledonie": "Caledonie",
    "antilles": "Antilles", "guyane": "Guyane",
    "la réunion": "Reunion", "la reunion": "Reunion",
    "mayotte": "Mayotte", "liban": "Liban"
}

SUJETS = {
    "sujet 1": "J1", "jour 1": "J1", "j1": "J1",
    "sujet 2": "J2", "jour 2": "J2", "j2": "J2",
    "sujet 3": "J3", "jour 3": "J3"
}

MOIS = {
    "mars": "Mars", "mai": "Mai", "juin": "Juin", "septembre": "Sept", "novembre": "Nov"
}

# ==========================================
# VOCABULAIRE DES CHAPITRES CONNUS
# ==========================================

CHAPITRES_CONNUS = [
    "aire de trapèze", "aire de triangle", "aire d’un disque", "algorithme",
    "arbre pondéré", "arrangements et combinaisons", "asymptote",
    "Bienaymé-Tchebychev", "calcul de distance", "calcul de dérivée",
    "calcul de limite", "calcul d’aire", "calcul d’angle", "calcul d’intégrale",
    "combinaison", "combinatoire", "convergence de suite", "convexité",
    "cosinus", "cube", "distance d’un point à un plan",
    "distance d’un point à une droite", "distance point-plan",
    "droite et plan orthogonaux", "droite et plan parallèles",
    "droite orthogonal", "droites coplanaires", "droites non coplanaires",
    "droites parallèles", "droites perpendiculaires", "droites sécantes",
    "démonstration par récurrence", "dénombrement", "dérivée", "dérivée seconde",
    "espérance", "extremum", "fonction bornée", "fonction convexe",
    "fonction croissante", "fonction exponentielle", "fonction logarithme",
    "fonction logarithme népérien", "fonction monotone", "fonction paire",
    "fonction polynôme", "fonction racine carrée", "Fonctions", "géométrie",
    "géométrie dans l’espace", "intersection de droites", "intégrale",
    "intégration par parties", "inégalité de Bienaymé-Tchebychev",
    "inégalité de concentration", "inéquation", "lecture graphique",
    "limite de fonction", "limite de suite", "loi binomiale",
    "loi de probabilité", "maximum", "mesure d’angle", "minimum", "moyenne",
    "n-uplets", "nombre dérivé", "norme de vecteur", "plan médiateur",
    "plan orthogonal", "plans orthogonaux", "plans parallèles",
    "plans perpendiculaires", "plans sécants", "points alignés",
    "points coplanaires", "points non alignés", "pourcentage moyen",
    "primitive", "probabilité conditionnelle", "probabilités",
    "produit scalaire", "projeté orthogonal", "Python", "QCM",
    "raisonnement par l’absurde", "représentation paramétrique de droite",
    "récurrence", "résolution d’équation", "script python",
    "signe d’une fonction", "sinus", "somme de variables aléatoires",
    "sphère", "suite", "suite arithmétique", "suite bornée",
    "suite convergente", "suite croissante", "suite divergente",
    "suite décroissante", "suite géométrique", "suite monotone",
    "suite récurrente", "suites", "tableau de probabilités",
    "tableau de variations", "tangente d’angle", "tangente à la courbe",
    "théorème des valeurs intermédiaires", "trapèze", "triangle rectangle",
    "trigonométrie", "valeur moyenne", "valeur moyenne d’une fonction",
    "valeurs intermédiaires", "variable aléatoire", "variance",
    "variations de fonction", "vecteur directeur",
    "vecteur et plan orthogonaux", "vecteur normal", "vecteurs colinéaires",
    "vecteurs orthogonaux", "volume de pyramide", "volume de tétraèdre",
    "volume d’un cône", "volume pyramide", "volume tétraèdre", "Vrai-Faux",
    "équation", "équation avec exponentielle", "équation de droite",
    "équation de la tangente", "équation de plan", "équation de tangente",
    "équation différentielle", "équation différentielle homogène",
    "équation du second degré", "équation paramétrique de droite",
    "évènements indépendants",
]

# Synonymes / tournures typiques utilisées dans les énoncés.
SYNONYMES = {
    "récurrence": ["par recurrence", "hypothese de recurrence", "initialisation"],
    "démonstration par récurrence": ["par recurrence", "hypothese de recurrence", "initialisation"],
    "raisonnement par l’absurde": ["par l'absurde", "raisonnement par l absurde"],
    "probabilité conditionnelle": ["sachant que", "probabilite conditionnelle", "p_a(", "pa(", "pb("],
    "arbre pondéré": ["arbre de probabilite", "recopier l'arbre", "arbre ci-dessous"],
    "loi binomiale": ["binomiale"],
    "loi de probabilité": ["loi de probabilite"],
    "espérance": ["esperance"],
    "variance": ["variance"],
    "somme de variables aléatoires": ["x1 + x2", "x1+x2", "moyenne des"],
    "variable aléatoire": ["variable aleatoire"],
    "Bienaymé-Tchebychev": ["bienayme", "tchebychev"],
    "inégalité de Bienaymé-Tchebychev": ["bienayme", "tchebychev"],
    "inégalité de concentration": ["bienayme", "tchebychev", "concentration"],
    "évènements indépendants": ["independants", "independantes", "independance"],
    "combinatoire": ["denombrement", "combinaison", "factorielle"],
    "arrangements et combinaisons": ["combinaison", "factorielle", "arrangement"],
    "combinaison": ["combinaison"],
    "dénombrement": ["denombrement", "nombre de facons", "nombre de tirages"],
    "n-uplets": ["n-uplet", "n uplets", "uplets"],
    "QCM": ["qcm", "cocher", "une seule reponse exacte"],
    "Vrai-Faux": ["vraie ou fausse", "vrai ou faux", "indiquer si elle est vraie"],
    "convexité": ["convexe", "concave", "point d'inflexion"],
    "fonction convexe": ["convexe", "derivee seconde"],
    "dérivée seconde": ["derivee seconde", "f''", "f ''"],
    "tableau de variations": ["tableau de variation"],
    "variations de fonction": ["sens de variation", "variations de la fonction"],
    "tangente à la courbe": ["tangente a la courbe", "equation de la tangente"],
    "équation de la tangente": ["equation reduite de la tangente", "equation de la tangente"],
    "équation de tangente": ["equation de la tangente"],
    "asymptote": ["asymptote"],
    "limite de fonction": ["limite de la fonction"],
    "limite de suite": ["limite de la suite"],
    "suite convergente": ["converge", "convergente"],
    "convergence de suite": ["converge", "convergente"],
    "suite arithmétique": ["arithmetique"],
    "suite géométrique": ["geometrique"],
    "suite récurrente": ["u_n+1", "un+1", "u(n+1)"],
    "suite bornée": ["bornee", "majoree", "minoree"],
    "suite monotone": ["monotone"],
    "suite croissante": ["croissante"],
    "suite décroissante": ["decroissante"],
    "fonction bornée": ["bornee", "majoree", "minoree"],
    "fonction monotone": ["monotone"],
    "fonction croissante": ["croissante"],
    "produit scalaire": ["produit scalaire"],
    "vecteur normal": ["vecteur normal", "normal au plan"],
    "vecteurs colinéaires": ["colineaires"],
    "vecteurs orthogonaux": ["vecteurs orthogonaux"],
    "vecteur directeur": ["vecteur directeur"],
    "vecteur et plan orthogonaux": ["orthogonal au plan"],
    "droite orthogonal": ["orthogonale au plan"],
    "droite et plan orthogonaux": ["orthogonale au plan", "orthogonal au plan"],
    "droite et plan parallèles": ["parallele au plan"],
    "droites perpendiculaires": ["perpendiculaires"],
    "droites parallèles": ["paralleles"],
    "droites sécantes": ["secantes", "point d'intersection"],
    "droites coplanaires": ["coplanaires"],
    "droites non coplanaires": ["non coplanaires", "ne sont pas coplanaires"],
    "plans parallèles": ["plans paralleles"],
    "plans orthogonaux": ["plans orthogonaux"],
    "plans perpendiculaires": ["perpendiculaires"],
    "plans sécants": ["intersection des plans"],
    "plan médiateur": ["mediateur"],
    "plan orthogonal": ["orthogonal au plan"],
    "distance d’un point à un plan": ["distance du point", "au plan"],
    "distance d’un point à une droite": ["distance du point", "a la droite"],
    "distance point-plan": ["distance du point", "au plan"],
    "projeté orthogonal": ["projete orthogonal"],
    "représentation paramétrique de droite": ["representation parametrique"],
    "équation paramétrique de droite": ["representation parametrique", "equation parametrique"],
    "équation de plan": ["equation cartesienne du plan"],
    "équation de droite": ["equation de la droite"],
    "points alignés": ["alignes"],
    "points non alignés": ["non alignes", "ne sont pas alignes"],
    "points coplanaires": ["coplanaires"],
    "intersection de droites": ["point d'intersection"],
    "norme de vecteur": ["norme du vecteur"],
    "mesure d’angle": ["mesure de l'angle", "arrondie au degre"],
    "cosinus": ["cos("],
    "sinus": ["sin("],
    "tangente d’angle": ["tan("],
    "trigonométrie": ["cos(", "sin(", "trigonometrique"],
    "triangle rectangle": ["triangle rectangle"],
    "aire de triangle": ["aire du triangle"],
    "aire de trapèze": ["aire du trapeze", "trapeze"],
    "trapèze": ["trapeze"],
    "aire d’un disque": ["aire du disque", "disque de rayon"],
    "calcul d’aire": ["aire du domaine", "aire de la surface"],
    "volume de pyramide": ["volume de la pyramide"],
    "volume pyramide": ["volume de la pyramide"],
    "volume de tétraèdre": ["volume du tetraedre"],
    "volume tétraèdre": ["volume du tetraedre"],
    "volume d’un cône": ["volume du cone"],
    "sphère": ["sphere"],
    "primitive": ["primitive"],
    "intégrale": ["integrale"],
    "calcul d’intégrale": ["integrale"],
    "intégration par parties": ["integration par parties"],
    "valeur moyenne": ["valeur moyenne"],
    "valeur moyenne d’une fonction": ["valeur moyenne de la fonction"],
    "fonction exponentielle": ["exponentielle", "e^", "exp("],
    "fonction logarithme": ["ln(", "logarithme"],
    "fonction logarithme népérien": ["ln(", "logarithme neperien"],
    "fonction polynôme": ["polynome"],
    "fonction racine carrée": ["racine carree"],
    "fonction paire": ["fonction paire"],
    "signe d’une fonction": ["signe de la fonction", "tableau de signes"],
    "extremum": ["extremum"],
    "nombre dérivé": ["nombre derive"],
    "calcul de dérivée": ["calculer la derivee", "fonction derivee"],
    "dérivée": ["derivee"],
    "équation": ["equation"],
    "équation du second degré": ["second degre", "discriminant"],
    "équation avec exponentielle": ["exponentielle"],
    "résolution d’équation": ["resoudre l'equation"],
    "inéquation": ["resoudre l'inequation", "inequation"],
    "équation différentielle": ["equation differentielle"],
    "équation différentielle homogène": ["equation differentielle", "sans second membre"],
    "théorème des valeurs intermédiaires": ["valeurs intermediaires", "corollaire du theoreme"],
    "valeurs intermédiaires": ["valeurs intermediaires"],
    "lecture graphique": ["a l'aide du graphique", "graphiquement"],
    "tableau de probabilités": ["loi de probabilite"],
    "pourcentage moyen": ["pourcentage"],
    "algorithme": ["def ", "algorithme"],
    "Python": ["python", "def ", "return"],
    "script python": ["python", "def ", "return"],
    "calcul de limite": ["calculer la limite"],
    "calcul de distance": ["calculer la distance"],
    "calcul d’angle": ["mesure de l'angle"],
    "géométrie dans l’espace": ["repere orthonorme", "l'espace"],
}

# Mots trop génériques à ignorer (articles, prépositions...).
MOTS_VIDES = {
    "de", "du", "des", "la", "le", "les", "un", "une", "à", "a", "et", "en",
    "au", "aux", "par", "sur", "avec", "pour", "dans", "ou", "son", "sa",
    "ses", "ce", "cet", "cette", "d", "l", "n", "qui", "que", "est", "sont",
}

# ==========================================
# REGROUPEMENT DES CHAPITRES EN GROS DOSSIERS
# ==========================================

GROUPES = {
    "Suites_et_Recurrence": [
        "convergence de suite", "démonstration par récurrence", "récurrence",
        "raisonnement par l’absurde", "suite", "suite arithmétique",
        "suite bornée", "suite convergente", "suite croissante",
        "suite divergente", "suite décroissante", "suite géométrique",
        "suite monotone", "suite récurrente", "suites",
    ],
    "Fonctions_Derivee_Variations": [
        "asymptote", "calcul de dérivée", "convexité", "dérivée",
        "dérivée seconde", "extremum", "fonction bornée", "fonction convexe",
        "fonction croissante", "fonction monotone", "fonction paire",
        "fonction polynôme", "fonction racine carrée", "Fonctions",
        "lecture graphique", "maximum", "minimum", "nombre dérivé",
        "signe d’une fonction", "tableau de variations",
        "tangente à la courbe", "variations de fonction",
        "équation de la tangente", "équation de tangente",
    ],
    "Fonction_Exponentielle_Logarithme": [
        "fonction exponentielle", "fonction logarithme",
        "fonction logarithme népérien", "équation avec exponentielle",
    ],
    "Limites": [
        "calcul de limite", "limite de fonction", "limite de suite",
        "théorème des valeurs intermédiaires", "valeurs intermédiaires",
    ],
    "Integrales_Primitives": [
        "calcul d’aire", "calcul d’intégrale", "intégrale",
        "intégration par parties", "primitive", "valeur moyenne",
        "valeur moyenne d’une fonction",
    ],
    "Probabilites": [
        "arbre pondéré", "Bienaymé-Tchebychev", "espérance",
        "inégalité de Bienaymé-Tchebychev", "inégalité de concentration",
        "loi binomiale", "loi de probabilité", "moyenne",
        "pourcentage moyen", "probabilité conditionnelle", "probabilités",
        "somme de variables aléatoires", "tableau de probabilités",
        "variable aléatoire", "variance", "évènements indépendants",
    ],
    "Denombrement": [
        "arrangements et combinaisons", "combinaison", "combinatoire",
        "dénombrement", "n-uplets",
    ],
    "Geometrie_Espace": [
        "calcul de distance", "distance d’un point à un plan",
        "distance d’un point à une droite", "distance point-plan",
        "droite et plan orthogonaux", "droite et plan parallèles",
        "droite orthogonal", "droites coplanaires", "droites non coplanaires",
        "droites parallèles", "droites perpendiculaires", "droites sécantes",
        "géométrie", "géométrie dans l’espace", "intersection de droites",
        "plan médiateur", "plan orthogonal", "plans orthogonaux",
        "plans parallèles", "plans perpendiculaires", "plans sécants",
        "points alignés", "points coplanaires", "points non alignés",
        "projeté orthogonal", "représentation paramétrique de droite",
        "équation de droite", "équation de plan",
        "équation paramétrique de droite",
    ],
    "Vecteurs": [
        "norme de vecteur", "produit scalaire", "vecteur directeur",
        "vecteur et plan orthogonaux", "vecteur normal",
        "vecteurs colinéaires", "vecteurs orthogonaux",
    ],
    "Aires_et_Volumes": [
        "aire de trapèze", "aire de triangle", "aire d’un disque", "cube",
        "sphère", "trapèze", "volume de pyramide", "volume de tétraèdre",
        "volume d’un cône", "volume pyramide", "volume tétraèdre",
    ],
    "Trigonometrie": [
        "calcul d’angle", "cosinus", "mesure d’angle", "sinus",
        "tangente d’angle", "triangle rectangle", "trigonométrie",
    ],
    "Equations_Inequations": [
        "inéquation", "résolution d’équation", "équation",
        "équation du second degré",
    ],
    "Equations_Differentielles": [
        "équation différentielle", "équation différentielle homogène",
    ],
    "Algorithmique_Python": [
        "algorithme", "Python", "script python",
    ],
    "QCM_VraiFaux": [
        "QCM", "Vrai-Faux",
    ],
}

CHAPITRE_VERS_DOSSIER = {
    chap: groupe for groupe, chapitres in GROUPES.items() for chap in chapitres
}

_chapitres_non_groupes = [c for c in CHAPITRES_CONNUS if c not in CHAPITRE_VERS_DOSSIER]
if _chapitres_non_groupes:
    raise ValueError(
        "Ces chapitres de CHAPITRES_CONNUS n'ont pas de groupe dans GROUPES "
        f"(vérifier l'orthographe / les accents) : {_chapitres_non_groupes}"
    )

def dossier_pour_chapitre(nom_chapitre):
    return CHAPITRE_VERS_DOSSIER.get(nom_chapitre, nom_chapitre)

# ---- Seuils de décision ----
SEUIL_VERIFICATION = 0.55
RATIO_DOMINANCE_INDEX = 0.70
SEUIL_AUTO = 0.40
RATIO_DOMINANCE_AUTO = 0.65
NB_CHAPITRES_AUTO = 2
SEUIL_AMBIGU = 0.80
TAILLE_FENETRE_COOCCURRENCE = 8

NOM_FICHIER_RAPPORT = "rapport_classification.jsonl"


# ==========================================
# FONCTIONS UTILITAIRES (PDF / images)
# ==========================================

def crop_white_margins(img):
    gray = img.convert('L')
    inv = ImageOps.invert(gray)
    bbox = inv.getbbox()
    if bbox:
        left = max(0, bbox[0] - 15)
        top = max(0, bbox[1] - 15)
        right = min(img.width, bbox[2] + 15)
        bottom = min(img.height, bbox[3] + 15)
        return img.crop((left, top, right, bottom))
    return img

def trouver_titre_sujet(doc, start_page):
    for p_idx in range(start_page, -1, -1):
        text = doc[p_idx].get_text("text")
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        if not lines:
            continue

        header_text = " ".join(lines[:8]).lower()

        if "baccalauréat" in header_text or "baccalaureat" in header_text or re.search(r'a\.?\s*p\.?\s*m\.?\s*e\.?\s*p', header_text):
            titre_propre = " ".join(lines[:5])
            return re.sub(r'\s+', ' ', titre_propre)

    return "Titre inconnu"

def extraire_tous_les_exercices(doc):
    exercises = {}
    current_exo_id = None
    counters_per_context = {}
    current_context = {"region": "Inconnu", "sujet": "", "mois": ""}

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text_lower = page.get_text("text").lower()

        found_new_region = False
        for key, val in REGIONS.items():
            if key in text_lower:
                current_context["region"] = val
                found_new_region = True
                break

        if found_new_region:
            current_context["sujet"] = ""
            current_context["mois"] = ""

        for key, val in SUJETS.items():
            if key in text_lower:
                current_context["sujet"] = val
                break

        for key, val in MOIS.items():
            if key in text_lower:
                current_context["mois"] = val
                break

        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if b.get("type") == 0:
                for l in b.get("lines", []):
                    line_text = "".join([s.get("text", "") for s in l.get("spans", [])]).strip()
                    match = re.search(r'(?i)^\s*(?:exercice|problème)\s*([0-9A-Za-z]+)', line_text)

                    if match:
                        exo_num = match.group(1).upper()
                        y_coord = l["spans"][0]["bbox"][1]

                        if current_exo_id and current_exo_id in exercises:
                            exercises[current_exo_id]["end_page"] = page_idx
                            exercises[current_exo_id]["end_y"] = max(0, y_coord - 15)

                        sig_parts = [current_context["region"]]
                        if current_context["mois"]: sig_parts.append(current_context["mois"])
                        if current_context["sujet"]: sig_parts.append(current_context["sujet"])
                        sig_parts.append(f"Exo_{exo_num}")

                        base_sig = "_".join(sig_parts)

                        if base_sig not in counters_per_context:
                            counters_per_context[base_sig] = 0
                        counters_per_context[base_sig] += 1

                        new_exo_id = f"{base_sig}_v{counters_per_context[base_sig]}"

                        titre_officiel = trouver_titre_sujet(doc, page_idx)

                        exercises[new_exo_id] = {
                            "id": new_exo_id,
                            "num": exo_num,
                            "start_page": page_idx,
                            "start_y": max(0, y_coord - 15),
                            "end_page": len(doc) - 1,
                            "end_y": doc[len(doc)-1].rect.height,
                            "folder_name": new_exo_id,
                            "titre_pdf_global": titre_officiel
                        }
                        current_exo_id = new_exo_id

    return exercises

def trouver_corrige_correspondant(exo_id_enonce, exos_corrige):
    if not exos_corrige:
        return None

    if exo_id_enonce in exos_corrige:
        return exos_corrige[exo_id_enonce]

    parts = exo_id_enonce.split('_')
    region = parts[0]
    v_part = parts[-1]

    match = re.search(r'(Exo_[0-9A-Za-z]+)', exo_id_enonce)
    if not match:
        return None
    exo_part = match.group(1)

    for c_id, c_info in exos_corrige.items():
        if region in c_id and exo_part in c_id and c_id.endswith(v_part):
            return c_info

    return None

def render_exercise_pages(doc, exo_info, matrix):
    """Renvoie la LISTE des images (une par page réellement occupée par
    l'exercice), sans les recoller. Nécessaire pour la pagination du bot
    Discord (v2 les recollait en une seule grande image)."""
    images = []
    for p_idx in range(exo_info["start_page"], exo_info["end_page"] + 1):
        page = doc[p_idx]
        rect = page.rect

        if p_idx == exo_info["start_page"]:
            rect.y0 = exo_info["start_y"]
        else:
            rect.y0 = 0

        if p_idx == exo_info["end_page"]:
            rect.y1 = exo_info["end_y"]
        else:
            rect.y1 = page.rect.height

        if rect.y0 >= rect.y1:
            continue

        pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        img = crop_white_margins(img)
        if img.width > 0 and img.height > 0:
            images.append(img)

    return images


# ==========================================
# CLASSIFICATION PAR CONTENU
# ==========================================

def normaliser_texte(s):
    s = s.lower()
    s = (s.replace('ﬁ', 'fi').replace('ﬂ', 'fl').replace('ﬀ', 'ff')
           .replace('ﬃ', 'ffi').replace('ﬄ', 'ffl'))
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s

def stem_mot(m):
    if len(m) > 4 and m.endswith('s'):
        return m[:-1]
    return m

def mots_significatifs(nom_chapitre):
    nom_norm = normaliser_texte(nom_chapitre)
    mots = re.findall(r'[a-z0-9]+', nom_norm)
    return [m for m in mots if m not in MOTS_VIDES and len(m) >= 3]

def _est_signal_specifique(s):
    if len(s.split()) >= 2:
        return True
    if re.search(r'[0-9_()\']', s):
        return True
    return False

def _construire_info_chapitres():
    info = {}
    for nom in CHAPITRES_CONNUS:
        mots = mots_significatifs(nom)
        synonymes_norm = [normaliser_texte(s) for s in SYNONYMES.get(nom, [])]
        info[nom] = {
            "mots": mots,
            "phrase": " ".join(mots),
            "synonymes": synonymes_norm,
        }
    return info

_INFO_CHAPITRES = _construire_info_chapitres()

def _construire_poids_mots():
    compte = {}
    for info in _INFO_CHAPITRES.values():
        for m in set(info["mots"]):
            compte[m] = compte.get(m, 0) + 1
    return {m: 1.0 / n for m, n in compte.items()}

_POIDS_MOTS = _construire_poids_mots()

def poids_mot(m):
    return _POIDS_MOTS.get(m, 1.0)

def compter_occurrences(mot, texte_norm, cap=3):
    base = stem_mot(mot)
    pattern = r'\b' + re.escape(base) + r's?\b'
    return min(len(re.findall(pattern, texte_norm)), cap)

def _mots_dans_fenetre(mots_stems, tokens, taille_fenetre=TAILLE_FENETRE_COOCCURRENCE):
    besoin = set(mots_stems)
    if len(besoin) < 2:
        return False

    fenetre = deque()
    compte = Counter()
    for tok in tokens:
        fenetre.append(tok)
        if tok in besoin:
            compte[tok] += 1
        if len(fenetre) > taille_fenetre:
            old = fenetre.popleft()
            if old in compte:
                compte[old] -= 1
                if compte[old] == 0:
                    del compte[old]
        if len(compte) >= len(besoin):
            return True
    return False

def score_chapitre(nom_chapitre, texte_norm):
    info = _INFO_CHAPITRES.get(nom_chapitre)
    if info is None:
        mots = mots_significatifs(nom_chapitre)
        info = {"mots": mots, "phrase": " ".join(mots), "synonymes": []}

    mots = info["mots"]
    if not mots:
        return 1.0

    poids_total = sum(poids_mot(m) for m in mots)
    if poids_total <= 0:
        return 0.0

    score_mots = sum(compter_occurrences(m, texte_norm) * poids_mot(m) for m in mots)
    score_mots_normalise = score_mots / (poids_total * 3)

    bonus = 0.0
    phrase = info["phrase"]
    if phrase and _est_signal_specifique(phrase) and phrase in texte_norm:
        bonus = 0.35

    if bonus == 0.0:
        for syn in info.get("synonymes", []):
            if syn and _est_signal_specifique(syn) and syn in texte_norm:
                bonus = 0.35
                break

    if bonus == 0.0:
        tokens = None
        mots_stems = [stem_mot(m) for m in mots]
        if len(set(mots_stems)) >= 2:
            tokens = [stem_mot(t) for t in re.findall(r'[a-z0-9]+', texte_norm)]
            if _mots_dans_fenetre(mots_stems, tokens):
                bonus = 0.25
        if bonus == 0.0:
            for syn in info.get("synonymes", []):
                syn_tokens = re.findall(r'[a-z0-9]+', syn)
                if len(syn_tokens) >= 2:
                    if tokens is None:
                        tokens = [stem_mot(t) for t in re.findall(r'[a-z0-9]+', texte_norm)]
                    syn_stems = [stem_mot(t) for t in syn_tokens]
                    if _mots_dans_fenetre(syn_stems, tokens):
                        bonus = 0.25
                        break

    return min(1.0, score_mots_normalise + bonus)

def tous_scores_chapitres(texte_norm):
    scores = [(score_chapitre(nom, texte_norm), nom) for nom in CHAPITRES_CONNUS]
    scores.sort(key=lambda x: x[0], reverse=True)
    return scores

def meilleurs_chapitres_par_contenu(classement, top_n=NB_CHAPITRES_AUTO, seuil=SEUIL_AUTO,
                                     ratio_dominance=RATIO_DOMINANCE_AUTO):
    if not classement or classement[0][0] < seuil:
        return []
    meilleur_score = classement[0][0]
    retenus = []
    for score, nom in classement[:top_n]:
        if score < seuil:
            break
        if score < meilleur_score * ratio_dominance:
            break
        retenus.append(nom)
    return retenus

def normaliser_nom_dossier(s):
    s = normaliser_texte(s)
    return re.sub(r'[^a-z0-9]', '', s)

def trouver_dossier_chapitre(nom_candidat, dossier_principal):
    if not os.path.isdir(dossier_principal):
        return nom_candidat

    candidat_norm = normaliser_nom_dossier(nom_candidat)
    meilleur_dossier = None
    meilleur_score = 0

    for nom_dossier in os.listdir(dossier_principal):
        chemin = os.path.join(dossier_principal, nom_dossier)
        if not os.path.isdir(chemin):
            continue
        dossier_norm = normaliser_nom_dossier(nom_dossier)
        if not dossier_norm:
            continue
        if candidat_norm == dossier_norm:
            return nom_dossier
        if candidat_norm in dossier_norm or dossier_norm in candidat_norm:
            score = min(len(candidat_norm), len(dossier_norm))
            if score > meilleur_score:
                meilleur_score = score
                meilleur_dossier = nom_dossier

    return meilleur_dossier if meilleur_dossier else nom_candidat

def extraire_texte_exercice(doc, exo_info, max_pages=None):
    textes = []
    debut = exo_info["start_page"]
    fin = exo_info["end_page"] if max_pages is None else min(exo_info["end_page"], debut + max_pages - 1)
    for p_idx in range(debut, fin + 1):
        textes.append(doc[p_idx].get_text("text"))
    return "\n".join(textes)


# ==========================================
# LECTURE DE L'INDEX (quand il existe)
# ==========================================

def lire_index_chapitres(doc_enonce, pages_idx):
    chapters_data = {}
    for p_num in pages_idx:
        if p_num < 0:
            p_num = len(doc_enonce) + p_num
        if p_num >= len(doc_enonce) or p_num < 0:
            continue

        text = doc_enonce[p_num].get_text("text")
        for line in text.split('\n'):
            match = re.search(r'^([a-zA-ZÀ-ÿ\s\-\'’]+),\s*(\d+(?:\s*,\s*\d+)*)', line.strip())
            if match:
                chap_name = match.group(1).strip()
                pages_str = match.group(2)
                pages_list = [int(p.strip()) for p in pages_str.split(',')]
                if chap_name not in chapters_data:
                    chapters_data[chap_name] = []
                chapters_data[chap_name].extend(pages_list)
    return chapters_data

def construire_candidats_par_exercice(chapters_data, exos_enonce):
    candidats = {exo_id: set() for exo_id in exos_enonce}
    for chap_name, pages in chapters_data.items():
        for p in pages:
            target_p = p - 1
            for exo_id, info in exos_enonce.items():
                if info["start_page"] <= target_p <= info["end_page"]:
                    candidats[exo_id].add(chap_name)
    return candidats


# ==========================================
# JOURNAL D'AUDIT
# ==========================================

def enregistrer_rapport(entry):
    chemin = os.path.join(DOSSIER_PRINCIPAL, NOM_FICHIER_RAPPORT)
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ==========================================
# CLASSEMENT + RANGEMENT D'UN EXERCICE
# ==========================================

def classer_et_filer_exercice(exo_id, info, candidats_index, doc_enonce, doc_corrige, exos_corrige, annee, matrix):
    texte_norm = normaliser_texte(extraire_texte_exercice(doc_enonce, info))

    classement = tous_scores_chapitres(texte_norm)
    meilleur_score = classement[0][0] if classement else 0.0
    meilleur_chap = classement[0][1] if classement else None
    deuxieme_score = classement[1][0] if len(classement) > 1 else 0.0
    deuxieme_chap = classement[1][1] if len(classement) > 1 else None

    chapitres_valides = []
    chapitres_rejetes = []
    scores_index = {}
    for chap_name in candidats_index:
        s = score_chapitre(chap_name, texte_norm)
        scores_index[chap_name] = round(s, 3)
        domine = meilleur_score > 0 and s < meilleur_score * RATIO_DOMINANCE_INDEX
        if s >= SEUIL_VERIFICATION and not domine:
            chapitres_valides.append(chap_name)
        else:
            raison = "score_insuffisant" if s < SEUIL_VERIFICATION else f"domine_par_{meilleur_chap}({round(meilleur_score,3)})"
            chapitres_rejetes.append({"chapitre": chap_name, "score": round(s, 3), "raison": raison})

    if chapitres_valides:
        origine = "index (vérifié)"
    else:
        chapitres_valides = meilleurs_chapitres_par_contenu(classement)
        origine = "contenu (index rejeté)" if candidats_index else "contenu (pas d'index)"

    if not chapitres_valides:
        chapitres_valides = ["A_classer"]
        origine = "aucune correspondance trouvée"

    ambigu = (
        meilleur_score > 0
        and deuxieme_score >= meilleur_score * SEUIL_AMBIGU
        and deuxieme_chap not in chapitres_valides
    )

    enregistrer_rapport({
        "exo_id": exo_id,
        "annee": annee,
        "chapitres_retenus": chapitres_valides,
        "origine": origine,
        "chapitres_index_proposes": scores_index,
        "chapitres_index_rejetes": chapitres_rejetes,
        "top3_contenu": [{"chapitre": c, "score": round(s, 3)} for s, c in classement[:3]],
        "ambigu": ambigu,
    })
    if ambigu:
        print(f"   [AMBIGU] {exo_id} : retenu={chapitres_valides} "
              f"mais '{deuxieme_chap}' est proche ({round(deuxieme_score,3)} vs {round(meilleur_score,3)}) -> à vérifier")

    folder_name = f"{annee}_{info['folder_name']}"
    groupes_cibles = []
    for chap_name in chapitres_valides:
        groupe = dossier_pour_chapitre(chap_name)
        if groupe not in groupes_cibles:
            groupes_cibles.append(groupe)

    dossiers_a_creer = []
    for groupe in groupes_cibles:
        dossier_chapitre = trouver_dossier_chapitre(groupe, DOSSIER_PRINCIPAL)
        safe_chap = re.sub(r'[\\/*?:"<>|]', "", dossier_chapitre).strip()
        full_folder_path = os.path.join(DOSSIER_PRINCIPAL, safe_chap, folder_name)
        if not os.path.exists(os.path.join(full_folder_path, "infos.json")):
            dossiers_a_creer.append(full_folder_path)

    if not dossiers_a_creer:
        return

    pages_enonce = render_exercise_pages(doc_enonce, info, matrix)
    corr_info = trouver_corrige_correspondant(exo_id, exos_corrige)
    pages_corrige = render_exercise_pages(doc_corrige, corr_info, matrix) if (doc_corrige and corr_info) else []

    for full_folder_path in dossiers_a_creer:
        os.makedirs(full_folder_path, exist_ok=True)

        for i, img in enumerate(pages_enonce, start=1):
            img.save(os.path.join(full_folder_path, f"enonce_{i}.png"))

        has_corrige = len(pages_corrige) > 0
        for i, img in enumerate(pages_corrige, start=1):
            img.save(os.path.join(full_folder_path, f"corrige_{i}.png"))

        metadata = {
            "annee": annee,
            "has_corrige": has_corrige,
            "nb_pages_enonce": len(pages_enonce),
            "nb_pages_corrige": len(pages_corrige),
            "titre_pdf_global": info["titre_pdf_global"],
            "classement": origine,
            "chapitres_detailles": chapitres_valides,
            "chapitres_index_rejetes": chapitres_rejetes if chapitres_rejetes else None,
            "ambigu": ambigu,
            "source_internet": "https://www.apmep.fr/Annales-Specialite-Maths-depuis-2021"
        }

        json_path = os.path.join(full_folder_path, "infos.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=4)


# ==========================================
# TRAITEMENT D'UN PDF (avec ou sans index)
# ==========================================

def traiter_pdf(pdf_path, pages_idx, matrix):
    if not os.path.exists(pdf_path):
        print(f" -> Attention : Le fichier '{pdf_path}' est introuvable, on passe au suivant.")
        return

    annee_match = re.search(r'20\d{2}', pdf_path)
    annee = annee_match.group(0) if annee_match else "Inconnue"

    mode = "avec index" if pages_idx is not None else "SANS index (classification automatique)"
    print(f"--- Traitement de {pdf_path} (Année {annee}) — {mode} ---")

    try:
        doc_enonce = fitz.open(pdf_path)
    except Exception as e:
        print(f" -> Erreur lors de l'ouverture du PDF de l'énoncé : {e}\n")
        return

    doc_corrige = None
    corrige_path = MODELE_NOM_CORRIGE.format(annee=annee)
    if os.path.exists(corrige_path):
        doc_corrige = fitz.open(corrige_path)
        print(f" -> Corrigé local trouvé : '{corrige_path}'.")
    else:
        print(f" -> Attention : Aucun corrigé trouvé à '{corrige_path}'.")

    print(" -> Cartographie des exercices par régions et sujets...")
    exos_enonce = extraire_tous_les_exercices(doc_enonce)
    exos_corrige = extraire_tous_les_exercices(doc_corrige) if doc_corrige else {}

    candidats_par_exercice = {exo_id: set() for exo_id in exos_enonce}
    if pages_idx is not None:
        chapters_data = lire_index_chapitres(doc_enonce, pages_idx)
        candidats_par_exercice = construire_candidats_par_exercice(chapters_data, exos_enonce)

    print(f" -> {len(exos_enonce)} exercice(s) détecté(s). Vérification du contenu et classement...")

    for exo_id, info in exos_enonce.items():
        classer_et_filer_exercice(
            exo_id, info, candidats_par_exercice.get(exo_id, set()),
            doc_enonce, doc_corrige, exos_corrige, annee, matrix
        )

    doc_enonce.close()
    if doc_corrige:
        doc_corrige.close()

    print(f" -> Terminé pour l'année {annee}.\n")


# ==========================================
# PROGRAMME PRINCIPAL
# ==========================================

def process_multiple_pdfs():
    if len(CHEMINS_PDF) != len(PAGES_INDEX):
        print("Erreur : La liste CHEMINS_PDF et la liste PAGES_INDEX doivent avoir le même nombre d'éléments.")
        return

    print(f"=== Début du traitement de {len(CHEMINS_PDF)} PDF(s) ===\n")
    os.makedirs(DOSSIER_PRINCIPAL, exist_ok=True)
    matrix = fitz.Matrix(3, 3)

    entrees = list(zip(CHEMINS_PDF, PAGES_INDEX))
    entrees_avec_index = [e for e in entrees if e[1] is not None]
    entrees_sans_index = [e for e in entrees if e[1] is None]

    print(f" -> {len(entrees_avec_index)} PDF avec index (traités en premier), "
          f"{len(entrees_sans_index)} PDF sans index (traités en dernier).\n")

    for pdf_path, pages_idx in entrees_avec_index:
        traiter_pdf(pdf_path, pages_idx, matrix)

    for pdf_path, pages_idx in entrees_sans_index:
        traiter_pdf(pdf_path, pages_idx, matrix)

    rapport = os.path.join(DOSSIER_PRINCIPAL, NOM_FICHIER_RAPPORT)
    print(f"=== Terminé ! Tes duos 'énoncé/corrigé' géolocalisés + les fichiers JSON t'attendent dans '{DOSSIER_PRINCIPAL}'. ===")
    print(f"=== Journal d'audit du classement : '{rapport}' (cherche \"ambigu\": true pour repérer les cas à vérifier en priorité) ===")

if __name__ == "__main__":
    process_multiple_pdfs()
