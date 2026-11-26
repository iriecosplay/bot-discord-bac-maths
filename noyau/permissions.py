"""Système de permissions unique pour toutes les commandes du bot.

Hiérarchie (du plus bas au plus haut) :
    0   Membre
    0.5 Junior Mod        (rôle JUNIOR_MOD_ROLE_ID)
    1   Modérateur        (rôle MOD_ROLE_ID)
    2   PA Test           (rôle PA_TEST_ROLE_ID)
    3   Staff / Admin     (rôle STAFF / ADMIN, ou permission Administrateur)
    4   Saint             (rôle SAINT_ROLE_ID)
    5   Owner             (OWNER_ID)
« Perm Jail » est un rôle indépendant : seul lui (ou l'owner) peut envoyer en prison.

Utilisation sur une commande :

    @commands.hybrid_command(...)
    @niveau(MOD)
    async def warn(self, ctx, ...): ...

Le niveau requis est mémorisé dans `command.extras["niveau"]`, ce qui permet à
/aide d'afficher automatiquement qui peut utiliser quoi.
"""
import discord
from discord.ext import commands

from noyau import etat

MEMBRE, JUNIOR, MOD, PA_TEST, STAFF, SAINT, OWNER = 0, 0.5, 1, 2, 3, 4, 5

NOMS_NIVEAUX = {
    MEMBRE: "👤 Membre", JUNIOR: "🔸 Junior Mod", MOD: "🔹 Modérateur", PA_TEST: "🔷 PA Test",
    STAFF: "🛡️ Staff", SAINT: "⚔️ Saint", OWNER: "👑 Owner",
}


class PermissionRefusee(commands.CheckFailure):
    def __init__(self, texte):
        super().__init__(texte)
        self.texte = texte


def _marquer(cmd_ou_fonction, cle, valeur):
    cible = cmd_ou_fonction
    if isinstance(cible, commands.Command):
        cible.extras[cle] = valeur
    else:
        extras = getattr(cible, "__commands_extras__", {})
        extras[cle] = valeur
        cible.__commands_extras__ = extras
    return cible


def niveau(minimum: float, message: str | None = None):
    """Exige un niveau de la hiérarchie (l'owner passe toujours)."""
    async def predicate(ctx):
        if ctx.guild is None:
            raise PermissionRefusee("Cette commande ne marche que sur le serveur.")
        if etat.is_owner(ctx.author.id) or etat.has_min_perm(ctx.author, minimum):
            return True
        raise PermissionRefusee(message or f"Il faut être au moins **{NOMS_NIVEAUX[minimum]}** pour utiliser cette commande.")

    def deco(f):
        f = commands.check(predicate)(f)
        return _marquer(f, "niveau", minimum)
    return deco


def perm_jail():
    async def predicate(ctx):
        if etat.is_owner(ctx.author.id) or etat.has_perm_jail(ctx.author):
            return True
        raise PermissionRefusee("Seuls les membres ayant le rôle **Perm Jail** peuvent utiliser cette commande.")

    def deco(f):
        f = commands.check(predicate)(f)
        return _marquer(f, "niveau", "perm_jail")
    return deco


def administrateur():
    """Permission Discord « Administrateur » (ou owner)."""
    async def predicate(ctx):
        if etat.is_owner(ctx.author.id) or (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator):
            return True
        raise PermissionRefusee("Il faut la permission **Administrateur** pour utiliser cette commande.")

    def deco(f):
        f = commands.check(predicate)(f)
        return _marquer(f, "niveau", "admin")
    return deco


def owner_seulement():
    async def predicate(ctx):
        if etat.is_owner(ctx.author.id):
            return True
        raise PermissionRefusee("Seul le créateur du serveur peut utiliser cette commande.")

    def deco(f):
        f = commands.check(predicate)(f)
        return _marquer(f, "niveau", OWNER)
    return deco


def label_niveau(valeur) -> str:
    if valeur == "perm_jail":
        return "⛓️ Perm Jail"
    if valeur == "admin":
        return "🔒 Administrateur"
    return NOMS_NIVEAUX.get(valeur, "👤 Membre")


def verifier_cible(ctx, cible: discord.Member, action="sanctionner"):
    """Lève PermissionRefusee si l'auteur ne peut pas viser ce membre (hiérarchie)."""
    if not etat.can_target(ctx.author, cible):
        raise PermissionRefusee(f"Tu ne peux pas {action} ce membre (hiérarchie).")
