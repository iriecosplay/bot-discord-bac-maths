"""ℹ️ Commandes d'information accessibles à tous."""
import platform
import time

import discord
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import err_embed, hexc, now


class Infos(commands.Cog, name="Infos"):
    """ℹ️ Infos sur le serveur, les membres et le bot."""

    def __init__(self, bot):
        self.bot = bot
        self.debut = time.time()

    @commands.hybrid_command(name="ping", description="Latence du bot.")
    async def ping(self, ctx):
        e = discord.Embed(color=hexc("#5865F2"), title="🏓 Pong !")
        e.add_field(name="API", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        if ctx.interaction is None:
            e.add_field(name="Latence bot", value=f"{int((now() - ctx.message.created_at).total_seconds() * 1000)}ms", inline=True)
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="botinfo", description="Informations sur le bot.")
    async def botinfo(self, ctx):
        up = int(time.time() - self.debut)
        e = discord.Embed(color=hexc("#5865F2"), title="🤖 Bot Info", timestamp=now())
        e.set_thumbnail(url=self.bot.user.display_avatar.url)
        e.add_field(name="Nom", value=str(self.bot.user), inline=True)
        e.add_field(name="Uptime", value=f"{up // 3600}h {(up % 3600) // 60}m", inline=True)
        e.add_field(name="Python", value=platform.python_version(), inline=True)
        e.add_field(name="Commandes", value=str(len(self.bot.commands)), inline=True)
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="serverinfo", description="Informations sur le serveur.")
    async def serverinfo(self, ctx):
        g = ctx.guild
        bots = sum(1 for m in g.members if m.bot)
        e = discord.Embed(color=hexc("#5865F2"), title=f"🏠 {g.name}", timestamp=now())
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="Propriétaire", value=f"<@{g.owner_id}>", inline=True)
        e.add_field(name="Membres", value=f"{g.member_count - bots} humains · {bots} bots", inline=True)
        e.add_field(name="Salons", value=str(len(g.channels)), inline=True)
        e.add_field(name="Rôles", value=str(len(g.roles)), inline=True)
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="membercount", description="Nombre de membres.")
    async def membercount(self, ctx):
        n = sum(1 for m in ctx.guild.members if not m.bot)
        await ctx.reply(embed=discord.Embed(color=hexc("#5865F2"), description=f"👥 **{n}** membres."))

    @commands.hybrid_command(name="userinfo", description="Informations sur un membre.", usage="[@membre]")
    async def userinfo(self, ctx, membre: discord.Member | None = None):
        t = membre or ctx.author
        roles = ", ".join(r.mention for r in reversed(t.roles) if r.id != ctx.guild.id) or "Aucun"
        e = discord.Embed(color=hexc("#5865F2"), title=f"👤 {t}", timestamp=now())
        e.set_thumbnail(url=t.display_avatar.url)
        e.add_field(name="ID", value=str(t.id), inline=True)
        e.add_field(name="Rejoint", value=f"<t:{etat.ts(t.joined_at)}:R>", inline=True)
        e.add_field(name="Compte créé", value=f"<t:{etat.ts(t.created_at)}:R>", inline=True)
        e.add_field(name="Niveau de permission", value=etat.perm_label(etat.perm_level(t)), inline=True)
        e.add_field(name="Perm Jail", value="⛓️ Oui" if etat.has_perm_jail(t) else "✖️ Non", inline=True)
        e.add_field(name="En prison", value="⛓️ Oui" if t.get_role(ids.PRISON_ROLE_ID) else "✅ Non", inline=True)
        e.add_field(name="Rôles", value=roles[:1024], inline=False)
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="avatar", description="Afficher l'avatar d'un membre.", usage="[@membre]")
    async def avatar(self, ctx, membre: discord.Member | None = None):
        t = membre or ctx.author
        e = discord.Embed(color=hexc("#5865F2"), title=f"🖼️ {t.name}")
        e.set_image(url=t.display_avatar.with_size(512).url)
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="invite", aliases=["invites"], description="Nombre de personnes invitées par un membre.", usage="[@membre]")
    async def invite(self, ctx, membre: discord.Member | None = None):
        t = membre or ctx.author
        try:
            total = sum(i.uses or 0 for i in await ctx.guild.invites() if i.inviter and i.inviter.id == t.id)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de récupérer les invitations."))
        e = discord.Embed(color=hexc("#5865F2"), title="📨 Invitations", timestamp=now(),
                          description=f"**{t.name}** a invité **{total}** membre(s) sur le serveur.")
        e.set_thumbnail(url=t.display_avatar.url)
        await ctx.reply(embed=e)


async def setup(bot):
    await bot.add_cog(Infos(bot))
