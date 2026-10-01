import os
import json
import asyncio

import discord
from discord.ext import commands

import config
from setup_data import preparer_donnees
from data_index import IndexExercices
from sessions import GestionnaireSessions
from reports import GestionnaireSignalements

# ==========================================
# INITIALISATION
# ==========================================

preparer_donnees()

index_exercices = IndexExercices(config.DATA_DIR)
gestion_sessions = GestionnaireSessions(config.FICHIER_SESSIONS)
gestion_signalements = GestionnaireSignalements(config.FICHIER_SIGNALEMENTS)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

_categorie_id_cache = {}


# ==========================================
# UTILITAIRES
# ==========================================

async def obtenir_ou_creer_categorie(guild):
    if guild.id in _categorie_id_cache:
        cat = guild.get_channel(_categorie_id_cache[guild.id])
        if cat:
            return cat

    for cat in guild.categories:
        if cat.name == config.NOM_CATEGORIE_SESSIONS:
            _categorie_id_cache[guild.id] = cat.id
            return cat

    categorie_parente = guild.get_channel(config.CATEGORIE_PARENTE_ID)
    position = (categorie_parente.position + 1) if categorie_parente else None
    nouvelle = await guild.create_category(config.NOM_CATEGORIE_SESSIONS, position=position)
    _categorie_id_cache[guild.id] = nouvelle.id
    return nouvelle


async def creer_salon_session(interaction: discord.Interaction, exercice):
    guild = interaction.guild
    user = interaction.user

    salon_existant_id = await gestion_sessions.salon_actif(user.id)
    if salon_existant_id:
        salon_existant = guild.get_channel(salon_existant_id)
        if salon_existant:
            await interaction.response.send_message(
                f"Tu as déjà une session en cours : {salon_existant.mention}. "
                f"Termine-la avant d'en ouvrir une nouvelle.",
                ephemeral=True,
            )
            return
        await gestion_sessions.fermer(user.id)

    await interaction.response.defer(ephemeral=True)

    categorie = await obtenir_ou_creer_categorie(guild)

    # Masque le salon pour tout le monde sauf l'utilisateur et le bot
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, attach_files=True, embed_links=True
        ),
    }

    nom_salon = f"exo-{user.name}".lower().replace(" ", "-")[:90]
    salon = await guild.create_text_channel(nom_salon, category=categorie, overwrites=overwrites)

    await gestion_sessions.ouvrir(user.id, salon.id)
    await interaction.followup.send(f"Ton exercice est prêt ici : {salon.mention}", ephemeral=True)
    await envoyer_exercice(salon, exercice, page=1)


async def envoyer_exercice(salon, exercice, page):
    embed = discord.Embed(
        title=f"📘 {exercice.chapitre.replace('_', ' ')}",
        description=f"Année {exercice.annee} — {exercice.region.replace('_', ' ')}",
        color=discord.Color.blurple(),
    )
    if exercice.nb_pages_enonce > 1:
        embed.set_footer(text=f"Page {page}/{exercice.nb_pages_enonce}")

    chemin_image = exercice.chemin_page_enonce(page)
    if not os.path.exists(chemin_image):
        await salon.send("⚠️ Image introuvable pour cet exercice, désolé.")
        return

    fichier = discord.File(chemin_image, filename="enonce.png")
    embed.set_image(url="attachment://enonce.png")

    vue = discord.ui.View(timeout=None)
    vue.add_item(BoutonNavigationExercice("prev", exercice.chapitre, exercice.id, page, disabled=(page <= 1)))
    vue.add_item(BoutonNavigationExercice("next", exercice.chapitre, exercice.id, page, disabled=(page >= exercice.nb_pages_enonce)))
    vue.add_item(BoutonVoirCorrige(exercice.chapitre, exercice.id, disabled=(exercice.nb_pages_corrige == 0)))
    vue.add_item(BoutonSignaler(exercice.chapitre, exercice.id))
    vue.add_item(BoutonTerminerSession())

    await salon.send(embed=embed, file=fichier, view=vue)


async def envoyer_corrige(salon, exercice, page):
    embed = discord.Embed(title="📖 Corrigé", color=discord.Color.green())
    if exercice.nb_pages_corrige > 1:
        embed.set_footer(text=f"Page {page}/{exercice.nb_pages_corrige}")

    chemin_image = exercice.chemin_page_corrige(page)
    if not os.path.exists(chemin_image):
        await salon.send("⚠️ Image de corrigé introuvable, désolé.")
        return

    fichier = discord.File(chemin_image, filename="corrige.png")
    embed.set_image(url="attachment://corrige.png")

    vue = None
    if exercice.nb_pages_corrige > 1:
        vue = discord.ui.View(timeout=None)
        vue.add_item(BoutonNavigationCorrige("prev", exercice.chapitre, exercice.id, page, disabled=(page <= 1)))
        vue.add_item(BoutonNavigationCorrige("next", exercice.chapitre, exercice.id, page, disabled=(page >= exercice.nb_pages_corrige)))

    await salon.send(embed=embed, file=fichier, view=vue)


async def publier_signalement(client, report_id):
    signalement = gestion_signalements.get(report_id)
    if not signalement:
        return
    salon_logs = client.get_channel(config.SALON_LOGS_ID)
    if salon_logs is None:
        print("⚠️ Salon de logs introuvable, vérifie SALON_LOGS_ID.")
        return

    exo_nom = os.path.basename(signalement["exo_chemin"])
    if signalement["type"] == "mauvais_chapitre":
        description = (
            f"**Exercice :** `{exo_nom}`\n"
            f"**Chapitre actuel :** {signalement['ancien_chapitre']}\n"
            f"**Chapitre proposé :** {signalement['nouveau_chapitre']}\n"
            f"**Signalé par :** <@{signalement['auteur_id']}>"
        )
    else:
        description = (
            f"**Exercice :** `{exo_nom}`\n"
            f"**Chapitre :** {signalement['ancien_chapitre']}\n"
            f"**Problème :** le corrigé ne correspond pas au sujet\n"
            f"**Signalé par :** <@{signalement['auteur_id']}>"
        )

    embed = discord.Embed(title="⚠️ Nouveau signalement", description=description, color=discord.Color.orange())
    await salon_logs.send(embed=embed, view=VueConfirmationSignalement(report_id))


def _autorise_confirmation(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        return True
    role = interaction.guild.get_role(config.ROLE_CONFIRMATION_ID)
    return role in interaction.user.roles if role else False


# ==========================================
# VUES (BOUTONS / MENUS)
# ==========================================

class BoutonNavigationExercice(discord.ui.DynamicItem[discord.ui.Button],
                                template=r'exo:nav:(?P<action>prev|next):(?P<chapitre>[^|]+)\|(?P<id>[^|]+)\|(?P<page>\d+)'):
    def __init__(self, action, chapitre, exo_id, page, disabled=False):
        super().__init__(discord.ui.Button(
            label="◀️" if action == "prev" else "▶️",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=disabled,
            custom_id=f"exo:nav:{action}:{chapitre}|{exo_id}|{page}",
        ))
        self.action, self.chapitre, self.exo_id, self.page = action, chapitre, exo_id, page

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], match["chapitre"], match["id"], int(match["page"]))

    async def callback(self, interaction: discord.Interaction):
        exo = index_exercices.trouver(self.chapitre, self.exo_id)
        if exo is None:
            await interaction.response.send_message("Cet exercice n'existe plus.", ephemeral=True)
            return
        await interaction.response.defer()
        nouvelle_page = self.page - 1 if self.action == "prev" else self.page + 1
        await envoyer_exercice(interaction.channel, exo, nouvelle_page)


class BoutonNavigationCorrige(discord.ui.DynamicItem[discord.ui.Button],
                               template=r'cor:nav:(?P<action>prev|next):(?P<chapitre>[^|]+)\|(?P<id>[^|]+)\|(?P<page>\d+)'):
    def __init__(self, action, chapitre, exo_id, page, disabled=False):
        super().__init__(discord.ui.Button(
            label="◀️" if action == "prev" else "▶️",
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
            custom_id=f"cor:nav:{action}:{chapitre}|{exo_id}|{page}",
        ))
        self.action, self.chapitre, self.exo_id, self.page = action, chapitre, exo_id, page

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], match["chapitre"], match["id"], int(match["page"]))

    async def callback(self, interaction: discord.Interaction):
        exo = index_exercices.trouver(self.chapitre, self.exo_id)
        if exo is None:
            await interaction.response.send_message("Cet exercice n'existe plus.", ephemeral=True)
            return
        await interaction.response.defer()
        nouvelle_page = self.page - 1 if self.action == "prev" else self.page + 1
        await envoyer_corrige(interaction.channel, exo, nouvelle_page)


class BoutonVoirCorrige(discord.ui.DynamicItem[discord.ui.Button],
                         template=r'exo:corrige:(?P<chapitre>[^|]+)\|(?P<id>[^|]+)'):
    def __init__(self, chapitre, exo_id, disabled=False):
        super().__init__(discord.ui.Button(
            label="📖 Pas de corrigé" if disabled else "📖 Voir le corrigé",
            style=discord.ButtonStyle.primary,
            row=1,
            disabled=disabled,
            custom_id=f"exo:corrige:{chapitre}|{exo_id}",
        ))
        self.chapitre, self.exo_id = chapitre, exo_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["chapitre"], match["id"])

    async def callback(self, interaction: discord.Interaction):
        exo = index_exercices.trouver(self.chapitre, self.exo_id)
        if exo is None:
            await interaction.response.send_message("Cet exercice n'existe plus.", ephemeral=True)
            return
        await interaction.response.defer()
        await envoyer_corrige(interaction.channel, exo, page=1)


class BoutonSignaler(discord.ui.DynamicItem[discord.ui.Button],
                      template=r'exo:signaler:(?P<chapitre>[^|]+)\|(?P<id>[^|]+)'):
    def __init__(self, chapitre, exo_id):
        super().__init__(discord.ui.Button(
            label="⚠️ Signaler un problème", style=discord.ButtonStyle.danger, row=2,
            custom_id=f"exo:signaler:{chapitre}|{exo_id}",
        ))
        self.chapitre, self.exo_id = chapitre, exo_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["chapitre"], match["id"])

    async def callback(self, interaction: discord.Interaction):
        exo = index_exercices.trouver(self.chapitre, self.exo_id)
        if exo is None:
            await interaction.response.send_message("Cet exercice n'existe plus.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Quel est le problème ?", view=VueChoixSignalement(exo), ephemeral=True
        )


class BoutonTerminerSession(discord.ui.DynamicItem[discord.ui.Button], template=r'exo:terminer'):
    def __init__(self):
        super().__init__(discord.ui.Button(
            label="✅ Terminer la session", style=discord.ButtonStyle.gray, row=2, custom_id="exo:terminer",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Session terminée, ce salon va être supprimé.", ephemeral=True)
        await gestion_sessions.fermer_par_channel(interaction.channel.id)
        await asyncio.sleep(3)
        await interaction.channel.delete()


class VueChoixSignalement(discord.ui.View):
    def __init__(self, exercice):
        super().__init__(timeout=120)
        self.exercice = exercice

    @discord.ui.button(label="Le sujet n'est pas dans le bon chapitre", style=discord.ButtonStyle.danger)
    async def mauvais_chapitre(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Dans quel chapitre ce sujet devrait-il aller ?",
            view=VueSelectionNouveauChapitre(self.exercice),
            ephemeral=True,
        )

    @discord.ui.button(label="Le corrigé ne correspond pas", style=discord.ButtonStyle.danger)
    async def mauvais_corrige(self, interaction: discord.Interaction, button: discord.ui.Button):
        report_id = gestion_signalements.creer(
            "mauvais_corrige", self.exercice.chemin, self.exercice.chapitre, None, interaction.user.id
        )
        await publier_signalement(interaction.client, report_id)
        await interaction.response.edit_message(content="Signalement envoyé, merci !", view=None)


class VueSelectionNouveauChapitre(discord.ui.View):
    def __init__(self, exercice):
        super().__init__(timeout=120)
        self.exercice = exercice
        options = [
            discord.SelectOption(label=ch.replace("_", " "), value=ch)
            for ch in index_exercices.chapitres() if ch != exercice.chapitre
        ][:25]
        select = discord.ui.Select(placeholder="Choisir le bon chapitre", options=options)
        select.callback = self._callback
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction):
        nouveau_chapitre = interaction.data["values"][0]
        report_id = gestion_signalements.creer(
            "mauvais_chapitre", self.exercice.chemin, self.exercice.chapitre, nouveau_chapitre, interaction.user.id
        )
        await publier_signalement(interaction.client, report_id)
        await interaction.response.edit_message(content="Signalement envoyé, merci !", view=None)


class VueConfirmationSignalement(discord.ui.View):
    def __init__(self, report_id):
        super().__init__(timeout=None)
        self.report_id = report_id
        self.confirmer.custom_id = f"signal_confirmer:{report_id}"
        self.rejeter.custom_id = f"signal_rejeter:{report_id}"

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.success)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _autorise_confirmation(interaction):
            await interaction.response.send_message("Tu n'as pas la permission de valider ceci.", ephemeral=True)
            return

        signalement = gestion_signalements.get(self.report_id)
        if not signalement or signalement["traite"]:
            await interaction.response.send_message("Ce signalement a déjà été traité.", ephemeral=True)
            return

        if signalement["type"] == "mauvais_chapitre":
            exo = index_exercices.trouver_par_chemin(signalement["exo_chemin"])
            if exo:
                index_exercices.deplacer_exercice(exo, signalement["nouveau_chapitre"])

        gestion_signalements.marquer_traite(self.report_id)
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        await interaction.response.edit_message(content=f"✅ Confirmé par {interaction.user.mention}.", embed=embed, view=None)

    @discord.ui.button(label="❌ Rejeter", style=discord.ButtonStyle.secondary)
    async def rejeter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _autorise_confirmation(interaction):
            await interaction.response.send_message("Tu n'as pas la permission de rejeter ceci.", ephemeral=True)
            return

        gestion_signalements.marquer_traite(self.report_id)
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        await interaction.response.edit_message(content=f"❌ Rejeté par {interaction.user.mention}.", embed=embed, view=None)


class VueSelectionChapitrePourExo(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        options = [discord.SelectOption(label=ch.replace("_", " "), value=ch) for ch in index_exercices.chapitres()][:25]
        select = discord.ui.Select(placeholder="Choisir un chapitre", options=options)
        select.callback = self._callback
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction):
        chapitre = interaction.data["values"][0]
        exo = index_exercices.au_hasard(chapitre)
        if exo is None:
            await interaction.response.send_message("Aucun exercice dans ce chapitre.", ephemeral=True)
            return
        await creer_salon_session(interaction, exo)


class VueMenuPrincipal(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎲 Exercice au hasard", style=discord.ButtonStyle.primary,
                        custom_id="menu_hasard", row=0)
    async def hasard(self, interaction: discord.Interaction, button: discord.ui.Button):
        exo = index_exercices.au_hasard()
        if exo is None:
            await interaction.response.send_message("Aucun exercice disponible pour l'instant.", ephemeral=True)
            return
        await creer_salon_session(interaction, exo)

    @discord.ui.button(label="📚 Choisir un chapitre", style=discord.ButtonStyle.primary,
                        custom_id="menu_chapitre", row=0)
    async def chapitre(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Choisis un chapitre :", view=VueSelectionChapitrePourExo(), ephemeral=True
        )

    @discord.ui.button(label="📄 Liste des exercices", style=discord.ButtonStyle.secondary,
                        custom_id="menu_liste", row=1)
    async def liste(self, interaction: discord.Interaction, button: discord.ui.Button):
        lignes = [
            f"**{ch.replace('_', ' ')}** — {len(index_exercices.par_chapitre[ch])}"
            for ch in index_exercices.chapitres()
        ]
        embed = discord.Embed(title="📄 Exercices disponibles", description="\n".join(lignes) or "Aucun exercice.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📅 Années disponibles", style=discord.ButtonStyle.secondary,
                        custom_id="menu_annees", row=1)
    async def annees(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="📅 Années disponibles", description=", ".join(index_exercices.annees()) or "Aucune.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🌍 Pays disponibles", style=discord.ButtonStyle.secondary,
                        custom_id="menu_pays", row=1)
    async def pays(self, interaction: discord.Interaction, button: discord.ui.Button):
        regions = [r.replace("_", " ") for r in index_exercices.regions()]
        embed = discord.Embed(title="🌍 Pays / régions disponibles", description=", ".join(regions) or "Aucun.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
# ÉVÉNEMENTS
# ==========================================

async def assurer_message_menu():
    salon = bot.get_channel(config.SALON_INTERFACE_ID)
    if salon is None:
        print("⚠️ Salon d'interface introuvable, vérifie SALON_INTERFACE_ID.")
        return

    message_id = None
    if os.path.exists(config.FICHIER_MENU):
        with open(config.FICHIER_MENU, encoding="utf-8") as f:
            message_id = json.load(f).get("message_id")

    if message_id:
        try:
            await salon.fetch_message(message_id)
            return
        except discord.NotFound:
            pass

    embed = discord.Embed(
        title="📚 Exercices de Bac — Spécialité Maths",
        description="Choisis une option ci-dessous pour t'entraîner.",
        color=discord.Color.blurple(),
    )
    message = await salon.send(embed=embed, view=VueMenuPrincipal())
    os.makedirs(os.path.dirname(config.FICHIER_MENU) or ".", exist_ok=True)
    with open(config.FICHIER_MENU, "w", encoding="utf-8") as f:
        json.dump({"message_id": message.id}, f)


@bot.event
async def on_ready():
    bot.add_dynamic_items(
        BoutonNavigationExercice, BoutonNavigationCorrige,
        BoutonVoirCorrige, BoutonSignaler, BoutonTerminerSession,
    )
    bot.add_view(VueMenuPrincipal())
    for report_id in gestion_signalements.en_attente():
        bot.add_view(VueConfirmationSignalement(report_id))

    await assurer_message_menu()
    print(f"✅ Connecté en tant que {bot.user}")


if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)