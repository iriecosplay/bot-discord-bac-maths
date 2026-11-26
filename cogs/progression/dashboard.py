import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

# Les comptes rendus automatiques (stats serveur toutes les heures, classement
# vocal quotidien) ont été retirés : il reste le suivi du temps vocal et /time.




def _fmt_hhmm(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h}h{m:02d}" if h else f"{m}min"



class DashboardCog(commands.Cog, name="Statistiques"):
    def __init__(self, bot):
        self.bot = bot
        # { (guild_id, user_id) -> join_ts (float, timestamp UTC) }
        self._vocal_join: dict[tuple[int, int], float] = {}
        self.vocal_save_loop.start()

    def cog_unload(self):
        self.vocal_save_loop.cancel()

    # ══════════════════════════════════════════════════════════════════════════
    # SUIVI VOCAL JOURNALIER (minuit → minuit UTC)
    # ══════════════════════════════════════════════════════════════════════════

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        db = self.bot.db
        if db is None:
            return

        key = (member.guild.id, member.id)
        now_ts = datetime.now(timezone.utc).timestamp()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if before.channel is None and after.channel is not None:
            self._vocal_join[key] = now_ts

        elif before.channel is not None and after.channel is None:
            join_ts = self._vocal_join.pop(key, None)
            if join_ts is not None:
                elapsed_minutes = int((now_ts - join_ts) / 60)
                if elapsed_minutes > 0:
                    await self._add_vocal_minutes(
                        db, member.guild.id, member.id, elapsed_minutes, today
                    )

    async def _add_vocal_minutes(
        self, db, guild_id: int, user_id: int, minutes: int, date: str
    ):
        await db.daily_vocal_leaderboard.update_one(
            {"guild_id": str(guild_id), "user_id": str(user_id), "date": date},
            {"$inc": {"minutes": minutes}},
            upsert=True,
        )

    @tasks.loop(minutes=5)
    async def vocal_save_loop(self):
        db = self.bot.db
        if db is None:
            return

        now_ts = datetime.now(timezone.utc).timestamp()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for (guild_id, user_id), join_ts in list(self._vocal_join.items()):
            elapsed_minutes = int((now_ts - join_ts) / 60)
            if elapsed_minutes < 1:
                continue
            self._vocal_join[(guild_id, user_id)] = now_ts
            await self._add_vocal_minutes(db, guild_id, user_id, elapsed_minutes, today)

    @vocal_save_loop.before_loop
    async def before_vocal_save(self):
        await self.bot.wait_until_ready()

    # ─── /time ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="time",
        description="Voir le temps passé en vocal aujourd'hui et hier.",
    )
    @app_commands.describe(membre="Le membre dont voir le temps (toi par défaut)")
    async def time_cmd(
        self, interaction: discord.Interaction, membre: discord.Member = None
    ):
        target = membre or interaction.user
        db = self.bot.db

        if db is None:
            await interaction.response.send_message(
                "❌ Base de données indisponible.", ephemeral=True
            )
            return

        now_utc = datetime.now(timezone.utc)
        today = now_utc.strftime("%Y-%m-%d")
        yesterday = (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")
        guild_id_str = str(interaction.guild.id)
        user_id_str = str(target.id)

        # ── Données aujourd'hui ──────────────────────────────────────────────
        doc_today = await db.daily_vocal_leaderboard.find_one(
            {"guild_id": guild_id_str, "user_id": user_id_str, "date": today}
        )
        saved_minutes = doc_today.get("minutes", 0) if doc_today else 0

        # Temps live (si actuellement en vocal)
        key = (interaction.guild.id, target.id)
        live_minutes = 0
        join_ts = self._vocal_join.get(key)
        if join_ts is not None:
            live_minutes = int((now_utc.timestamp() - join_ts) / 60)

        total_today = saved_minutes + live_minutes
        is_live = join_ts is not None

        # ── Données hier ─────────────────────────────────────────────────────
        doc_yesterday = await db.daily_vocal_leaderboard.find_one(
            {"guild_id": guild_id_str, "user_id": user_id_str, "date": yesterday}
        )
        total_yesterday = doc_yesterday.get("minutes", 0) if doc_yesterday else 0

        # ── Rang du jour ─────────────────────────────────────────────────────
        count_above = await db.daily_vocal_leaderboard.count_documents({
            "guild_id": guild_id_str,
            "date": today,
            "minutes": {"$gt": total_today},
        })
        rank = count_above + 1

        # ── Formatage ────────────────────────────────────────────────────────
        def fmt(minutes: int) -> str:
            h = minutes // 60
            m = minutes % 60
            if h and m:
                return f"{h}h {m:02d}min"
            elif h:
                return f"{h}h"
            else:
                return f"{m}min"

        time_today_str = fmt(total_today)
        time_yesterday_str = fmt(total_yesterday)

        # Comparaison hier/aujourd'hui
        diff = total_today - total_yesterday
        if diff > 0:
            trend = f"▲ {fmt(diff)} de plus qu'hier"
            trend_emoji = "📈"
        elif diff < 0:
            trend = f"▼ {fmt(-diff)} de moins qu'hier"
            trend_emoji = "📉"
        else:
            trend = "Même durée qu'hier"
            trend_emoji = "➡️"

        # Couleur selon le temps du jour
        if total_today >= 120:
            color = 0x57F287   # vert
        elif total_today >= 30:
            color = 0xF0B132   # or
        else:
            color = 0x5865F2   # bleu

        # ── Embed ────────────────────────────────────────────────────────────
        embed = discord.Embed(
            title=f"{target.display_name} — Temps vocal",
            color=color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        live_badge = "  🔴 **EN VOCAL**" if is_live else ""
        embed.add_field(
            name=f"🎙️ Aujourd'hui{live_badge}",
            value=f"**{time_today_str}**\n🏅 Rang : **#{rank}**",
            inline=True,
        )
        embed.add_field(
            name="📅 Hier",
            value=f"**{time_yesterday_str}**",
            inline=True,
        )
        embed.add_field(
            name=f"{trend_emoji} Évolution",
            value=trend,
            inline=False,
        )

        midnight_next = (now_utc + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seconds_left = int((midnight_next - now_utc).total_seconds())
        hours_left = seconds_left // 3600
        minutes_left = (seconds_left % 3600) // 60

        embed.set_footer(
            text=f"Remise à zéro dans {hours_left}h{minutes_left:02d}  •  {today}"
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(DashboardCog(bot))
