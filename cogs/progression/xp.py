import discord
from discord.ext import commands, tasks
import logging
from datetime import datetime, timezone
from noyau.xp import add_xp, get_or_create_member, now_utc

logger = logging.getLogger(__name__)

# --- Configuration ---
AIDE_VOICE_CATEGORY_ID = 1501911926098235422
MESSAGE_XP = 5
MESSAGE_COOLDOWN = 60       # secondes
VOCAL_XP_NORMAL = 10
VOCAL_XP_AIDE = 25
VOCAL_CHECK_INTERVAL = 5    # minutes
DAILY_XP = 30

# Multiplicateurs de malus
MALUS_MUTE_MIC = 2      # micro coupé seulement : 2x moins
MALUS_MUTE_DEAF = 3.0   # casque coupé seulement : 3x moins
MALUS_AFK = 10.0        # complètement AFK (sourd + muet) : 10x moins

class XPCog(commands.Cog):
    """Gère l'XP messages, daily et vocal avec malus pour le mute."""

    def __init__(self, bot):
        self.bot = bot
        self.voice_xp_task.start()

    def cog_unload(self):
        self.voice_xp_task.cancel()

    # ─── Listener messages (XP + daily) ─────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        db = self.bot.db
        if db is None:
            return

        doc = await get_or_create_member(db, message.author.id, message.guild.id)
        updates = {}
        xp_to_add = 0

        # Daily bonus
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if doc.get("last_daily") != today:
            xp_to_add += DAILY_XP
            updates["last_daily"] = today
            logger.info(f"[DAILY] +{DAILY_XP} XP pour {message.author}")

        # XP message
        if len(message.content) >= 5:
            last = doc.get("last_message_xp")
            can_earn = True
            if last:
                last_dt = datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed < MESSAGE_COOLDOWN:
                    can_earn = False

            if can_earn:
                multiplier = await self._get_channel_multiplier(db, message.guild.id, message.channel.id)
                gain = int(MESSAGE_XP * multiplier)
                xp_to_add += gain
                updates["last_message_xp"] = now_utc()

        if updates:
            await db.members.update_one(
                {"user_id": str(message.author.id), "guild_id": str(message.guild.id)},
                {"$set": updates},
            )

        await db.members.update_one(
            {"user_id": str(message.author.id), "guild_id": str(message.guild.id)},
            {"$inc": {"total_messages": 1}},
        )

        # Compteurs journaliers pour le dashboard
        gid = str(message.guild.id)
        uid = str(message.author.id)
        await db.daily_activity.update_one(
            {"guild_id": gid, "type": "messages"},
            {"$inc": {"count": 1}},
            upsert=True,
        )
        await db.daily_activity.update_one(
            {"guild_id": gid, "type": "user_messages", "user_id": uid},
            {"$inc": {"count": 1}},
            upsert=True,
        )

        if xp_to_add > 0:
            new_xp, old_level, new_level = await add_xp(
                db, message.author.id, message.guild.id, xp_to_add, "message"
            )
            if new_level > old_level:
                await self._handle_level_up(message.author, old_level, new_level, new_xp)

    # ─── Task vocale (toutes les 5 min) ─────────────────────────────────────

    @tasks.loop(minutes=VOCAL_CHECK_INTERVAL)
    async def voice_xp_task(self):
        db = self.bot.db
        if db is None:
            return

        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                real_members = [m for m in vc.members if not m.bot]
                if not real_members:
                    continue

                is_aide = (vc.category_id == AIDE_VOICE_CATEGORY_ID)
                base_xp = VOCAL_XP_AIDE if is_aide else VOCAL_XP_NORMAL

                for member in real_members:
                    if not member.voice:
                        continue

                    try:
                        multiplier = 1.0
                        log_suffix = ""

                        # Calcul du malus selon l'état vocal
                        is_deaf = member.voice.self_deaf or member.voice.deaf
                        is_mute = member.voice.self_mute or member.voice.mute

                        if is_deaf and is_mute:
                            multiplier = 1 / MALUS_AFK
                            log_suffix = " (AFK)"
                        elif is_deaf:
                            multiplier = 1 / MALUS_MUTE_DEAF
                            log_suffix = " (mute casque)"
                        elif is_mute:
                            multiplier = 1 / MALUS_MUTE_MIC
                            log_suffix = " (mute micro)"

                        xp_gain = int(base_xp * multiplier)
                        
                        if xp_gain < 1: 
                            xp_gain = 1

                        new_xp, old_level, new_level = await add_xp(
                            db, member.id, guild.id, xp_gain, "vocal"
                        )
                        
                        await db.members.update_one(
                            {"user_id": str(member.id), "guild_id": str(guild.id)},
                            {"$inc": {"total_vocal_minutes": VOCAL_CHECK_INTERVAL}},
                        )

                        if multiplier == 1.0:
                            await db.daily_activity.update_one(
                                {"guild_id": str(guild.id), "type": "user_vocal_unmuted", "user_id": str(member.id)},
                                {"$inc": {"minutes": VOCAL_CHECK_INTERVAL}},
                                upsert=True,
                            )
                        
                        logger.info(f"[VOCAL] +{xp_gain} XP pour {member} dans #{vc.name}{log_suffix}")
                        
                        if new_level > old_level:
                            await self._handle_level_up(member, old_level, new_level, new_xp)
                            
                    except Exception as e:
                        logger.error(f"[VOCAL] Erreur pour {member} : {e}")

    @voice_xp_task.before_loop
    async def before_voice_xp(self):
        await self.bot.wait_until_ready()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    async def _handle_level_up(self, member, old_level, new_level, new_xp):
        roles_cog = self.bot.get_cog("RolesCog")
        if roles_cog:
            await roles_cog.update_member_roles(member, new_level)

    async def _get_channel_multiplier(self, db, guild_id: int, channel_id: int) -> float:
        # BUG CORRIGÉ : bare except remplacé par Exception explicite pour ne pas
        # avaler des erreurs critiques (ex: erreur de connexion DB).
        try:
            doc = await db.channel_multipliers.find_one(
                {"guild_id": str(guild_id), "channel_id": str(channel_id)}
            )
            return float(doc.get("multiplier", 1.0)) if doc else 1.0
        except Exception as e:
            logger.warning(f"[MULTIPLIER] Erreur lecture multiplicateur canal {channel_id} : {e}")
            return 1.0

async def setup(bot):
    await bot.add_cog(XPCog(bot))
