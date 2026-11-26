import discord
from discord.ext import commands
import logging
import asyncio
import random
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Rôles autorisés à lancer des giveaways
ALLOWED_ROLE_IDS = {
    1496261745495245004,
    1487180890277806151,
}

PROFIL_TIP = "💡 Tu peux vérifier ton nombre de messages et tes heures vocales avec la commande `/profil`."


def has_giveaway_permission():
    """Vérifie que l'utilisateur a un des rôles autorisés OU un rôle au-dessus."""
    async def predicate(ctx: commands.Context) -> bool:
        member = ctx.author
        guild = ctx.guild
        if member.guild_permissions.administrator:
            return True
        # Récupère les positions des rôles autorisés
        allowed_positions = set()
        for role in guild.roles:
            if role.id in ALLOWED_ROLE_IDS:
                allowed_positions.add(role.position)
        if not allowed_positions:
            return False
        min_allowed_position = min(allowed_positions)
        # L'utilisateur doit avoir un rôle dont la position >= min position autorisée
        for role in member.roles:
            if role.position >= min_allowed_position:
                return True
        return False
    return commands.check(predicate)


def parse_duration(duration_str: str) -> int:
    """Convertit une durée comme '2h', '30m', '1h30m' en secondes."""
    duration_str = duration_str.lower().strip()
    total_seconds = 0
    import re
    hours = re.findall(r'(\d+)\s*h', duration_str)
    minutes = re.findall(r'(\d+)\s*m', duration_str)
    if not hours and not minutes:
        # Suppose que c'est en heures si juste un nombre
        try:
            total_seconds = int(duration_str) * 3600
        except ValueError:
            raise ValueError(f"Format de durée invalide : `{duration_str}`. Utilise par exemple `2h`, `30m`, `1h30m`.")
    else:
        for h in hours:
            total_seconds += int(h) * 3600
        for m in minutes:
            total_seconds += int(m) * 60
    if total_seconds <= 0:
        raise ValueError("La durée doit être supérieure à 0.")
    return total_seconds


def format_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}h{minutes:02d}m"
    elif hours:
        return f"{hours}h"
    else:
        return f"{minutes}m"


# ─── Vue bouton "Participer" ──────────────────────────────────────────────────

class GiveawayView(discord.ui.View):
    def __init__(self, min_messages: int = 0, min_vocal_hours: float = 0, open: bool = True):
        super().__init__(timeout=None)
        self.participants: set[int] = set()
        self.min_messages = min_messages
        self.min_vocal_hours = min_vocal_hours
        self.min_vocal_minutes = int(min_vocal_hours * 60)
        self.open = open

    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.primary, custom_id="gw_participate")
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.open:
            await interaction.response.send_message("❌ Ce giveaway est terminé.", ephemeral=True)
            return

        user = interaction.user
        db = interaction.client.db

        # Vérification des conditions si requises
        if self.min_messages > 0 or self.min_vocal_minutes > 0:
            if db is None:
                await interaction.response.send_message("❌ Base de données indisponible.", ephemeral=True)
                return
            doc = await db.members.find_one({
                "user_id": str(user.id),
                "guild_id": str(interaction.guild.id)
            })
            user_messages = doc.get("total_messages", 0) if doc else 0
            user_vocal_min = doc.get("total_vocal_minutes", 0) if doc else 0

            if self.min_messages > 0 and user_messages < self.min_messages:
                missing = self.min_messages - user_messages
                await interaction.response.send_message(
                    f"❌ Tu n'as pas encore assez de messages pour participer.\n"
                    f"**Requis :** {self.min_messages:,} messages · **Tu en as :** {user_messages:,} ({missing:,} manquants)\n"
                    f"{PROFIL_TIP}",
                    ephemeral=True,
                )
                return

            if self.min_vocal_minutes > 0 and user_vocal_min < self.min_vocal_minutes:
                user_h = user_vocal_min // 60
                user_m = user_vocal_min % 60
                req_h = self.min_vocal_minutes // 60
                req_m = self.min_vocal_minutes % 60
                await interaction.response.send_message(
                    f"❌ Tu n'as pas encore assez d'heures en vocal pour participer.\n"
                    f"**Requis :** {req_h}h{req_m:02d} en vocal · **Tu as :** {user_h}h{user_m:02d}\n"
                    f"{PROFIL_TIP}",
                    ephemeral=True,
                )
                return

        if user.id in self.participants:
            self.participants.discard(user.id)
            await interaction.response.send_message("✅ Tu t'es retiré du giveaway.", ephemeral=True)
        else:
            self.participants.add(user.id)
            await interaction.response.send_message("🎉 Tu es bien inscrit au giveaway !", ephemeral=True)

        # Met à jour le compteur de participants sur le message
        try:
            await interaction.message.edit(
                embed=self._update_embed(interaction.message.embeds[0]),
            )
        except Exception:
            pass

    def _update_embed(self, embed: discord.Embed) -> discord.Embed:
        new_embed = embed.copy()
        for i, field in enumerate(new_embed.fields):
            if field.name == "👥 Participants":
                new_embed.set_field_at(i, name="👥 Participants", value=str(len(self.participants)), inline=True)
                break
        return new_embed


# ─── Cog principal ────────────────────────────────────────────────────────────

class GiveawayCog(commands.Cog, name="Giveaways"):
    def __init__(self, bot):
        self.bot = bot

    async def _run_giveaway(
        self,
        ctx: commands.Context,
        duration_seconds: int,
        prize: str,
        min_messages: int = 0,
        min_vocal_hours: float = 0,
    ):
        """Lance un giveaway et sélectionne un gagnant après la durée."""
        end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        end_timestamp = int(end_time.timestamp())

        view = GiveawayView(min_messages=min_messages, min_vocal_hours=min_vocal_hours)

        embed = discord.Embed(
            title="🎉 GIVEAWAY",
            description=f"**{prize}**",
            color=discord.Color.gold(),
        )
        embed.add_field(name="⏰ Fin", value=f"<t:{end_timestamp}:R> (<t:{end_timestamp}:f>)", inline=False)
        embed.add_field(name="👥 Participants", value="0", inline=True)
        embed.add_field(name="🏆 Gagnant(s)", value="1", inline=True)

        conditions = []
        if min_messages > 0:
            conditions.append(f"📨 Minimum **{min_messages:,} messages** envoyés sur le serveur")
        if min_vocal_hours > 0:
            h = int(min_vocal_hours)
            m = int((min_vocal_hours - h) * 60)
            label = f"{h}h{m:02d}" if m else f"{h}h"
            conditions.append(f"🎙️ Minimum **{label}** passées en vocal sur le serveur")

        if conditions:
            embed.add_field(
                name="📋 Conditions de participation",
                value="\n".join(conditions) + f"\n\n{PROFIL_TIP}",
                inline=False,
            )
        else:
            embed.add_field(name="📋 Conditions", value="Tout le monde peut participer !", inline=False)

        embed.set_footer(text=f"Organisé par {ctx.author.display_name} • Appuie sur le bouton pour participer !")

        gw_message = await ctx.send(embed=embed, view=view)

        # Attendre la fin du giveaway
        await asyncio.sleep(duration_seconds)

        # Clore les participations
        view.open = False
        for item in view.children:
            item.disabled = True

        if not view.participants:
            end_embed = embed.copy()
            end_embed.color = discord.Color.red()
            end_embed.title = "🎉 GIVEAWAY TERMINÉ"
            end_embed.set_field_at(0, name="⏰ Terminé", value=f"<t:{end_timestamp}:f>", inline=False)
            try:
                await gw_message.edit(embed=end_embed, view=view)
            except Exception:
                pass
            await ctx.send("😔 Personne n'a participé au giveaway. Aucun gagnant.")
            return

        # Sélection du gagnant
        winner_id = random.choice(list(view.participants))
        winner = ctx.guild.get_member(winner_id)
        if winner is None:
            try:
                winner = await ctx.guild.fetch_member(winner_id)
            except Exception:
                winner = None

        winner_mention = winner.mention if winner else f"<@{winner_id}>"

        end_embed = embed.copy()
        end_embed.color = discord.Color.green()
        end_embed.title = "🎉 GIVEAWAY TERMINÉ"
        end_embed.set_field_at(0, name="⏰ Terminé", value=f"<t:{end_timestamp}:f>", inline=False)
        end_embed.set_field_at(1, name="👥 Participants", value=str(len(view.participants)), inline=True)
        try:
            await gw_message.edit(embed=end_embed, view=view)
        except Exception:
            pass

        result_embed = discord.Embed(
            title="🏆 Résultat du Giveaway",
            description=f"Félicitations {winner_mention} ! Tu as gagné **{prize}** ! 🎊",
            color=discord.Color.gold(),
        )
        result_embed.add_field(name="👥 Participants", value=str(len(view.participants)), inline=True)
        await ctx.send(content=winner_mention, embed=result_embed)

    # ─── +setgivewaytext ─────────────────────────────────────────────────────

    @commands.command(name="setgivewaytext", description="Giveaway réservé aux membres ayant X messages.", usage="<nb_messages> <durée> [prix]", extras={"niveau": "giveaway"})
    @has_giveaway_permission()
    async def setgivewaytext(self, ctx: commands.Context, min_messages: int, duration: str, *, prize: str = "Surprise 🎁"):
        """
        Lance un giveaway avec un minimum de messages requis.
        Usage : +setgivewaytext <nb_messages> <durée> [prix]
        Exemple : +setgivewaytext 100 2h Nitro Discord
        """
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        if min_messages < 0:
            await ctx.send("❌ Le nombre de messages minimum doit être positif.")
            return

        await ctx.message.delete()
        await self._run_giveaway(ctx, seconds, prize, min_messages=min_messages)

    # ─── +setgivewayvoc ──────────────────────────────────────────────────────

    @commands.command(name="setgivewayvoc", description="Giveaway réservé aux membres ayant X heures de vocal.", usage="<heures> <durée> [prix]", extras={"niveau": "giveaway"})
    @has_giveaway_permission()
    async def setgivewayvoc(self, ctx: commands.Context, min_hours: float, duration: str, *, prize: str = "Surprise 🎁"):
        """
        Lance un giveaway avec un minimum d'heures en vocal requis.
        Usage : +setgivewayvoc <heures_vocal> <durée> [prix]
        Exemple : +setgivewayvoc 5 1h Nitro Discord
        """
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        if min_hours < 0:
            await ctx.send("❌ Le nombre d'heures minimum doit être positif.")
            return

        await ctx.message.delete()
        await self._run_giveaway(ctx, seconds, prize, min_vocal_hours=min_hours)

    # ─── +setgiveway ─────────────────────────────────────────────────────────

    @commands.command(name="setgiveway", description="Giveaway ouvert à tous.", usage="<durée> [prix]", extras={"niveau": "giveaway"})
    @has_giveaway_permission()
    async def setgiveway(self, ctx: commands.Context, duration: str, *, prize: str = "Surprise 🎁"):
        """
        Lance un giveaway ouvert à tous.
        Usage : +setgiveway <durée> [prix]
        Exemple : +setgiveway 2h Nitro Discord
        """
        try:
            seconds = parse_duration(duration)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return

        await ctx.message.delete()
        await self._run_giveaway(ctx, seconds, prize)

    # ─── Gestion des erreurs ─────────────────────────────────────────────────

    @setgivewaytext.error
    @setgivewayvoc.error
    @setgiveway.error
    async def giveaway_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "❌ Tu n'as pas la permission de lancer un giveaway. "
                "Il faut avoir un rôle suffisamment élevé.",
                delete_after=10,
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            cmd = ctx.command.name
            if cmd == "setgivewaytext":
                await ctx.send(
                    "❌ Usage : `+setgivewaytext <nb_messages> <durée> [prix]`\n"
                    "Exemple : `+setgivewaytext 100 2h Nitro Discord`",
                    delete_after=15,
                )
            elif cmd == "setgivewayvoc":
                await ctx.send(
                    "❌ Usage : `+setgivewayvoc <heures_vocal> <durée> [prix]`\n"
                    "Exemple : `+setgivewayvoc 5 1h Nitro Discord`",
                    delete_after=15,
                )
            elif cmd == "setgiveway":
                await ctx.send(
                    "❌ Usage : `+setgiveway <durée> [prix]`\n"
                    "Exemple : `+setgiveway 2h Nitro Discord`",
                    delete_after=15,
                )
        else:
            logger.error(f"Erreur giveaway : {error}")
            await ctx.send(f"❌ Une erreur est survenue : {error}", delete_after=15)
 

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
