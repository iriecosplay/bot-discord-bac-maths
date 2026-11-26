"""👋 Accueil : message de bienvenue, ping des nouveaux, panneaux guide / défis.

Fusionne :
  • progressionbot : message de bienvenue avec image, /autoping, /send_panel,
    /sendguide, /senddefi et les boutons d'accès aux challenges ;
  • irie-bot : +setwelcome (ping 5 s des nouveaux membres).
/autoping et +setwelcome faisaient la même chose : c'est maintenant un seul
réglage, enregistré en base (il survit aux redémarrages).
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from noyau import etat
from noyau.etat import err_embed, get_chan, ok_embed, supprimer_anciens_panneaux
from noyau.permissions import administrateur

logger = logging.getLogger(__name__)

WELCOME_EMBED_CHANNEL_ID = 1519104109872152667
WELCOME_IMAGE_URL = "https://i.pinimg.com/1200x/2f/ea/eb/2feaeb8d55f714f24690aea1371cf605.jpg"
PANEL_CHANNEL_ID = 1487184792347738152

ROLES_CHALLENGES = {
    "role_4e_3e": 1532351809891598446,
    "role_3e_2nde": 1508073776909254797,
    "role_2nde_1ere": 1506340921698942986,
    "role_1ere_term": 1508150559969120356,
    "role_term_sup": 1507869353205567671,
    "role_helper": 1527680545298059498,
}

_GUIDE = (
    "Bienvenue ! Voici quelques informations utiles pour profiter pleinement du serveur.\n\n"
    "📚 **Besoin d'aide ou envie d'aider d'autres membres ?**\n"
    "Consultez les salons <#1506342382201733180> et <#1506342418830594292>.\n\n"
    "👥 **Vous recherchez une équipe de travail ?**\n"
    "Regardez les annonces dans <#1503423558825672824> ou publiez la vôtre afin de trouver d'autres membres avec qui travailler.\n\n"
    "💡 **Vous avez une méthode de travail efficace ?**\n"
    "Partagez-la dans <#1496573007055945839>. Une bonne organisation ou une technique qui fonctionne pour vous pourra être utile à d'autres.\n\n"
    "📂 **Vous cherchez des ressources (PDF, fiches, liens utiles...) ?**\n"
    "Les ressources sont disponibles dans les différentes catégories du serveur. Si vous ne trouvez pas les salons correspondants, c'est probablement que vous n'avez pas encore sélectionné les catégories qui vous intéressent. Rendez-vous dans <#1487181193387577364>, puis dans <#1499497496727126117> afin de configurer les salons que vous souhaitez afficher.\n\n"
    "🎤 **Salons vocaux**\n"
    "En bas du serveur, vous trouverez les salons vocaux ainsi que la possibilité de créer vos propres vocaux temporaires via <#1518232838011355249>. Si vous souhaitez réviser un chapitre ou un niveau précis, n'hésitez pas à donner un titre explicite (par exemple « Second degré - Première ») afin que d'autres membres puissent facilement vous rejoindre.\n\n"
    "🏅 **Rôles d'activité**\n"
    "Les rôles visibles à droite du serveur (Apprenti, Stratège, etc.) sont attribués automatiquement en fonction de votre activité.\n\n"
)
_CHALLENGES = (
    "🚀 **Challenges quotidiens (à venir)**\n"
    "Un système de challenges quotidiens sera bientôt disponible afin de vous permettre de réviser progressivement avant la rentrée. Vous pourrez choisir les transitions scolaires qui vous intéressent grâce aux boutons situés sous ce message.\n\n"
)
_FIN = (
    "📝 **Exercices de bac**\n"
    "Le bot propose des exercices de bac corrigés : rendez-vous dans <#1512035664961736724>.\n\n"
    "💬 **Une dernière information :** la création des exercices et des challenges est actuellement assurée par une seule personne. Merci donc d'être compréhensifs si certaines fonctionnalités ou certains contenus mettent un peu de temps à arriver. Les retours et suggestions sont toujours les bienvenus. D'ailleurs, si le serveur vous plaît, n'hésitez pas à y inviter vos amis pour réviser ensemble ! Et si jamais vous avez un boost Discord non utilisé qui traîne, sachez qu'il sera accueilli avec une immense gratitude pour nous donner un petit coup de pouce. Mais le plus important reste bien sûr votre motivation et votre entraide ! ✨\n\n"
    "❓ Tape `/aide` pour voir toutes les commandes du bot."
)


def embed_guide(avec_challenges: bool):
    return discord.Embed(title="📢 Informations importantes sur le serveur", color=0x3498DB,
                         description=_GUIDE + (_CHALLENGES if avec_challenges else "") + _FIN)


def embed_defis():
    return discord.Embed(title="🚀 Challenges quotidiens", color=0x2ECC71,
                         description="Un système de challenges quotidiens est disponible afin de vous permettre de réviser progressivement. "
                                     "Vous pouvez choisir les transitions scolaires qui vous intéressent grâce aux boutons situés sous ce message !")


class InfoRoleView(discord.ui.View):
    """Boutons d'accès aux challenges (vue persistante)."""

    def __init__(self):
        super().__init__(timeout=None)
        boutons = [
            ("Accès challenge transition 4e vers 3e", "role_4e_3e", discord.ButtonStyle.primary, 0),
            ("Accès challenge transition 3e vers Seconde", "role_3e_2nde", discord.ButtonStyle.primary, 1),
            ("Accès challenge transition Seconde vers Première", "role_2nde_1ere", discord.ButtonStyle.primary, 1),
            ("Accès challenge transition Première vers Terminale", "role_1ere_term", discord.ButtonStyle.primary, 2),
            ("Accès challenge Terminale vers Supérieur", "role_term_sup", discord.ButtonStyle.primary, 2),
            ("Je veux aider", "role_helper", discord.ButtonStyle.success, 3),
        ]
        for label, cid, style, row in boutons:
            b = discord.ui.Button(label=label, custom_id=cid, style=style, row=row)
            b.callback = self._toggle
            self.add_item(b)

    async def _toggle(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(ROLES_CHALLENGES[interaction.data["custom_id"]])
        if role is None:
            return await interaction.response.send_message("❌ Rôle introuvable. Veuillez contacter un administrateur.", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"➖ Le rôle **{role.name}** vous a été retiré.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"➕ Le rôle **{role.name}** vous a été ajouté !", ephemeral=True)


class Bienvenue(commands.Cog, name="Accueil"):
    """👋 Bienvenue des nouveaux membres et panneaux d'information."""

    def __init__(self, bot):
        self.bot = bot
        self._ping_cache: dict[int, int | None] = {}

    async def cog_load(self):
        self.bot.add_view(InfoRoleView())

    async def _salon_ping(self, guild_id):
        if guild_id not in self._ping_cache:
            doc = await etat.db.welcomeconfigs.find_one({"guildId": str(guild_id)})
            self._ping_cache[guild_id] = int(doc["channelId"]) if doc and doc.get("channelId") else None
        return self._ping_cache[guild_id]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        ch = self.bot.get_channel(WELCOME_EMBED_CHANNEL_ID)
        if ch:
            e = discord.Embed(description=f"Bienvenue **{member.name}** !", color=discord.Color.blurple())
            e.set_image(url=WELCOME_IMAGE_URL)
            try:
                await ch.send(embed=e)
            except discord.HTTPException:
                pass
        cid = await self._salon_ping(member.guild.id)
        ping = member.guild.get_channel(cid) if cid else None
        if ping:
            try:
                await ping.send(member.mention, delete_after=5)
            except discord.HTTPException as e:
                logger.error(f"[PING BIENVENUE] {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        """Remplace le panneau d'infos de l'ancien progressionbot (boutons morts)."""
        if getattr(self, "_pret", False):
            return
        self._pret = True
        ch = await get_chan(PANEL_CHANNEL_ID)
        if ch and await supprimer_anciens_panneaux(ch):
            await ch.send(embed=embed_guide(True), view=InfoRoleView())

    @commands.hybrid_command(name="autoping", aliases=["setwelcome"],
                             description="Activer/désactiver le ping (5 s) des nouveaux membres dans un salon.", usage="[#salon]")
    @app_commands.describe(salon="Salon où pinger les nouveaux (vide = salon actuel)")
    @administrateur()
    async def autoping(self, ctx, salon: discord.TextChannel | None = None):
        salon = salon or ctx.channel
        actuel = await self._salon_ping(ctx.guild.id)
        if actuel == salon.id:
            await etat.db.welcomeconfigs.delete_one({"guildId": str(ctx.guild.id)})
            self._ping_cache[ctx.guild.id] = None
            return await ctx.reply(embed=ok_embed(f"🔕 Ping des nouveaux membres **désactivé** dans {salon.mention}."), ephemeral=True)
        await etat.db.welcomeconfigs.update_one({"guildId": str(ctx.guild.id)}, {"$set": {"channelId": str(salon.id)}}, upsert=True)
        self._ping_cache[ctx.guild.id] = salon.id
        await ctx.reply(embed=ok_embed(f"🔔 Ping des nouveaux membres **activé** dans {salon.mention} (supprimé après 5 secondes)."), ephemeral=True)

    async def _publier(self, ctx, salon, embed, view=None):
        try:
            await salon.send(embed=embed, view=view or discord.utils.MISSING)
        except discord.HTTPException as e:
            return await ctx.reply(embed=err_embed(f"Une erreur est survenue lors de l'envoi : {e}"), ephemeral=True)
        await ctx.reply(embed=ok_embed(f"Envoyé dans {salon.mention} !"), ephemeral=True)

    @commands.hybrid_command(name="send_panel", description="Publier le panneau d'informations + boutons des challenges.")
    @administrateur()
    async def send_panel(self, ctx):
        salon = await get_chan(PANEL_CHANNEL_ID)
        if salon is None:
            return await ctx.reply(embed=err_embed(f"Impossible de trouver le salon `{PANEL_CHANNEL_ID}`."), ephemeral=True)
        await self._publier(ctx, salon, embed_guide(True), InfoRoleView())

    @commands.hybrid_command(name="sendguide", description="Publier le guide du serveur (sans les boutons).", usage="[#salon]")
    @administrateur()
    async def sendguide(self, ctx, salon: discord.TextChannel | None = None):
        await self._publier(ctx, salon or ctx.channel, embed_guide(False))

    @commands.hybrid_command(name="senddefi", description="Publier la rubrique des défis avec les boutons d'accès.", usage="[#salon]")
    @administrateur()
    async def senddefi(self, ctx, salon: discord.TextChannel | None = None):
        await self._publier(ctx, salon or ctx.channel, embed_defis(), InfoRoleView())


async def setup(bot):
    await bot.add_cog(Bienvenue(bot))
