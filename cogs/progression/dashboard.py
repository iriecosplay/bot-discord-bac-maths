import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)

# Salon stats serveur (embed éditable toutes les heures)
CHANNEL_STATS = 1504488999530791033

# Salon activité quotidienne (leaderboard vocal envoyé à minuit UTC)
CHANNEL_DAILY = 1504489016123199613

# Clé DB pour retrouver l'ID du message stats permanent
STATS_MSG_KEY = "dashboard_stats_message_id"

MEDALS = ["🥇", "🥈", "🥉"]
NUMBER_EMOJIS = ["4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

RANK_COLORS = [0xFFD700, 0xC0C0C0, 0xCD7F32]  # or, argent, bronze



def _fmt_hhmm(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h}h{m:02d}" if h else f"{m}min"



class DashboardCog(commands.Cog, name="Statistiques"):
    def __init__(self, bot):
        self.bot = bot
        self._stats_message_id: int | None = None
        # { (guild_id, user_id) -> join_ts (float, timestamp UTC) }
        self._vocal_join: dict[tuple[int, int], float] = {}
        self.stats_loop.start()
        self.daily_loop.start()
        self.vocal_save_loop.start()

    def cog_unload(self):
        self.stats_loop.cancel()
        self.daily_loop.cancel()
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

    # ══════════════════════════════════════════════════════════════════════════
    # EMBED 1 : Stats serveur — édité toutes les heures
    # ══════════════════════════════════════════════════════════════════════════

    @tasks.loop(hours=1.0)
    async def stats_loop(self):
        channel = self.bot.get_channel(CHANNEL_STATS)
        if not channel:
            logger.warning(f"Salon stats {CHANNEL_STATS} introuvable.")
            return

        guild = channel.guild
        embed = self._build_stats_embed(guild)
        msg = await self._get_stats_message(channel)

        if msg:
            try:
                await msg.edit(embed=embed)
                logger.info("Embed stats mis à jour (édition).")
                return
            except discord.NotFound:
                self._stats_message_id = None
            except Exception as e:
                logger.error(f"Erreur édition embed stats : {e}")

        try:
            new_msg = await channel.send(embed=embed)
            self._stats_message_id = new_msg.id
            if self.bot.db is not None:
                await self.bot.db.config.update_one(
                    {"key": STATS_MSG_KEY},
                    {"$set": {"value": str(new_msg.id)}},
                    upsert=True,
                )
            logger.info(f"Embed stats créé (id={new_msg.id}).")
        except Exception as e:
            logger.error(f"Erreur envoi embed stats : {e}")

    def _build_stats_embed(self, guild: discord.Guild) -> discord.Embed:
        total_members = guild.member_count
        online_members = sum(
            1 for m in guild.members
            if m.status != discord.Status.offline and not m.bot
        )
        in_voice = sum(len(vc.members) for vc in guild.voice_channels)
        boosts = guild.premium_subscription_count

        embed = discord.Embed(
            title="Maths Beta 🏆 Statistiques !",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.description = (
            f"*Membres :* **{total_members:,}**\n"
            f"*En ligne :* **{online_members:,}**\n"
            f"*En Vocal :* **{in_voice:,}**\n"
            f"*Boosts :* **{boosts:,}**"
        )
        embed.set_footer(text="Actualisé toutes les heures")
        return embed

    async def _get_stats_message(self, channel: discord.TextChannel) -> discord.Message | None:
        if self._stats_message_id:
            try:
                return await channel.fetch_message(self._stats_message_id)
            except discord.NotFound:
                self._stats_message_id = None

        if self.bot.db is not None:
            doc = await self.bot.db.config.find_one({"key": STATS_MSG_KEY})
            if doc:
                try:
                    msg_id = int(doc["value"])
                    msg = await channel.fetch_message(msg_id)
                    if msg.author.id != self.bot.user.id:
                        # posté par l'ancien progressionbot : non modifiable → on le remplace
                        await msg.delete()
                        return None
                    self._stats_message_id = msg_id
                    return msg
                except Exception:
                    pass

        return None

    @stats_loop.before_loop
    async def before_stats(self):
        await self.bot.wait_until_ready()

    # ══════════════════════════════════════════════════════════════════════════
    # EMBED 2 : Leaderboard vocal — envoyé chaque minuit UTC
    # ══════════════════════════════════════════════════════════════════════════

    @tasks.loop(hours=24.0)
    async def daily_loop(self):
        channel = self.bot.get_channel(CHANNEL_DAILY)
        if not channel:
            logger.warning(f"Salon daily {CHANNEL_DAILY} introuvable.")
            return

        db = self.bot.db
        guild = channel.guild

        # Flush les sessions vocales en cours avant de construire le leaderboard
        if db is not None:
            now_ts = datetime.now(timezone.utc).timestamp()
            # On prend la date d'hier car on est à minuit, donc le jour vient de changer
            yesterday = (datetime.now(timezone.utc) - timedelta(seconds=1)).strftime("%Y-%m-%d")
            for (gid, uid), join_ts in list(self._vocal_join.items()):
                if gid != guild.id:
                    continue
                elapsed_minutes = int((now_ts - join_ts) / 60)
                if elapsed_minutes > 0:
                    self._vocal_join[(gid, uid)] = now_ts
                    await self._add_vocal_minutes(db, gid, uid, elapsed_minutes, yesterday)

        embed = await self._build_leaderboard_embed(guild, db)

        try:
            await channel.send(embed=embed)
            logger.info("Leaderboard vocal quotidien envoyé.")
        except Exception as e:
            logger.error(f"Erreur envoi leaderboard vocal : {e}")

        # Reset des compteurs journaliers messages
        if db is not None:
            await db.daily_activity.delete_many({"guild_id": str(guild.id)})
            logger.info("Compteurs journaliers messages remis à zéro.")

        # Supprime les données du jour terminé (hier) — le nouveau jour repart de zéro
        if db is not None:
            yesterday_str = (datetime.now(timezone.utc) - timedelta(seconds=1)).strftime("%Y-%m-%d")
            await db.daily_vocal_leaderboard.delete_many(
                {"guild_id": str(guild.id), "date": yesterday_str}
            )
            logger.info(f"Leaderboard vocal de {yesterday_str} remis à zéro.")

        # Vide le suivi en mémoire pour ce guild
        self._vocal_join = {
            k: v for k, v in self._vocal_join.items() if k[0] != guild.id
        }

    async def _build_leaderboard_embed(self, guild: discord.Guild, db) -> discord.Embed:
        # On prend hier car on est appelé à minuit (le jour vient de se terminer)
        yesterday = (datetime.now(timezone.utc) - timedelta(seconds=1))
        date_key = yesterday.strftime("%Y-%m-%d")
        date_display = yesterday.strftime("%d/%m/%Y")
        day_name = yesterday.strftime("%A %d %B %Y")  # ex: "Vendredi 23 Mai 2025"

        embed = discord.Embed(
            color=0x2B2D31,
            timestamp=datetime.now(timezone.utc),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.set_author(
            name="📊 Récap vocal du jour",
            icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
        )

        if db is None:
            embed.description = "*Base de données indisponible.*"
            return embed

        cursor = db.daily_vocal_leaderboard.find(
            {"guild_id": str(guild.id), "date": date_key}
        ).sort("minutes", -1).limit(10)
        docs = await cursor.to_list(length=10)

        if not docs:
            embed.title = f"🎙️ Leaderboard vocal — {date_display}"
            embed.description = "*Personne n'a passé de temps en vocal aujourd'hui.*"
            embed.set_footer(text="Remis à zéro chaque jour à minuit UTC")
            return embed

        max_minutes = docs[0].get("minutes", 1) or 1
        total_guild_minutes = sum(d.get("minutes", 0) for d in docs)

        # ── Header ────────────────────────────────────────────────────────────
        embed.title = f"🏆  Leaderboard Vocal  •  {date_display}"
        embed.description = (
            f"```\n"
            f"  {guild.name}\n"
            f"  {day_name}\n"
            f"  {len(docs)} participant{'s' if len(docs) > 1 else ''}  •  "
            f"{_fmt_hhmm(total_guild_minutes)} au total\n"
            f"```"
        )
 
        # ── Podium (top 3) ────────────────────────────────────────────────────
        podium_lines = []
        podium_headers = [
            ("🥇", "1ER", 0xFFD700),
            ("🥈", "2ÈME", 0xC0C0C0),
            ("🥉", "3ÈME", 0xCD7F32),
        ]

        for i, (medal, rank_label, _) in enumerate(podium_headers):
            if i >= len(docs):
                break
            doc = docs[i]
            member = guild.get_member(int(doc["user_id"]))
            name = member.display_name if member else f"<@{doc['user_id']}>"
            minutes = doc.get("minutes", 0)
            time_str = _fmt_hhmm(minutes)
            pct = int((minutes / max_minutes) * 100)
            podium_lines.append(
                f"{medal} **{name}**\n"
                f"┗ **{time_str}** — {pct}% du leader"
            )

        embed.add_field(
            name="┌─ Podium ──────────────────────",
            value="\n\n".join(podium_lines) if podium_lines else "*—*",
            inline=False,
        )

        # ── Reste du classement (4→10) ────────────────────────────────────────
        if len(docs) > 3:
            rest_lines = []
            for i in range(3, len(docs)):
                doc = docs[i]
                member = guild.get_member(int(doc["user_id"]))
                name = member.display_name if member else f"<@{doc['user_id']}>"
                minutes = doc.get("minutes", 0)
                time_str = _fmt_hhmm(minutes)
                emoji = NUMBER_EMOJIS[i - 3] if (i - 3) < len(NUMBER_EMOJIS) else f"**{i + 1}.**"
                rest_lines.append(f"{emoji} **{name}** — {time_str}")

            embed.add_field(
                name="└─ Suite du classement ─────────",
                value="\n".join(rest_lines),
                inline=False,
            )

        embed.set_footer(text=f"Remis à zéro chaque jour à minuit UTC  •  {guild.name}")
        return embed

    @daily_loop.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()
        # Attend le prochain minuit UTC
        now = datetime.now(timezone.utc)
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        wait_seconds = (next_midnight - now).total_seconds()
        logger.info(f"Daily leaderboard loop démarrera dans {wait_seconds:.0f}s (prochain minuit UTC).")
        await asyncio.sleep(wait_seconds)


async def setup(bot):
    await bot.add_cog(DashboardCog(bot))
