import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timezone
from noyau.xp import (
    get_or_create_member, add_xp, level_from_xp, xp_for_level,
    role_for_level, now_utc
)

logger = logging.getLogger(__name__)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


class CommandsCog(commands.Cog, name="Progression"):
    def __init__(self, bot):
        self.bot = bot

    # ─── /profil ────────────────────────────────────────────────────────────

    @app_commands.command(name="profil", description="Voir ton profil XP, niveau et statistiques.")
    @app_commands.describe(membre="Le membre dont voir le profil (toi par défaut)")
    async def profil(self, interaction: discord.Interaction, membre: discord.Member = None):
        target = membre or interaction.user
        db = self.bot.db
        doc = await get_or_create_member(db, target.id, interaction.guild.id)

        xp = doc["xp"]
        level = level_from_xp(xp)
        xp_next = xp_for_level(level + 1)
        xp_current_level = xp_for_level(level)
        progress = xp - xp_current_level
        needed = xp_next - xp_current_level
        bar_length = 20
        filled = int((progress / needed) * bar_length) if needed > 0 else bar_length
        bar = "█" * filled + "░" * (bar_length - filled)

        role_name = role_for_level(level) or "Aucun"

        embed = discord.Embed(
            title=f"📊 Profil de {target.display_name}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="🏆 Niveau", value=str(level), inline=True)
        embed.add_field(name="✨ XP Total", value=f"{xp:,}", inline=True)
        embed.add_field(name="🎭 Rôle", value=role_name, inline=True)
        embed.add_field(
            name=f"Progression vers niveau {level + 1}",
            value=f"`{bar}` {progress:,}/{needed:,} XP",
            inline=False,
        )
        embed.add_field(name="💬 XP Messages", value=f"{doc.get('xp_messages', 0):,}", inline=True)
        embed.add_field(name="🎙️ XP Vocal", value=f"{doc.get('xp_vocal', 0):,}", inline=True)
        embed.add_field(name="📨 Messages envoyés", value=f"{doc.get('total_messages', 0):,}", inline=True)
        embed.add_field(name="🕐 Heures en vocal", value=f"{doc.get('total_vocal_minutes', 0) // 60:,}h{doc.get('total_vocal_minutes', 0) % 60:02d}", inline=True)
        derniere = doc.get("derniere_activite", "N/A")
        if derniere != "N/A":
            try:
                dt = datetime.fromisoformat(derniere)
                derniere = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass
        embed.set_footer(text=f"Dernière activité : {derniere}")
        await interaction.response.send_message(embed=embed)

    # ─── /xp-add ────────────────────────────────────────────────────────────

    @app_commands.command(name="xp-add", description="[Admin] Ajouter de l'XP à un membre.")
    @app_commands.describe(membre="Le membre", montant="Quantité d'XP à ajouter")
    @is_admin()
    async def xp_add(self, interaction: discord.Interaction, membre: discord.Member, montant: int):
        if montant <= 0:
            await interaction.response.send_message("❌ Le montant doit être positif.", ephemeral=True)
            return

        db = self.bot.db
        new_xp, old_level, new_level = await add_xp(db, membre.id, interaction.guild.id, montant)

        roles_cog = self.bot.get_cog("RolesCog")
        if roles_cog and new_level > old_level:
            await roles_cog.update_member_roles(membre, new_level)

        await interaction.response.send_message(
            f"✅ +{montant} XP ajouté à {membre.mention}. XP total : {new_xp:,} (Niv. {new_level})",
            ephemeral=True,
        )

    # ─── /xp-reset ──────────────────────────────────────────────────────────

    @app_commands.command(name="xp-reset", description="[Admin] Remet le profil d'un membre à zéro.")
    @app_commands.describe(membre="Le membre à réinitialiser")
    @is_admin()
    async def xp_reset(self, interaction: discord.Interaction, membre: discord.Member):
        db = self.bot.db
        await db.members.update_one(
            {"user_id": str(membre.id), "guild_id": str(interaction.guild.id)},
            {"$set": {
                "xp": 0, "level": 0, "xp_messages": 0, "xp_vocal": 0,
                "solutions_données": 0, "solutions_reçues": 0,
                "monthly_solutions": 0, "roles_actifs": [],
                "derniere_activite": now_utc(),
            }},
        )

        from noyau.xp import ROLES_CONFIG
        xp_role_names = {r["name"] for r in ROLES_CONFIG}
        roles_to_remove = [r for r in membre.roles if r.name in xp_role_names]
        if roles_to_remove:
            try:
                await membre.remove_roles(*roles_to_remove, reason="Reset XP admin")
            except discord.Forbidden:
                pass

        await interaction.response.send_message(
            f"✅ Profil de {membre.mention} réinitialisé.", ephemeral=True
        )

    # ─── Error handlers ──────────────────────────────────────────────────────

    @xp_add.error
    @xp_reset.error
    async def admin_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CommandsCog(bot))
