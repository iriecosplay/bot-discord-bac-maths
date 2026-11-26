"""Bot Discord unique du serveur Mathematic.

Regroupe les 3 anciens bots :
  • bot-discord-bac-maths  → cogs/exercices.py           (exercices de bac)
  • progressionbot         → cogs/progression/*           (XP, niveaux, vocaux, giveaways, stats…)
  • irie-bot (JS)          → cogs/serveur/* + cogs/moderation/*  (sécurité, panneaux, tickets, avis, modération)

Toutes les commandes passent par le même système (noyau/permissions.py) :
préfixe « + » ou « ! » ET commandes / (slash), /aide liste tout.
"""
import logging
import time

import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient

import config
from noyau import etat, ids
from noyau.etat import err_embed
from noyau.permissions import PermissionRefusee

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bot")

EXTENSIONS = [
    # 📝 Exercices de bac
    "cogs.exercices",
    # 📈 Progression (ex progressionbot)
    "cogs.progression.xp",
    "cogs.progression.niveaux",
    "cogs.progression.profil",
    "cogs.progression.forum",
    "cogs.progression.mensuel",
    "cogs.progression.giveaways",
    "cogs.progression.dashboard",
    "cogs.progression.vocaux",
    # 🏠 Serveur (ex irie-bot + accueil progressionbot)
    "cogs.serveur.securite",
    "cogs.serveur.panneaux",
    "cogs.serveur.avis",
    "cogs.serveur.tickets",
    "cogs.serveur.bienvenue",
    # 🛡️ Modération (ex irie-bot)
    "cogs.moderation.infos",
    "cogs.moderation.sanctions",
    "cogs.moderation.salons",
    "cogs.moderation.roles",
    "cogs.moderation.administration",
    # ❓ Aide
    "cogs.aide",
]

# Commandes utilisables par le bot exempté d'automod (comme dans irie-bot)
COMMANDES_PUBLIQUES = {"invite", "ping", "botinfo", "serverinfo", "membercount", "userinfo", "avatar", "aide"}


class BotMaths(commands.Bot):
    def __init__(self):
        # Seulement les événements utiles (moins de trafic = moins de CPU/RAM sur Railway)
        intents = discord.Intents.all()
        intents.typing = False                 # « X est en train d'écrire »
        intents.dm_typing = False
        intents.guild_scheduled_events = False
        intents.auto_moderation = False
        intents.emojis_and_stickers = False
        super().__init__(command_prefix=["+", "!"], intents=intents, help_command=None,
                         max_messages=300,  # cache de messages réduit (défaut 1000)
                         case_insensitive=True, allowed_mentions=discord.AllowedMentions(everyone=False, roles=True, users=True))
        self.db = None            # base « mathsxp » (XP / progression)
        self._derniere_cmd: dict[int, float] = {}
        self._synchro = False

    async def setup_hook(self):
        etat.bot = self
        prog_client = AsyncIOMotorClient(config.MONGODB_URI)
        self.db = prog_client[config.MONGO_DB_PROGRESSION]
        irie_client = prog_client if config.MONGO_URI_IRIE == config.MONGODB_URI else AsyncIOMotorClient(config.MONGO_URI_IRIE)
        etat.db = irie_client[ids.MONGO_DB_IRIE]
        await etat.charger_depuis_db()
        logger.info("✅ MongoDB connecté")

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Module chargé : {ext}")
            except Exception:
                logger.exception(f"❌ Erreur chargement {ext}")

        self.add_check(self._anti_flood)

    async def on_ready(self):
        logger.info(f"✅ Connecté en tant que {self.user} ({len(self.guilds)} serveur(s))")
        if not self._synchro:
            self._synchro = True
            try:
                # Commandes enregistrées sur le serveur uniquement : visibles tout de suite,
                # et pas de doublons (on vide la liste globale).
                guild = discord.Object(config.GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                logger.info(f"{len(synced)} commandes slash synchronisées")
            except Exception:
                logger.exception("Erreur de synchronisation des commandes slash")

    # ── Messages : l'anti-spam passe AVANT les commandes ──
    async def on_message(self, message: discord.Message):
        if message.author.id == self.user.id:
            return
        if message.guild and message.author.id == ids.AUTOMOD_IGNORED_BOT_ID:
            ctx = await self.get_context(message)
            if ctx.command and ctx.command.qualified_name in COMMANDES_PUBLIQUES:
                await self.invoke(ctx)
            return
        if message.guild:
            securite = self.get_cog("Sécurité")
            if securite and await securite.scan_message(message):
                return
        await self.process_commands(message)

    # ── Anti-flood : 4 s entre deux commandes « + » (sauf owner) ──
    async def _anti_flood(self, ctx: commands.Context):
        if ctx.interaction is not None or etat.is_owner(ctx.author.id) or ctx.command.name == "invite":
            return True
        t = time.monotonic()
        if t - self._derniere_cmd.get(ctx.author.id, 0) < ids.COMMAND_COOLDOWN:
            raise commands.CommandOnCooldown(commands.Cooldown(1, ids.COMMAND_COOLDOWN), ids.COMMAND_COOLDOWN, commands.BucketType.user)
        self._derniere_cmd[ctx.author.id] = t
        return True

    # ── Gestion d'erreurs centrale ──
    async def on_command_error(self, ctx: commands.Context, error):
        if ctx.command and (ctx.command.has_error_handler() or (ctx.cog and ctx.cog.has_error_handler())):
            return
        error = getattr(error, "original", error)
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, PermissionRefusee):
            if str(error) == "Spam de sanctions détecté.":
                return
            texte = error.texte
        elif isinstance(error, commands.CommandOnCooldown):
            return await self._repondre(ctx, err_embed("Doucement ! Attends quelques secondes avant de relancer une commande."), delete_after=4)
        elif isinstance(error, commands.CheckFailure):
            texte = "Tu n'as pas la permission d'utiliser cette commande."
        elif isinstance(error, (commands.MissingRequiredArgument, commands.TooManyArguments)):
            texte = f"Usage : `+{ctx.command.qualified_name} {ctx.command.usage or ctx.command.signature}`"
        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            texte = f"Membre introuvable : `{error.argument}`."
        elif isinstance(error, commands.RoleNotFound):
            texte = f"Rôle introuvable : `{error.argument}`."
        elif isinstance(error, commands.ChannelNotFound):
            texte = f"Salon introuvable : `{error.argument}`."
        elif isinstance(error, (commands.BadArgument, commands.BadUnionArgument, commands.RangeError)):
            texte = f"Argument invalide.\nUsage : `+{ctx.command.qualified_name} {ctx.command.usage or ctx.command.signature}`"
        elif isinstance(error, discord.Forbidden):
            texte = "Je n'ai pas la permission de faire ça (vérifie la position de mon rôle)."
        else:
            logger.error(f"Erreur dans +{ctx.command}", exc_info=error)
            texte = "Une erreur inattendue est survenue."
        await self._repondre(ctx, err_embed(texte))

    async def _repondre(self, ctx, embed, delete_after=None):
        try:
            if ctx.interaction:
                if ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.reply(embed=embed, delete_after=delete_after)
        except discord.HTTPException:
            pass


if __name__ == "__main__":
    BotMaths().run(config.DISCORD_TOKEN, log_handler=None)
