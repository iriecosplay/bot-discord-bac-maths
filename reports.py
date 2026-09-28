import json
import os
import uuid


class GestionnaireSignalements:
    """Persiste les signalements en attente de validation par un
    modérateur, pour pouvoir ré-enregistrer les boutons de confirmation
    comme des vues persistantes même après un redémarrage du bot."""

    def __init__(self, chemin_fichier):
        self.chemin_fichier = chemin_fichier
        self.data = self._lire()

    def _lire(self):
        if os.path.exists(self.chemin_fichier):
            try:
                with open(self.chemin_fichier, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _ecrire(self):
        os.makedirs(os.path.dirname(self.chemin_fichier) or ".", exist_ok=True)
        with open(self.chemin_fichier, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def creer(self, type_signalement, exo_chemin, ancien_chapitre, nouveau_chapitre, auteur_id):
        """type_signalement : 'mauvais_chapitre' ou 'mauvais_corrige'."""
        report_id = uuid.uuid4().hex[:8]
        self.data[report_id] = {
            "type": type_signalement,
            "exo_chemin": exo_chemin,
            "ancien_chapitre": ancien_chapitre,
            "nouveau_chapitre": nouveau_chapitre,
            "auteur_id": auteur_id,
            "traite": False,
        }
        self._ecrire()
        return report_id

    def get(self, report_id):
        return self.data.get(report_id)

    def marquer_traite(self, report_id):
        if report_id in self.data:
            self.data[report_id]["traite"] = True
            self._ecrire()

    def en_attente(self):
        return {rid: r for rid, r in self.data.items() if not r.get("traite")}
