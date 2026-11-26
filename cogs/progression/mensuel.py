import discord
from discord.ext import commands, tasks
import logging
from datetime import datetime, timezone
logger = logging.getLogger(__name__)
# BUG CORRIGÉ : on utilise le channel level-up déjà défini dans roles.py
# plutôt que de chercher/créer un channel "annonces-niveaux" aléatoire.
LEVELUP_CHANNEL_ID = 1496296729471877183
class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monthly_task.start()
    def cog_unload(self):
        self.monthly_task.cancel()
    @tasks.loop(hours=1)
    async def monthly_task(self):
        """Runs every hour but only acts on the 1st of the month at midnight."""
        now = datetime.now(timezone.utc)
        if now.day != 1 or now.hour != 0:
            return
        db = self.bot.db
        if db is None:
            return
        current_month = now.strftime("%Y-%m")
        for guild in self.bot.guilds:
            await self._announce_aidant_du_mois(guild, db, current_month)
        # Reset monthly counters for the new month
        await db.members.update_many(
            {},
            {"$set": {"monthly_solutions": 0, "monthly_reset": current_month}},
        )
        logger.info(f"Reset mensuel effectué pour {current_month}")
    async def _announce_aidant_du_mois(self, guild: discord.Guild, db, current_month: str):
        """Announce the top helper of the month."""
        now = datetime.now(timezone.utc)
        if now.month == 1:
            prev_year = now.year - 1
            prev_month = 12
        else:
            prev_year = now.year
            prev_month = now.month - 1
        prev_month_str = f"{prev_year}-{prev_month:02d}"
        top = await db.members.find_one(
            {"guild_id": str(guild.id), "monthly_reset": prev_month_str},
            sort=[("monthly_solutions", -1)],
        )
        if not top or top.get("monthly_solutions", 0) == 0:
            return
        member = guild.get_member(int(top["user_id"]))
        if member is None:
            return
        # BUG CORRIGÉ : on utilise LEVELUP_CHANNEL_ID (channel existant et connu)
        # au lieu de chercher/créer "annonces-niveaux" qui pouvait créer un channel
        # indésirable ou annoncer dans le mauvais endroit.
        channel = guild.get_channel(LEVELUP_CHANNEL_ID)
        if channel is None:
            logger.warning(f"Channel level-up {LEVELUP_CHANNEL_ID} introuvable dans {guild.name}")
            return
        embed = discord.Embed(
            title="🏅 Aidant du mois !",
            description=(
                f"Félicitations à {member.mention} pour avoir été **l'aidant du mois de {prev_month_str}** "
                f"avec **{top['monthly_solutions']} solution(s)** apportée(s) ! 🎉"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
        logger.info(f"Aidant du mois annoncé: {member} dans {guild.name}")
    @monthly_task.before_loop
    async def before_monthly(self):
        await self.bot.wait_until_ready()
async def setup(bot):
    await bot.add_cog(TasksCog(bot))
