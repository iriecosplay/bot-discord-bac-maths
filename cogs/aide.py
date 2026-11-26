"""❓ /aide : aide interactive générée automatiquement à partir des commandes.

Chaque commande déclare sa description, son usage et son niveau requis
(noyau/permissions.py) : l'aide les lit, les range par catégorie et n'affiche
à chaque personne que ce qu'elle a le droit d'utiliser.
"""
import discord
from discord import app_commands
from discord.ext import commands

from noyau import etat
from noyau.etat import hexc
from noyau.permissions import label_niveau

# Catégorie d'aide → (emoji, description, noms de cogs)
CATEGORIES = {
    "exos":       ("📝", "Exercices de bac", ["Exercices"]),
    "progression": ("📈", "XP, niveaux, vocal, giveaways", ["Progression", "Statistiques", "Giveaways", "Vocaux"]),
    "infos":      ("ℹ️", "Infos serveur & membres", ["Infos"]),
    "sanctions":  ("⚖️", "Prison, warns, mute, kick, ban", ["Sanctions"]),
    "salons":     ("🧹", "Nettoyage & salons", ["Salons"]),
    "roles":      ("🎭", "Rôles & surnoms", ["Rôles"]),
    "admin":      ("🔐", "Administration & accueil", ["Administration", "Accueil"]),
}

# Fonctionnalités sans commande, décrites pour que tout le monde sache qu'elles existent
AUTOMATIQUE = {
    "exos": "Ouvre le menu dans <#1512035664961736724> : exercice au hasard ou par chapitre, salon privé, corrigé, signalement.",
    "progression": "Tu gagnes de l'XP en écrivant (1×/min) et en vocal (bonus en salon d'aide). Les rôles 🔰 Novice → 🔺 Ascendant arrivent tout seuls.",
    "admin": "Automatique : anti-raid, anti-spam, tickets, avis, panneaux de rôles/couleurs/visibilité, salon de stats, logs d'arrivée/départ.",
}


def niveau_cmd(cmd) -> object:
    extras = dict(getattr(cmd, "extras", {}) or {})
    cb = getattr(cmd, "callback", None)
    extras.update(getattr(cb, "__commands_extras__", {}) or {})
    return extras.get("niveau", 0)


def peut_utiliser(member, niv) -> bool:
    if etat.is_owner(member.id):
        return True
    if niv == "perm_jail":
        return etat.has_perm_jail(member)
    if niv in ("admin", "giveaway"):
        return member.guild_permissions.administrator or (niv == "giveaway" and etat.has_min_perm(member, 3))
    return etat.has_min_perm(member, niv)


class Entree:
    def __init__(self, nom, description, usage, niv, slash, prefixe):
        self.nom, self.description, self.usage, self.niv = nom, description, usage, niv
        self.slash, self.prefixe = slash, prefixe

    def ligne(self):
        forme = []
        if self.prefixe:
            forme.append(f"`+{self.nom}{' ' + self.usage if self.usage else ''}`")
        if self.slash:
            forme.append(f"`/{self.nom}`")
        niv = "" if self.niv in (0, None) else f" · *{label_niveau(self.niv) if self.niv != 'giveaway' else '🎉 Staff giveaway'}*"
        return f"{' · '.join(forme)}{niv}\n╰ {self.description or '—'}"


def collecter(bot) -> dict[str, list[Entree]]:
    par_cog: dict[str, list[Entree]] = {}
    vus = set()
    for cmd in bot.commands:
        if cmd.hidden:
            continue
        slash = isinstance(cmd, (commands.HybridCommand, commands.HybridGroup))
        par_cog.setdefault(cmd.cog_name or "", []).append(
            Entree(cmd.name, cmd.description or cmd.short_doc, cmd.usage or "", niveau_cmd(cmd), slash, True))
        vus.add(cmd.name)
    for cog in bot.cogs.values():
        for ac in cog.get_app_commands():
            if ac.name in vus:
                continue
            admin = bool(ac.default_permissions and ac.default_permissions.administrator) or "[Admin]" in (ac.description or "")
            par_cog.setdefault(cog.qualified_name, []).append(
                Entree(ac.name, (ac.description or "").replace("[Admin] ", ""), "", "admin" if admin else 0, True, False))
    return par_cog


def embed_categorie(bot, member, cle):
    emoji, titre, cogs = CATEGORIES[cle]
    par_cog = collecter(bot)
    entrees = [e for c in cogs for e in par_cog.get(c, []) if peut_utiliser(member, e.niv)]
    e = discord.Embed(color=hexc("#5865F2"), title=f"{emoji} {titre}")
    texte = ""
    if cle in AUTOMATIQUE:
        texte += f"> {AUTOMATIQUE[cle]}\n\n"
    texte += "\n".join(x.ligne() for x in sorted(entrees, key=lambda x: x.nom)) or "*Aucune commande accessible pour toi ici.*"
    e.description = texte[:4096]
    e.set_footer(text="+commande ou /commande · <obligatoire> [facultatif]")
    return e


def embed_accueil(bot, member):
    par_cog = collecter(bot)
    e = discord.Embed(color=hexc("#5865F2"), title="❓ Aide — Bot Mathematic",
                      description="Toutes les commandes marchent avec **`+`** (ou `!`) **et** en **`/`**.\n"
                                  "Choisis une catégorie dans le menu ci-dessous.\n\n"
                                  f"Ton niveau : **{etat.perm_label(etat.perm_level(member))}**"
                                  + (" · ⛓️ Perm Jail" if etat.has_perm_jail(member) else ""))
    for cle, (emoji, titre, cogs) in CATEGORIES.items():
        n = sum(1 for c in cogs for x in par_cog.get(c, []) if peut_utiliser(member, x.niv))
        if n or cle in AUTOMATIQUE:
            e.add_field(name=f"{emoji} {titre}", value=f"{n} commande(s)", inline=True)
    return e


class MenuAide(discord.ui.View):
    def __init__(self, bot, member):
        super().__init__(timeout=300)
        self.bot, self.member = bot, member
        par_cog = collecter(bot)
        options = [discord.SelectOption(label="Accueil", value="_accueil", emoji="🏠")]
        for cle, (emoji, titre, cogs) in CATEGORIES.items():
            if cle in AUTOMATIQUE or any(peut_utiliser(member, x.niv) for c in cogs for x in par_cog.get(c, [])):
                options.append(discord.SelectOption(label=titre, value=cle, emoji=emoji))
        sel = discord.ui.Select(placeholder="📂 Choisis une catégorie…", options=options)
        sel.callback = self._choix
        self.add_item(sel)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("Tape `/aide` pour ouvrir ta propre aide 😉", ephemeral=True)
            return False
        return True

    async def _choix(self, interaction: discord.Interaction):
        v = interaction.data["values"][0]
        e = embed_accueil(self.bot, self.member) if v == "_accueil" else embed_categorie(self.bot, self.member, v)
        await interaction.response.edit_message(embed=e, view=self)


class Aide(commands.Cog, name="Aide"):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="aide", aliases=["help", "commandes"], description="Afficher toutes les commandes du bot.",
                             usage="[catégorie]")
    @app_commands.describe(categorie="Catégorie à afficher directement")
    @app_commands.choices(categorie=[app_commands.Choice(name=v[1], value=k) for k, v in CATEGORIES.items()])
    async def aide(self, ctx, categorie: str | None = None):
        member = ctx.author
        if categorie and categorie.lower() in CATEGORIES:
            e = embed_categorie(self.bot, member, categorie.lower())
        else:
            e = embed_accueil(self.bot, member)
        await ctx.reply(embed=e, view=MenuAide(self.bot, member), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Aide(bot))
