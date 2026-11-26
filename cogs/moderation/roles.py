"""🎭 Rôles : ajout/retrait, création, surnoms, reaction roles, dons, editmember."""
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import err_embed, hexc, info_embed, now, ok_embed, send_mod_log
from noyau.permissions import PA_TEST, SAINT, STAFF, niveau, verifier_cible


class Roles(commands.Cog, name="Rôles"):
    """🎭 Gestion des rôles et des surnoms."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="addrole", description="Ajouter un rôle à un membre.", usage="@membre @rôle")
    @niveau(STAFF)
    async def addrole(self, ctx, membre: discord.Member, role: discord.Role):
        try:
            await membre.add_roles(role)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible d'ajouter le rôle."))
        await send_mod_log("ADDROLE", membre, ctx.author, f"Rôle: {role.name}")
        await ctx.reply(embed=ok_embed(f"Rôle **{role.name}** ajouté à <@{membre.id}>."))

    @commands.hybrid_command(name="removerole", aliases=["takerole"], description="Retirer un rôle à un membre.", usage="@membre @rôle")
    @niveau(STAFF)
    async def removerole(self, ctx, membre: discord.Member, role: discord.Role):
        try:
            await membre.remove_roles(role)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de retirer le rôle."))
        await send_mod_log("REMOVEROLE", membre, ctx.author, f"Rôle: {role.name}")
        await ctx.reply(embed=ok_embed(f"Rôle **{role.name}** retiré de <@{membre.id}>."))

    @commands.hybrid_command(name="giverole", description="Donner un rôle à un membre, ou à tout le monde avec « all ».", usage="@rôle <@membre|all>")
    @app_commands.describe(cible="Un membre (@mention / ID) ou « all »")
    @niveau(STAFF)
    async def giverole(self, ctx, role: discord.Role, cible: str):
        await ctx.defer()
        if cible.lower() == "all":
            n = 0
            for m in ctx.guild.members:
                if not m.bot and role not in m.roles:
                    try:
                        await m.add_roles(role)
                    except discord.HTTPException:
                        pass
                    n += 1
                    await asyncio.sleep(0.3)
            return await ctx.send(embed=ok_embed(f"Rôle **{role.name}** donné à **{n}** membre(s)."))
        try:
            membre = await commands.MemberConverter().convert(ctx, cible)
        except commands.BadArgument:
            return await ctx.send(embed=err_embed("Membre introuvable."))
        try:
            await membre.add_roles(role)
        except discord.HTTPException:
            return await ctx.send(embed=err_embed("Impossible d'ajouter le rôle."))
        await ctx.send(embed=ok_embed(f"Rôle **{role.name}** donné à <@{membre.id}>."))

    @commands.hybrid_command(name="createrole", description="Créer un rôle.", usage="<nom> [couleur hex]")
    @niveau(STAFF)
    async def createrole(self, ctx, nom: str, couleur: str = "#99AAB5"):
        try:
            c = hexc(couleur)
        except ValueError:
            c = hexc("#99AAB5")
        try:
            role = await ctx.guild.create_role(name=nom, color=c, reason=f"[CREATEROLE] par {ctx.author}")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de créer le rôle."))
        await send_mod_log("CREATEROLE", (role.name, role.id), ctx.author, f"Rôle créé: {nom}")
        await ctx.reply(embed=ok_embed(f"🎭 Rôle **{role.name}** créé avec succès (ID: `{role.id}`)."))

    @commands.hybrid_command(name="deleterole", description="Supprimer un rôle.", usage="@rôle")
    @niveau(STAFF)
    async def deleterole(self, ctx, role: discord.Role):
        await send_mod_log("DELETEROLE", (role.name, role.id), ctx.author, f"Rôle supprimé: {role.name}")
        try:
            await role.delete(reason=f"[DELETEROLE] par {ctx.author}")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de supprimer le rôle."))
        await ctx.reply(embed=ok_embed(f"🗑️ Rôle **{role.name}** supprimé."))

    @commands.hybrid_command(name="nick", description="Changer le surnom d'un membre (« reset » pour l'enlever).", usage="@membre <surnom|reset>")
    @niveau(PA_TEST)
    async def nick(self, ctx, membre: discord.Member, *, surnom: str = "reset"):
        verifier_cible(ctx, membre, "modifier le surnom de")
        surnom = None if surnom == "reset" else surnom
        try:
            await membre.edit(nick=surnom, reason=f"[NICK] par {ctx.author}")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de changer le surnom (hiérarchie de rôles)."))
        await send_mod_log("NICKNAME", membre, ctx.author, f"Surnom: {surnom}" if surnom else "Surnom réinitialisé")
        await ctx.reply(embed=ok_embed(f"✏️ Surnom de <@{membre.id}> changé en **{surnom}**." if surnom else f"✏️ Surnom de <@{membre.id}> réinitialisé."))

    @commands.hybrid_command(name="editmember", description="Remettre en vérification les membres sans rôle de classe.")
    @niveau(STAFF)
    async def editmember(self, ctx):
        p = await ctx.reply(embed=discord.Embed(color=hexc("#f59e0b"), description="⏳ Analyse des membres..."))
        g = ctx.guild
        mr, uv = g.get_role(ids.MEMBER_ROLE_ID), g.get_role(ids.UNVERIFIED_ROLE_ID)
        if not mr or not uv:
            return await p.edit(embed=err_embed("Rôle Membre ou Unverified introuvable."))
        classes = set(etat.all_classe_role_ids())
        cibles = [m for m in g.members if not m.bot and mr in m.roles and not any(r.id in classes for r in m.roles)]
        if not cibles:
            return await p.edit(embed=ok_embed("Aucun membre à modifier."))
        ok = fail = 0
        for m in cibles:
            try:
                await m.remove_roles(mr)
                if uv not in m.roles:
                    await m.add_roles(uv)
                ok += 1
                await asyncio.sleep(0.3)
            except discord.HTTPException:
                fail += 1
        await p.edit(embed=discord.Embed(color=hexc("#f59e0b"), title="🛠️ editmember — Résultat", timestamp=now(),
                                         description=f"**{ok}** membre(s) remis en vérification." + (f"\n**{fail}** échec(s)." if fail else "")))

    @commands.hybrid_command(name="donate", description="Enregistrer un don (rôle Donateur, VIP dès 30 €).", usage="@membre <montant>")
    @niveau(SAINT)
    async def donate(self, ctx, membre: discord.Member, montant: float):
        g = ctx.guild
        don, vip = g.get_role(ids.DONATOR_ROLE_ID), g.get_role(ids.VIP_ROLE_ID)
        try:
            if montant >= 30:
                await membre.add_roles(*[r for r in (vip, don) if r])
                e = discord.Embed(color=hexc("#FFD700"), title="👑  Nouveau VIP !", timestamp=now(),
                                  description=f"<@{membre.id}> a donné **€{montant:g}** et reçoit le rôle **VIP** ! 💛")
            else:
                if don:
                    await membre.add_roles(don)
                e = discord.Embed(color=hexc("#f5c518"), title="💛  Nouveau donateur !", timestamp=now(),
                                  description=f"<@{membre.id}> a donné **€{montant:g}** ! Merci ! 🙏")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible d'assigner le rôle."))
        e.set_thumbnail(url=membre.display_avatar.url)
        await ctx.channel.send(embed=e)
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        else:
            await ctx.send(embed=ok_embed("Don enregistré."), ephemeral=True)

    # ── Reaction roles (bouton « Obtenir le rôle ») ──

    @commands.hybrid_command(name="setmessagerole", description="Publier un message avec un bouton qui donne un rôle.", usage="@rôle <texte>")
    @niveau(SAINT)
    async def setmessagerole(self, ctx, role: discord.Role, *, texte: str):
        from cogs.serveur.panneaux import build_reaction_role_message
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        sent = await ctx.channel.send(**build_reaction_role_message(texte, role))
        await etat.db.reactionroles.update_one({"messageId": str(sent.id)}, {"$set": {
            "guildId": str(ctx.guild.id), "channelId": str(ctx.channel.id), "messageId": str(sent.id),
            "roleId": str(role.id), "texte": texte}, "$setOnInsert": {"createdAt": now()}}, upsert=True)
        etat.reaction_roles[sent.id] = {"roleId": role.id, "channelId": ctx.channel.id, "guildId": ctx.guild.id, "texte": texte}
        if ctx.interaction:
            await ctx.send(embed=ok_embed("Message publié."), ephemeral=True)

    @commands.hybrid_command(name="listrr", description="Lister les messages à rôle actifs.")
    @niveau(SAINT)
    async def listrr(self, ctx):
        docs = await etat.db.reactionroles.find({"guildId": str(ctx.guild.id)}).to_list(None)
        if not docs:
            return await ctx.reply(embed=info_embed("Aucun reaction role actif sur ce serveur."))
        lignes = []
        for i, d in enumerate(docs):
            r = ctx.guild.get_role(int(d["roleId"]))
            lignes.append(f"**{i + 1}.** Rôle : {'@' + r.name if r else '`' + d['roleId'] + '`'} • Salon : <#{d['channelId']}> • Message ID : `{d['messageId']}`")
        e = discord.Embed(color=hexc("#5865F2"), title=f"🎭 Reaction Roles — {len(docs)} actif(s)", description="\n".join(lignes)[:4096], timestamp=now())
        e.set_footer(text="Utilise +delrr <messageId> pour en supprimer un.")
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="delrr", description="Supprimer un message à rôle.", usage="<ID du message>")
    @niveau(SAINT)
    async def delrr(self, ctx, message_id: str):
        doc = await etat.db.reactionroles.find_one({"messageId": message_id, "guildId": str(ctx.guild.id)})
        if not doc:
            return await ctx.reply(embed=err_embed(f"Aucun reaction role trouvé avec l'ID `{message_id}`."))
        ch = ctx.guild.get_channel(int(doc["channelId"]))
        if ch:
            try:
                await (await ch.fetch_message(int(message_id))).delete()
            except discord.HTTPException:
                pass
        await etat.db.reactionroles.delete_one({"messageId": message_id})
        etat.reaction_roles.pop(int(message_id), None)
        await ctx.reply(embed=ok_embed(f"Reaction role `{message_id}` supprimé."))


async def setup(bot):
    await bot.add_cog(Roles(bot))
