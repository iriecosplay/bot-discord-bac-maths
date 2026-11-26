"""🧹 Gestion des salons : clear, purgeuser, slowmode, lock/unlock, nuke, say, announce."""
import discord
from discord import app_commands
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import err_embed, hexc, now, ok_embed, send_mod_log
from noyau.permissions import MOD, STAFF, niveau


async def supprimer_commande(ctx):
    if ctx.interaction is None:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


class Salons(commands.Cog, name="Salons"):
    """🧹 Nettoyage, verrouillage et messages du staff."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="clear", description="Supprimer entre 1 et 100 messages.", usage="<1-100>")
    @niveau(MOD)
    async def clear(self, ctx, nombre: app_commands.Range[int, 1, 100]):
        await ctx.defer(ephemeral=True)
        await supprimer_commande(ctx)
        try:
            deleted = await ctx.channel.purge(limit=nombre, before=ctx.message if ctx.interaction is None else None)
        except discord.HTTPException:
            return await ctx.send(embed=err_embed("Impossible de supprimer les messages (peut-être trop anciens > 14 jours)."), delete_after=5)
        await send_mod_log("CLEAR", (f"{len(deleted)} messages", ctx.channel.id), ctx.author, "Suppression en masse",
                           channel=ctx.channel.id, count=len(deleted))
        e = discord.Embed(color=hexc("#22c55e"), description=f"🗑️ **{len(deleted)}** message(s) supprimé(s).", timestamp=now())
        e.set_footer(text=f"Par {ctx.author.name}")
        await ctx.send(embed=e, delete_after=4, ephemeral=True)

    @commands.hybrid_command(name="purgeuser", description="Supprimer les derniers messages d'un membre dans ce salon.", usage="@membre [nombre]")
    @niveau(MOD)
    async def purgeuser(self, ctx, membre: discord.Member, nombre: app_commands.Range[int, 1, 100] = 50):
        await ctx.defer(ephemeral=True)
        await supprimer_commande(ctx)
        compteur = {"n": 0}

        def check(m):
            if m.author.id == membre.id and compteur["n"] < nombre:
                compteur["n"] += 1
                return True
            return False
        try:
            deleted = await ctx.channel.purge(limit=100, check=check)
        except discord.HTTPException:
            return await ctx.send(embed=err_embed("Impossible de supprimer les messages."))
        await ctx.send(embed=ok_embed(f"🗑️ **{len(deleted)}** message(s) de <@{membre.id}> supprimé(s)."), delete_after=5, ephemeral=True)

    @commands.hybrid_command(name="slowmode", description="Régler le mode lent du salon (0 = désactivé).", usage="<secondes 0-21600>")
    @niveau(MOD)
    async def slowmode(self, ctx, secondes: app_commands.Range[int, 0, 21600]):
        try:
            await ctx.channel.edit(slowmode_delay=secondes)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de régler le slowmode."))
        await send_mod_log("SLOWMODE", (ctx.channel.name, ctx.channel.id), ctx.author, f"Slowmode réglé à {secondes}s", channel=ctx.channel.id)
        await ctx.reply(embed=ok_embed("Slowmode désactivé." if secondes == 0 else f"⏱️ Slowmode réglé à **{secondes} secondes**."))

    @commands.hybrid_command(name="lock", description="Verrouiller un salon pour les membres.", usage="[#salon] [raison]")
    @niveau(MOD)
    async def lock(self, ctx, salon: discord.TextChannel | None = None, *, raison: str = "Non précisé"):
        salon = salon or ctx.channel
        role = ctx.guild.get_role(ids.MEMBER_ROLE_ID)
        try:
            await salon.set_permissions(role, send_messages=False, send_messages_in_threads=False, create_public_threads=False,
                                        create_private_threads=False, add_reactions=False)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de verrouiller le salon."))
        await send_mod_log("LOCK", (salon.name, salon.id), ctx.author, raison, channel=salon.id)
        await ctx.reply(embed=discord.Embed(color=hexc("#ef4444"), title="🔒 Salon verrouillé", timestamp=now(),
                                            description=f"{salon.mention} est maintenant verrouillé.\nUtilise `+unlock` pour le déverrouiller."))

    @commands.hybrid_command(name="unlock", description="Déverrouiller un salon.", usage="[#salon]")
    @niveau(MOD)
    async def unlock(self, ctx, salon: discord.TextChannel | None = None):
        salon = salon or ctx.channel
        role = ctx.guild.get_role(ids.MEMBER_ROLE_ID)
        try:
            await salon.set_permissions(role, send_messages=None, send_messages_in_threads=True, create_public_threads=None,
                                        create_private_threads=None, add_reactions=None)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de déverrouiller le salon."))
        await send_mod_log("UNLOCK", (salon.name, salon.id), ctx.author, "Salon déverrouillé", channel=salon.id)
        await ctx.reply(embed=discord.Embed(color=hexc("#22c55e"), title="🔓 Salon déverrouillé", timestamp=now(),
                                            description=f"{salon.mention} est à nouveau accessible."))

    @commands.hybrid_command(name="nuke", description="Recréer le salon à l'identique (efface tout l'historique).")
    @niveau(STAFF)
    async def nuke(self, ctx):
        ch = ctx.channel
        try:
            clone = await ch.clone(reason=f"[NUKE] par {ctx.author}")
            await clone.edit(position=ch.position)
            await ch.delete(reason=f"[NUKE] par {ctx.author}")
            e = discord.Embed(color=hexc("#ff0000"), title="💣 Salon nuke", description="Ce salon a été entièrement purgé.", timestamp=now())
            e.set_footer(text=f"Par {ctx.author.name}")
            await clone.send(embed=e, delete_after=5)
        except discord.HTTPException:
            await ctx.reply(embed=err_embed("Impossible de nuker ce salon."))

    async def _envoyer(self, ctx, salon, message, annonce):
        salon = salon or ctx.channel
        await supprimer_commande(ctx)
        if annonce:
            e = discord.Embed(color=hexc("#f5c518"), title="📢 Annonce", description=message, timestamp=now())
            e.set_footer(text=f"Par {ctx.author.name}")
            await salon.send(embed=e)
        else:
            await salon.send(message)
        if ctx.interaction:
            await ctx.send(embed=ok_embed(f"Message envoyé dans {salon.mention}."), ephemeral=True)

    @commands.hybrid_command(name="say", description="Faire parler le bot.", usage="[#salon] <message>")
    @niveau(STAFF)
    async def say(self, ctx, salon: discord.TextChannel | None = None, *, message: str):
        await self._envoyer(ctx, salon, message, annonce=False)

    @commands.hybrid_command(name="announce", description="Publier une annonce mise en forme.", usage="[#salon] <message>")
    @niveau(STAFF)
    async def announce(self, ctx, salon: discord.TextChannel | None = None, *, message: str):
        await self._envoyer(ctx, salon, message, annonce=True)


async def setup(bot):
    await bot.add_cog(Salons(bot))
