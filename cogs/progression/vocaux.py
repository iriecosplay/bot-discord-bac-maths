import discord
from discord.ext import commands, tasks
import logging

from noyau.permissions import administrateur

logger = logging.getLogger(__name__)

# Salon "hub" de référence pour la catégorie
HUB_CHANNEL_ID = 1507132699524071485

# Catégorie où placer la vocale en haut
CATEGORY_ID = 1487179769866092727

# (le message de bienvenue est maintenant dans cogs/serveur/bienvenue.py)

# ─── Modals (Formulaires) ────────────────────────────────────────────────

class VocalModal(discord.ui.Modal, title="Créer ta vocale"):
    channel_name = discord.ui.TextInput(
        label="Comment veux-tu appeler le salon ?",
        style=discord.TextStyle.short,
        placeholder="Ex: Chill, Gaming...",
        required=True,
        max_length=50
    )

    user_limit = discord.ui.TextInput(
        label="Nombre max de personnes (0 = infini)",
        style=discord.TextStyle.short,
        default="0",
        required=True,
        max_length=2
    )

    def __init__(self, cog: "VocalCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.user_limit.value)
            if limit < 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ La limite doit être un nombre entier positif ou 0.",
                ephemeral=True
            )
            return

        # 🟢 MODIFICATION : On récupère directement la catégorie cible via CATEGORY_ID
        category = interaction.guild.get_channel(CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ La catégorie de destination est introuvable ou invalide.",
                ephemeral=True
            )
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
                use_embedded_activities=True,
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
                use_embedded_activities=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
            ),
        }

        name = f"🎙️ {self.channel_name.value}"

        try:
            vc = await interaction.guild.create_voice_channel(
                name=name,
                category=category, # Applique la catégorie récupérée
                user_limit=limit if limit > 0 else None,
                overwrites=overwrites,
                reason=f"Vocale créée par {interaction.user} via le bouton."
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Je n'ai pas la permission de créer un salon.", ephemeral=True)
            return
        except Exception as e:
            logger.error(f"[VOCAL] Erreur création pour {interaction.user} : {e}")
            await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ── Placer la vocale en haut de la catégorie (position 0) ──
        try:
            # Récupère tous les salons vocaux de la catégorie, triés par position
            voice_channels = sorted(
                [c for c in category.channels if isinstance(c, discord.VoiceChannel)],
                key=lambda c: c.position
            )
            # Position = position du premier salon vocal de la catégorie
            top_position = voice_channels[0].position if voice_channels else 0
            await vc.edit(position=top_position)
        except Exception as e:
            logger.warning(f"[VOCAL] Impossible de déplacer la vocale en haut : {e}")

        self.cog._user_channels[interaction.user.id] = vc
        self.cog._empty_since[vc.id] = discord.utils.utcnow()

        limit_str = f"**{limit} personnes max**" if limit > 0 else "**illimitée**"
        await interaction.response.send_message(
            f"✅ Ta vocale **{vc.mention}** a été créée ({limit_str}) !\n"
            f"*(Attention : elle sera supprimée après 1 heure d'inactivité)*",
            ephemeral=True
        )


class EditNameModal(discord.ui.Modal, title="Modifier le nom du salon"):
    new_name = discord.ui.TextInput(
        label="Nouveau nom :",
        style=discord.TextStyle.short,
        placeholder="Ex: Tryhard Ranked",
        required=True,
        max_length=50
    )

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc

    async def on_submit(self, interaction: discord.Interaction):
        new_channel_name = f"🎙️ {self.new_name.value}"
        await self.vc.edit(name=new_channel_name)
        await interaction.response.send_message(f"✅ Le nom de ta vocale a été changé en **{self.new_name.value}** !", ephemeral=True)


class EditLimitModal(discord.ui.Modal, title="Modifier la limite de places"):
    new_limit = discord.ui.TextInput(
        label="Nouvelle limite (0 = infini) :",
        style=discord.TextStyle.short,
        required=True,
        max_length=2
    )

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.new_limit.value)
            if limit < 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ La limite doit être un nombre entier positif ou 0.", ephemeral=True)
            return

        await self.vc.edit(user_limit=limit if limit > 0 else None)
        limit_str = f"**{limit} personnes max**" if limit > 0 else "**illimitée**"
        await interaction.response.send_message(f"✅ La limite de ta vocale est maintenant {limit_str} !", ephemeral=True)


# ─── Vue (Boutons) ───────────────────────────────────────────────────────

class CreateVocalView(discord.ui.View):
    def __init__(self, cog: "VocalCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Créer une vocale",
        style=discord.ButtonStyle.primary,
        custom_id="persistent_create_vocal_btn",
        emoji="🎙️"
    )
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = self.cog._get_user_channel(interaction.user.id)
        if existing is not None:
            await interaction.response.send_message(
                f"❌ Tu as déjà une vocale active : **{existing.name}**. Supprime-la d'abord pour en créer une nouvelle.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(VocalModal(self.cog))

    @discord.ui.button(
        label="Modifier le nom",
        style=discord.ButtonStyle.secondary,
        custom_id="persistent_edit_name_btn",
        emoji="✏️"
    )
    async def edit_name_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.cog._get_user_channel(interaction.user.id)
        if vc is None:
            await interaction.response.send_message("❌ Tu n'as aucune vocale active à modifier.", ephemeral=True)
            return

        await interaction.response.send_modal(EditNameModal(vc))

    @discord.ui.button(
        label="Modifier la limite",
        style=discord.ButtonStyle.secondary,
        custom_id="persistent_edit_limit_btn",
        emoji="👥"
    )
    async def edit_limit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.cog._get_user_channel(interaction.user.id)
        if vc is None:
            await interaction.response.send_message("❌ Tu n'as aucune vocale active à modifier.", ephemeral=True)
            return

        await interaction.response.send_modal(EditLimitModal(vc))


# ─── Cog Principal ───────────────────────────────────────────────────────

class VocalCog(commands.Cog, name="Vocaux"):
    def __init__(self, bot):
        self.bot = bot
        self._user_channels: dict[int, discord.VoiceChannel] = {}
        self._empty_since: dict[int, discord.utils.utcnow] = {}

    async def cog_load(self):
        self.bot.add_view(CreateVocalView(self))
        self.vocal_cleanup_task.start()

    async def cog_unload(self):
        self.vocal_cleanup_task.cancel()

    def _get_user_channel(self, user_id: int) -> discord.VoiceChannel | None:
        ch = self._user_channels.get(user_id)
        if ch is not None and ch not in self.bot.get_all_channels():
            del self._user_channels[user_id]
            self._empty_since.pop(ch.id, None)
            return None
        return ch

    def _embed_panneau(self):
        return discord.Embed(
            title="🎙️ Salons Vocaux Temporaires",
            description=(
                "Utilise les boutons ci-dessous pour gérer ton salon vocal !\n\n"
                "• **Créer** un salon à ton nom.\n"
                "• **Modifier** son nom à tout moment.\n"
                "• **Gérer** la limite du nombre de personnes.\n\n"
                "⚠️ **La vocale se supprimera automatiquement après 1 heure si personne n'y est connecté.**"
            ),
            color=discord.Color.blurple()
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """Remplace l'ancien panneau (posté par progressionbot) dans le salon hub."""
        if getattr(self, "_pret", False):
            return
        self._pret = True
        from noyau.etat import get_chan, supprimer_anciens_panneaux, deja_poste
        hub = await get_chan(HUB_CHANNEL_ID)
        if hub and await supprimer_anciens_panneaux(hub) and not await deja_poste(hub):
            await hub.send(embed=self._embed_panneau(), view=CreateVocalView(self))

    @commands.command(name="setupvocal", description="Publier le panneau des vocaux temporaires dans ce salon.")
    @administrateur()
    async def setupvocal(self, ctx: commands.Context):
        await ctx.send(embed=self._embed_panneau(), view=CreateVocalView(self))
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @tasks.loop(minutes=5)
    async def vocal_cleanup_task(self):
        now = discord.utils.utcnow()

        for uid, vc in list(self._user_channels.items()):
            if not self.bot.get_channel(vc.id):
                continue

            if len(vc.members) == 0:
                if vc.id not in self._empty_since:
                    self._empty_since[vc.id] = now
                else:
                    elapsed_seconds = (now - self._empty_since[vc.id]).total_seconds()
                    if elapsed_seconds >= 3600:
                        try:
                            await vc.delete(reason="Salon vocal inactif pendant 1 heure.")
                            logger.info(f"[VOCAL] Salon {vc.name} supprimé pour inactivité.")
                        except Exception as e:
                            logger.error(f"[VOCAL] Erreur lors de la suppression de {vc.name} : {e}")
            else:
                if vc.id in self._empty_since:
                    del self._empty_since[vc.id]

    @vocal_cleanup_task.before_loop
    async def before_vocal_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.VoiceChannel):
            return

        to_remove_uid = None
        for uid, vc in self._user_channels.items():
            if vc.id == channel.id:
                to_remove_uid = uid
                break

        if to_remove_uid:
            del self._user_channels[to_remove_uid]
            self._empty_since.pop(channel.id, None)
            logger.info(f"[VOCAL] Vocale de user_id={to_remove_uid} supprimée (mémoire nettoyée).")


async def setup(bot):
    await bot.add_cog(VocalCog(bot))
