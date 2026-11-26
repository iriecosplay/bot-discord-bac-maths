import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime, timezone
from noyau.xp import add_xp, get_or_create_member, now_utc

logger = logging.getLogger(__name__)

# ─── Forums d'aide suivis ─────────────────────────────────────────────────────
FORUM_CHANNEL_IDS: set[int] = {
    1503131672995172403,
    1503423640270667938,
    1503423558825672824,
    1503423694033125539,
    1503423824996208720,
    1495847597775126680,
}

AVIS_CHANNEL_ID       = 1496149092919673023
RESOLU_XP_HELPER      = 80
RESOLU_XP_AUTHOR      = 20
INACTIVITY_MINUTES    = 2880   # 48h avant question "résolu ?"

# thread_id -> datetime (dernier message) — en mémoire, réinitialisé au redémarrage
_last_message: dict[int, datetime] = {}


# ─── Helpers DB ───────────────────────────────────────────────────────────────

async def _is_notified(db, thread_id: int) -> bool:
    doc = await db.forum_inactivity.find_one({"thread_id": str(thread_id)})
    return doc is not None

async def _set_notified(db, thread_id: int):
    await db.forum_inactivity.update_one(
        {"thread_id": str(thread_id)},
        {"$set": {"thread_id": str(thread_id), "notified_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

async def _clear_notified(db, thread_id: int):
    await db.forum_inactivity.delete_one({"thread_id": str(thread_id)})


# ─── Vue : question "Résolu ?" après inactivité ───────────────────────────────

class ResoluView(discord.ui.View):
    def __init__(self, thread: discord.Thread, author: discord.Member):
        super().__init__(timeout=None)
        self.thread = thread
        self.author = author

    async def _find_most_active_helper(self) -> discord.Member | None:
        message_counts: dict[int, int] = {}
        async for message in self.thread.history(limit=200, oldest_first=False):
            if message.author.bot:
                continue
            if message.author.id == self.author.id:
                continue
            message_counts[message.author.id] = message_counts.get(message.author.id, 0) + 1

        if not message_counts:
            return None

        top_user_id = max(message_counts, key=lambda uid: message_counts[uid])
        member = self.thread.guild.get_member(top_user_id)
        if member is None:
            try:
                member = await self.thread.guild.fetch_member(top_user_id)
            except Exception:
                return None
        return member

    @discord.ui.button(label="✅ Oui, c'est résolu !", style=discord.ButtonStyle.success, custom_id="resolu_oui")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Seul l'auteur du post peut répondre.", ephemeral=True)
            return

        await interaction.response.defer()

        aidant = await self._find_most_active_helper()
        db = interaction.client.db

        if aidant and db is not None:
            new_xp_h, old_level_h, new_level_h = await add_xp(
                db, aidant.id, interaction.guild.id, RESOLU_XP_HELPER, "misc"
            )
            await db.members.update_one(
                {"user_id": str(aidant.id), "guild_id": str(interaction.guild.id)},
                {"$inc": {"solutions_données": 1, "monthly_solutions": 1}},
            )
            new_xp_a, old_level_a, new_level_a = await add_xp(
                db, interaction.user.id, interaction.guild.id, RESOLU_XP_AUTHOR, "misc"
            )
            await db.members.update_one(
                {"user_id": str(interaction.user.id), "guild_id": str(interaction.guild.id)},
                {"$inc": {"solutions_reçues": 1}},
            )

            roles_cog = interaction.client.get_cog("RolesCog")
            if roles_cog:
                if new_level_h > old_level_h:
                    await roles_cog.update_member_roles(aidant, new_level_h)
                if new_level_a > old_level_a:
                    await roles_cog.update_member_roles(interaction.user, new_level_a)

        await _mark_resolved(self.thread, interaction.guild)

        avis_channel = interaction.guild.get_channel(AVIS_CHANNEL_ID)

        if aidant:
            embed = discord.Embed(title="✅ Post résolu !", color=discord.Color.green())
            embed.add_field(name=f"🎁 {aidant.display_name}", value=f"+{RESOLU_XP_HELPER} XP", inline=True)
            embed.add_field(name=f"📝 {interaction.user.display_name}", value=f"+{RESOLU_XP_AUTHOR} XP", inline=True)
            if avis_channel:
                embed.set_footer(text=f"N'oublie pas de laisser un avis dans #{avis_channel.name} 😊")
            await interaction.followup.send(embed=embed)
        else:
            msg = "✅ Post marqué comme résolu !"
            if avis_channel:
                msg += f"\nSi quelqu'un t'a aidé, n'hésite pas à lui laisser un avis dans {avis_channel.mention} 😊"
            await interaction.followup.send(msg)

        self.stop()

    @discord.ui.button(label="❌ Non, j'ai encore besoin d'aide", style=discord.ButtonStyle.danger, custom_id="resolu_non")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Seul l'auteur du post peut répondre.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Pas de souci ! Le post reste ouvert. Tu peux continuer à poser tes questions ici 📖"
        )
        self.stop()


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _mark_resolved(thread: discord.Thread, guild: discord.Guild):
    try:
        if isinstance(thread.parent, discord.ForumChannel):
            for tag in thread.parent.available_tags:
                if "résolu" in tag.name.lower() or "✅" in tag.name:
                    current_tags = list(thread.applied_tags)
                    if tag not in current_tags:
                        current_tags.append(tag)
                        await thread.edit(applied_tags=current_tags)
                    break
        await thread.edit(archived=True, locked=True)
    except Exception as e:
        logger.warning(f"Impossible de marquer le thread résolu: {e}")


# ─── Cog principal ────────────────────────────────────────────────────────────

class ForumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        pass

    # ─── Nouveau post créé ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if not isinstance(thread.parent, discord.ForumChannel):
            return

        _last_message[thread.id] = datetime.now(timezone.utc)

        # ── Suivi des forums d'aide classiques ──────────────────────────────
        parent = thread.parent
        if parent.id not in FORUM_CHANNEL_IDS:
            return

    # ─── Suivi de l'activité ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        # ── Suivi d'activité pour les forums d'aide ──────────────────────────
        if not isinstance(message.channel, discord.Thread):
            return
        parent = message.channel.parent
        if not parent or parent.id not in FORUM_CHANNEL_IDS:
            return

        thread_id = message.channel.id
        _last_message[thread_id] = datetime.now(timezone.utc)

        db = self.bot.db
        if db is not None:
            await _clear_notified(db, thread_id)

async def setup(bot):
    await bot.add_cog(ForumCog(bot))
