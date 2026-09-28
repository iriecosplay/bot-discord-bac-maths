import json
import os
import asyncio


class GestionnaireSessions:
    """Garde la trace du salon privé actif de chaque utilisateur, persisté
    sur disque pour survivre à un redémarrage du bot (Railway peut
    redéployer à tout moment)."""

    def __init__(self, chemin_fichier):
        self.chemin_fichier = chemin_fichier
        self.lock = asyncio.Lock()
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
            json.dump(self.data, f)

    async def salon_actif(self, user_id):
        async with self.lock:
            return self.data.get(str(user_id))

    async def ouvrir(self, user_id, channel_id):
        async with self.lock:
            self.data[str(user_id)] = channel_id
            self._ecrire()

    async def fermer(self, user_id):
        async with self.lock:
            self.data.pop(str(user_id), None)
            self._ecrire()

    async def fermer_par_channel(self, channel_id):
        async with self.lock:
            uid = next((k for k, v in self.data.items() if v == channel_id), None)
            if uid:
                self.data.pop(uid, None)
                self._ecrire()
