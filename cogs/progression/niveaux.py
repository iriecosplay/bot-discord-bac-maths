import discord
from discord.ext import commands
import logging
from noyau.xp import ROLES_CONFIG, role_for_level, level_from_xp, xp_for_level

logger = logging.getLogger(__name__)

MEMBER_ROLE_ID = 1487181268549374013

ROLE_COLORS = {
    "🔰 Novice":    discord.Color.light_gray(),
    "🌱 Apprenti":  discord.Color.green(),
    "♟️ Stratège":  discord.Color.blue(),
    "📖 Érudit":    discord.Color.purple(),
    "🎵 Virtuose":  discord.Color.gold(),
    "⚡ Titan":     discord.Color.orange(),
    "🔺 Ascendant": discord.Color.red(),
}


class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def setup_roles(self, guild: discord.Guild):
        """Crée les rôles XP s'ils n'existent pas et les positionne correctement."""
        member_role = guild.get_role(MEMBER_ROLE_ID)
        if member_role is None:
            logger.warning(f"Rôle member introuvable dans {guild.name}")
            return

        existing_names = {r.name: r for r in guild.roles}
        created_roles = []

        for config in ROLES_CONFIG:
            name = config["name"]
            if name in existing_names:
                role = existing_names[name]
                # Ensure hoist
                if not role.hoist:
                    await role.edit(hoist=True)
                created_roles.append(role)
            else:
                try:
                    role = await guild.create_role(
                        name=name,
                        color=ROLE_COLORS.get(name, discord.Color.default()),
                        hoist=True,
                        reason="Bot Maths XP - création automatique",
                    )
                    created_roles.append(role)
                    logger.info(f"Rôle créé : {name}")
                except discord.Forbidden:
                    logger.error(f"Impossible de créer le rôle {name} - permissions insuffisantes")

        # Position: place all XP roles just above member_role
        # Get member_role position
        try:
            positions = {}
            base_pos = member_role.position + 1
            for i, role in enumerate(ROLES_CONFIG):
                r = discord.utils.get(guild.roles, name=role["name"])
                if r:
                    positions[r] = base_pos + i

            await guild.edit_role_positions(positions=positions)
            logger.info(f"Rôles repositionnés dans {guild.name}")
        except Exception as e:
            logger.warning(f"Impossible de repositionner les rôles: {e}")

    async def update_member_roles(self, member: discord.Member, new_level: int):
        """Met à jour les rôles XP d'un membre selon son niveau."""
        target_role_name = role_for_level(new_level)
        all_xp_role_names = {r["name"] for r in ROLES_CONFIG}

        roles_to_remove = [r for r in member.roles if r.name in all_xp_role_names]
        role_to_add = discord.utils.get(member.guild.roles, name=target_role_name) if target_role_name else None

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Mise à jour rôle XP")
            if role_to_add and role_to_add not in member.roles:
                await member.add_roles(role_to_add, reason="Montée de niveau XP")
        except discord.Forbidden:
            logger.error(f"Impossible de modifier les rôles de {member}")


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
