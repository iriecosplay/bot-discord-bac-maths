"""⚖️ Sanctions : prison, warns, mute, kick, ban, menu de sanction, actions de masse."""
import asyncio
import logging
import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import Composants, bouton, err_embed, hexc, info_embed, now, ok_embed, send_mod_log
from noyau.permissions import (JUNIOR, MOD, PA_TEST, SAINT, STAFF, PermissionRefusee, niveau, perm_jail,
                               verifier_cible)

logger = logging.getLogger(__name__)
B = discord.ButtonStyle
MAX_TIMEOUT = 28 * 24 * 3600
SANCTIONS_SURVEILLEES = {"prison", "warn", "warng", "mute", "kick", "ban"}


async def dm(member, embed):
    try:
        await member.send(embed=embed)
    except discord.HTTPException:
        pass


async def emprisonner(target: discord.Member, moderator, reason) -> list[int]:
    roles = etat.roles_a_sauver(target)
    await etat.save_prison_roles(target.id, target.guild.id, roles, reason, moderator.id)
    etat.prison_release_whitelist.add(target.id)
    try:
        await etat.mettre_en_prison_roles(target, f"[PRISON] {reason} — par {moderator}")
    finally:
        asyncio.get_running_loop().call_later(3, etat.prison_release_whitelist.discard, target.id)
    await send_mod_log("PRISON", target, moderator, reason)
    return roles


class Sanctions(commands.Cog, name="Sanctions"):
    """⚖️ Prison, avertissements, mute, kick, ban."""

    def __init__(self, bot):
        self.bot = bot
        self.spam = etat.Fenetre(ids.SANCTION_WINDOW)

    async def cog_before_invoke(self, ctx):
        """Anti-abus : un modérateur qui enchaîne les sanctions est kick."""
        if ctx.command.name not in SANCTIONS_SURVEILLEES or etat.is_owner(ctx.author.id):
            return
        d = self.spam.get(ctx.author.id)
        if d is None:
            self.spam.start(ctx.author.id, count=1)
            return
        d["count"] += 1
        if d["count"] >= ids.SANCTION_THRESHOLD:
            self.spam.delete(ctx.author.id)
            try:
                await ctx.author.kick(reason=f"[AUTO-MOD] Spam de commandes de sanction ({d['count']}x en {int(ids.SANCTION_WINDOW)}s)")
                await etat.send_log(discord.Embed(color=hexc("#ff6600"), title="⚠️ AutoMod — Spam de sanctions", timestamp=now(),
                    description=f"<@{ctx.author.id}> (**{ctx.author}**) a été **kick** pour avoir utilisé des commandes de sanction en rafale.\n**{d['count']} commandes** en moins de {int(ids.SANCTION_WINDOW)}s.\n> Commande déclenchante : `+{ctx.command.name}`"))
            except discord.HTTPException as e:
                logger.error(f"[SANCTION SPAM] {e}")
            raise PermissionRefusee("Spam de sanctions détecté.")

    # ─────────────────────────── Prison ───────────────────────────

    @commands.hybrid_command(name="prison", description="Envoyer un membre en prison (ses rôles sont sauvegardés).",
                             usage="@membre [raison]")
    @app_commands.describe(membre="Le membre à emprisonner", raison="La raison")
    @perm_jail()
    async def prison(self, ctx, membre: discord.Member, *, raison: str = "Non précisé"):
        if not etat.is_owner(ctx.author.id):
            if etat.is_owner(membre.id):
                raise PermissionRefusee("Tu ne peux pas sanctionner le créateur du serveur.")
            if etat.perm_level(membre) >= JUNIOR:
                raise PermissionRefusee("Tu ne peux pas mettre ce membre en prison (hiérarchie).")
        if membre.get_role(ids.PRISON_ROLE_ID):
            return await ctx.reply(embed=err_embed("Ce membre est déjà en prison."))
        try:
            roles = await emprisonner(membre, ctx.author, raison)
        except Exception:
            return await ctx.reply(embed=err_embed("Impossible. Vérifie mes permissions."))
        await dm(membre, discord.Embed(color=hexc("#4a0000"), title="⛓️ Tu as été mis en prison", timestamp=now(),
                                       description=f"**Serveur :** {ctx.guild.name}\n**Raison :** {raison}\n**Modérateur :** {ctx.author}"))
        await ctx.reply(embed=ok_embed(f"<@{membre.id}> a été envoyé en prison. **{len(roles)}** rôle(s) sauvegardé(s).\n**Raison :** {raison}"))

    @commands.hybrid_command(name="liberer", description="Libérer un membre de prison et lui rendre ses rôles.", usage="@membre")
    @niveau(JUNIOR)
    async def liberer(self, ctx, membre: discord.Member):
        saved = await etat.get_prison_roles(membre.id)
        await etat.delete_prison_roles(membre.id)
        valides = [r for r in (ctx.guild.get_role(i) for i in saved) if r and not r.managed and r < ctx.guild.me.top_role]
        etat.prison_release_whitelist.add(membre.id)
        try:
            prison = ctx.guild.get_role(ids.PRISON_ROLE_ID)
            if prison and prison in membre.roles:
                await membre.remove_roles(prison, reason=f"[LIBERER] par {ctx.author}")
            if valides:
                await membre.add_roles(*valides, reason="Restauration rôles après libération")
        except discord.HTTPException:
            etat.prison_release_whitelist.discard(membre.id)
            return await ctx.reply(embed=err_embed("Impossible de restaurer les rôles."))
        asyncio.get_running_loop().call_later(3, etat.prison_release_whitelist.discard, membre.id)
        await send_mod_log("LIBERER", membre, ctx.author, "Libéré de prison")
        await dm(membre, discord.Embed(color=hexc("#22c55e"), title="🔓 Tu as été libéré de prison", timestamp=now(),
                                       description=f"**Serveur :** {ctx.guild.name}\n**Modérateur :** {ctx.author}"))
        await ctx.reply(embed=ok_embed(f"<@{membre.id}> libéré. **{len(valides)}** rôle(s) restauré(s)."))

    @commands.hybrid_command(name="prisonlist", description="Liste des membres en prison.")
    @niveau(JUNIOR)
    async def prisonlist(self, ctx):
        docs = await etat.db.prisonsaves.find({"guildId": str(ctx.guild.id)}).to_list(None)
        if not docs:
            return await ctx.reply(embed=info_embed("Aucun membre actuellement en prison."))
        lignes = []
        for d in docs:
            m = ctx.guild.get_member(int(d["userId"]))
            lignes.append(f"• <@{d['userId']}> (`{m or 'Inconnu (' + d['userId'] + ')'}`) — Raison: {d.get('reason') or 'N/A'} — <t:{etat.ts(d.get('savedAt'))}:R>")
        await ctx.reply(embed=discord.Embed(color=hexc("#4a0000"), title=f"⛓️ Liste des prisonniers — {len(docs)}",
                                            description="\n".join(lignes)[:4096], timestamp=now()))

    # ─────────────────────────── Warns ───────────────────────────

    @commands.hybrid_command(name="warn", description="Avertir un membre (3 = prison auto, 5 = kick auto).", usage="@membre [raison]")
    @niveau(MOD)
    async def warn(self, ctx, membre: discord.Member, *, raison: str = "Non précisé"):
        verifier_cible(ctx, membre)
        count = await etat.add_warn(membre.id, ctx.guild.id, "normal", raison, ctx.author.id)
        await send_mod_log("WARN", membre, ctx.author, raison, count=f"{count} avertissement(s)")
        await dm(membre, discord.Embed(color=hexc("#f59e0b"), title="⚠️ Avertissement reçu", timestamp=now(),
                                       description=f"**Serveur :** {ctx.guild.name}\n**Raison :** {raison}\n**Total warns :** {count}\n**Modérateur :** {ctx.author}"))
        auto = ""
        if count >= 5:
            try:
                await membre.kick(reason="[AUTO] 5 warns accumulés")
                auto = "\n> 🦵 **Kick automatique** (5 warns atteints)"
            except discord.HTTPException:
                pass
        elif count >= 3:
            await etat.save_prison_roles(membre.id, ctx.guild.id, etat.roles_a_sauver(membre), "3 warns accumulés", ctx.author.id)
            try:
                await etat.mettre_en_prison_roles(membre, "[AUTO] 3 warns accumulés")
            except Exception:
                pass
            auto = "\n> ⛓️ **Prison automatique** (3 warns atteints)"
        await ctx.reply(embed=discord.Embed(color=hexc("#f59e0b"), title="⚠️ Avertissement", timestamp=now(),
                                            description=f"**Membre :** <@{membre.id}>\n**Raison :** {raison}\n**Total warns :** **{count}**/5{auto}"))

    @commands.hybrid_command(name="warng", description="Avertissement grave (3 = ban auto).", usage="@membre [raison]")
    @niveau(PA_TEST)
    async def warng(self, ctx, membre: discord.Member, *, raison: str = "Non précisé"):
        verifier_cible(ctx, membre)
        count = await etat.add_warn(membre.id, ctx.guild.id, "grave", raison, ctx.author.id)
        await send_mod_log("WARN_GRAVE", membre, ctx.author, raison, count=f"{count} warn(s) grave(s)")
        await dm(membre, discord.Embed(color=hexc("#ef4444"), title="🚨 Avertissement grave reçu", timestamp=now(),
                                       description=f"**Serveur :** {ctx.guild.name}\n**Raison :** {raison}\n**Total warns graves :** {count}\n**Modérateur :** {ctx.author}"))
        auto = ""
        if count >= 3:
            try:
                await ctx.guild.ban(membre, reason="[AUTO] 3 warns graves accumulés")
                auto = "\n> 🔨 **Ban automatique** (3 warns graves atteints)"
            except discord.HTTPException:
                pass
        await ctx.reply(embed=discord.Embed(color=hexc("#ef4444"), title="🚨 Avertissement grave", timestamp=now(),
                                            description=f"**Membre :** <@{membre.id}>\n**Raison :** {raison}\n**Total warns graves :** **{count}**/3{auto}"))

    @commands.hybrid_command(name="warns", description="Voir le nombre d'avertissements d'un membre.", usage="@membre")
    @niveau(MOD)
    async def warns(self, ctx, membre: discord.Member):
        n = await etat.get_warn_count(membre.id, ctx.guild.id, "normal")
        g = await etat.get_warn_count(membre.id, ctx.guild.id, "grave")
        e = discord.Embed(color=hexc("#f59e0b"), title=f"⚠️ Avertissements — {membre.name}", timestamp=now(),
                          description="> 3 warns légers → prison auto\n> 5 warns légers → kick auto\n> 3 warns graves → ban auto")
        e.set_thumbnail(url=membre.display_avatar.url)
        e.add_field(name="⚠️ Légers", value=f"**{n}**/5", inline=True)
        e.add_field(name="🚨 Graves", value=f"**{g}**/3", inline=True)
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="warnhistory", description="Historique des 10 derniers avertissements.", usage="@membre")
    @niveau(MOD)
    async def warnhistory(self, ctx, membre: discord.Member):
        doc = await etat.get_warn_doc(membre.id, ctx.guild.id)
        warns = (doc or {}).get("warns") or []
        if not warns:
            return await ctx.reply(embed=info_embed(f"Aucun avertissement pour <@{membre.id}>."))
        lignes = [f"**{i + 1}.** {'🚨' if w.get('type') == 'grave' else '⚠️'} {w.get('reason')} — <@{w.get('moderatorId') or 'N/A'}> — <t:{etat.ts(w.get('date'))}:R>"
                  for i, w in enumerate(warns[-10:])]
        e = discord.Embed(color=hexc("#f59e0b"), title=f"📋 Historique des warns — {membre.name}", description="\n".join(lignes), timestamp=now())
        e.set_footer(text=f"Affichage des 10 derniers warns • Total: {len(warns)}")
        await ctx.reply(embed=e)

    @commands.hybrid_command(name="resetwarn", description="Remettre à zéro les avertissements d'un membre.", usage="@membre")
    @niveau(MOD)
    async def resetwarn(self, ctx, membre: discord.Member):
        await etat.reset_warn(membre.id, ctx.guild.id)
        await ctx.reply(embed=ok_embed(f"Tous les avertissements réinitialisés pour <@{membre.id}>."))

    # ─────────────────────────── Mute ───────────────────────────

    @commands.hybrid_command(name="mute", aliases=["tempmute"], description="Rendre muet (timeout). Durée : 10m, 2h, 1d… (max 28j).",
                             usage="@membre [durée] [raison]")
    @app_commands.describe(duree="Ex : 10m, 2h, 1d (vide = 28 jours)")
    @niveau(PA_TEST)
    async def mute(self, ctx, membre: discord.Member, duree: str | None = None, *, raison: str | None = None):
        verifier_cible(ctx, membre, "mute")
        dur = etat.parse_duration(duree) if duree else None
        if duree and dur is None:  # ce n'était pas une durée : ça fait partie de la raison
            raison = f"{duree} {raison or ''}".strip()
        raison = raison or "Non précisé"
        sec = min(dur, MAX_TIMEOUT) if dur else MAX_TIMEOUT
        try:
            await membre.timeout(timedelta(seconds=sec), reason=raison)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de mute ce membre."))
        await etat.db.mutes.update_one({"userId": str(membre.id), "guildId": str(ctx.guild.id)},
            {"$set": {"expiresAt": now() + timedelta(seconds=sec), "reason": raison, "moderatorId": str(ctx.author.id), "mutedAt": now()}}, upsert=True)
        fd = etat.format_duration(dur) if dur else None
        await send_mod_log("MUTE", membre, ctx.author, raison, duration=fd or "Permanent (28j max)")
        await dm(membre, discord.Embed(color=hexc("#f59e0b"), title="🔇 Tu as été mute", timestamp=now(),
            description=f"**Serveur :** {ctx.guild.name}\n**Durée :** {fd or 'Jusqu’à expiration'}\n**Raison :** {raison}\n**Modérateur :** {ctx.author}"))
        await ctx.reply(embed=ok_embed(f"🔇 <@{membre.id}> a été mute.\n**Durée :** {fd or 'Max (28j)'}\n**Raison :** {raison}"))

    @commands.hybrid_command(name="unmute", description="Retirer le mute d'un membre.", usage="@membre")
    @niveau(PA_TEST)
    async def unmute(self, ctx, membre: discord.Member):
        try:
            await membre.timeout(None, reason=f"[UNMUTE] par {ctx.author}")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de retirer le mute."))
        await etat.db.mutes.delete_one({"userId": str(membre.id), "guildId": str(ctx.guild.id)})
        await send_mod_log("UNMUTE", membre, ctx.author, "Unmute manuel")
        await ctx.reply(embed=ok_embed(f"🔊 <@{membre.id}> a été unmute."))

    @commands.hybrid_command(name="mutelist", description="Liste des membres mute.")
    @niveau(PA_TEST)
    async def mutelist(self, ctx):
        mutes = await etat.db.mutes.find({"guildId": str(ctx.guild.id)}).to_list(None)
        if not mutes:
            return await ctx.reply(embed=info_embed("Aucun membre actuellement mute."))
        lignes = []
        for m in mutes:
            expire = f"<t:{etat.ts(m['expiresAt'])}:R>" if m.get("expiresAt") else "N/A"
            lignes.append(f"• <@{m['userId']}> — Expire: {expire} — {m.get('reason')}")
        await ctx.reply(embed=discord.Embed(color=hexc("#f59e0b"), title=f"🔇 Membres mute — {len(mutes)}", description="\n".join(lignes)[:4096], timestamp=now()))

    # ─────────────────────────── Kick / Ban ───────────────────────────

    @commands.hybrid_command(name="kick", description="Expulser un membre.", usage="@membre [raison]")
    @niveau(STAFF)
    async def kick(self, ctx, membre: discord.Member, *, raison: str = "Non précisé"):
        verifier_cible(ctx, membre, "kick")
        await dm(membre, discord.Embed(color=hexc("#f97316"), title="👢 Tu as été kick", timestamp=now(),
                                       description=f"**Serveur :** {ctx.guild.name}\n**Raison :** {raison}\n**Modérateur :** {ctx.author}"))
        try:
            await membre.kick(reason=raison)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de kick ce membre."))
        await send_mod_log("KICK", membre, ctx.author, raison)
        await ctx.reply(embed=ok_embed(f"👢 <@{membre.id}> a été kick.\n**Raison :** {raison}"))

    async def _ban_log(self, uid, guild_id, reason, mod_id):
        await etat.db.banlogs.update_one({"userId": str(uid), "guildId": str(guild_id)},
                                         {"$set": {"reason": reason, "moderatorId": str(mod_id), "bannedAt": now()}}, upsert=True)

    @commands.hybrid_command(name="ban", description="Bannir un membre (ou un ID, même absent du serveur).", usage="@membre|ID [raison]")
    @niveau(SAINT, "Seul le rôle **Saint** peut bannir des membres.")
    async def ban(self, ctx, utilisateur: discord.User, *, raison: str = "Non précisé"):
        membre = ctx.guild.get_member(utilisateur.id)
        if membre:
            verifier_cible(ctx, membre, "bannir")
            await dm(membre, discord.Embed(color=hexc("#ff0000"), title="🔨 Tu as été banni", timestamp=now(),
                                           description=f"**Serveur :** {ctx.guild.name}\n**Raison :** {raison}\n**Modérateur :** {ctx.author}"))
        try:
            await ctx.guild.ban(utilisateur, reason=raison, delete_message_seconds=86400)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de bannir cet utilisateur."))
        await self._ban_log(utilisateur.id, ctx.guild.id, raison, ctx.author.id)
        await send_mod_log("BAN", utilisateur, ctx.author, raison)
        await ctx.reply(embed=ok_embed(f"🔨 <@{utilisateur.id}> a été banni.\n**Raison :** {raison}"))

    @commands.hybrid_command(name="unban", description="Débannir un utilisateur par son ID.", usage="ID")
    @niveau(SAINT, "Seul le rôle **Saint** peut débannir des membres.")
    async def unban(self, ctx, user_id: str):
        if not user_id.isdigit():
            return await ctx.reply(embed=err_embed("Usage : `+unban <id>`"))
        try:
            await ctx.guild.unban(discord.Object(int(user_id)), reason=f"[UNBAN] par {ctx.author}")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de débannir cet utilisateur (vérifie l'ID)."))
        await etat.db.banlogs.delete_one({"userId": user_id, "guildId": str(ctx.guild.id)})
        await send_mod_log("UNBAN", (user_id, user_id), ctx.author, "Déban manuel")
        await ctx.reply(embed=ok_embed(f"✅ `{user_id}` a été débanni."))

    @commands.hybrid_command(name="tempban", description="Bannir temporairement (1d, 12h, 30m…).", usage="@membre <durée> [raison]")
    @niveau(SAINT, "Seul le rôle **Saint** peut bannir des membres.")
    async def tempban(self, ctx, membre: discord.Member, duree: str, *, raison: str = "Non précisé"):
        verifier_cible(ctx, membre, "bannir")
        dur = etat.parse_duration(duree)
        if not dur:
            return await ctx.reply(embed=err_embed("Durée invalide. Ex: `1d`, `12h`, `30m`"))
        fd = etat.format_duration(dur)
        await dm(membre, discord.Embed(color=hexc("#ff0000"), title="🔨 Tu as été temporairement banni", timestamp=now(),
                                       description=f"**Serveur :** {ctx.guild.name}\n**Durée :** {fd}\n**Raison :** {raison}\n**Modérateur :** {ctx.author}"))
        try:
            await ctx.guild.ban(membre, reason=f"[TEMPBAN {fd}] {raison}", delete_message_seconds=86400)
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de bannir ce membre."))
        await send_mod_log("BAN", membre, ctx.author, raison, duration=fd)
        # le débannissement est enregistré en base : il survit aux redémarrages du bot
        await etat.db.tempbans.update_one({"userId": str(membre.id), "guildId": str(ctx.guild.id)},
                                          {"$set": {"unbanAt": now() + timedelta(seconds=dur)}}, upsert=True)
        asyncio.create_task(self._unban_plus_tard(ctx.guild, membre.id, dur, fd))
        await ctx.reply(embed=ok_embed(f"🔨 <@{membre.id}> banni pour **{fd}**.\n**Raison :** {raison}"))

    async def _unban_plus_tard(self, guild, uid, delai, fd="?"):
        await asyncio.sleep(max(0, delai))
        try:
            await guild.unban(discord.Object(uid), reason=f"[TEMPBAN] Expiration après {fd}")
        except discord.HTTPException:
            pass
        await etat.db.tempbans.delete_one({"userId": str(uid), "guildId": str(guild.id)})

    @commands.Cog.listener()
    async def on_ready(self):
        if getattr(self, "_repris", False):
            return
        self._repris = True
        async for d in etat.db.tempbans.find():
            g = self.bot.get_guild(int(d["guildId"]))
            if g:
                fin = d["unbanAt"].replace(tzinfo=now().tzinfo)
                asyncio.create_task(self._unban_plus_tard(g, int(d["userId"]), (fin - now()).total_seconds()))

    @commands.hybrid_command(name="softban", description="Ban + déban immédiat (supprime 7 jours de messages).", usage="@membre [raison]")
    @niveau(SAINT, "Seul le rôle **Saint** peut utiliser le softban.")
    async def softban(self, ctx, membre: discord.Member, *, raison: str = "Softban (suppression messages)"):
        verifier_cible(ctx, membre)
        try:
            await ctx.guild.ban(membre, reason=f"[SOFTBAN] {raison}", delete_message_seconds=604800)
            await ctx.guild.unban(membre, reason="[SOFTBAN] Déban automatique post-softban")
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible d'effectuer le softban."))
        await send_mod_log("KICK", membre, ctx.author, f"Softban — {raison}")
        await ctx.reply(embed=ok_embed(f"🧹 <@{membre.id}> softban — messages supprimés, membre déban automatiquement.\n**Raison :** {raison}"))

    @commands.hybrid_command(name="banlist", description="Liste des membres bannis.")
    @niveau(SAINT)
    async def banlist(self, ctx):
        try:
            bans = [b async for b in ctx.guild.bans(limit=1000)]
        except discord.HTTPException:
            return await ctx.reply(embed=err_embed("Impossible de récupérer la liste des bans."))
        if not bans:
            return await ctx.reply(embed=info_embed("Aucun membre banni."))
        lignes = [f"• `{b.user}` (`{b.user.id}`) — {b.reason or 'Pas de raison'}" for b in bans[:20]]
        e = discord.Embed(color=hexc("#ff0000"), title=f"🔨 Membres bannis — {len(bans)} total", description="\n".join(lignes)[:4096], timestamp=now())
        e.set_footer(text="Affichage des 20 premiers")
        await ctx.reply(embed=e)

    # ─────────────────────────── Menu de sanction ───────────────────────────

    @commands.hybrid_command(name="sanction", description="Menu de sanction complet avec boutons.", usage="@membre")
    @niveau(STAFF)
    async def sanction(self, ctx, membre: discord.Member):
        verifier_cible(ctx, membre)
        n = await etat.get_warn_count(membre.id, ctx.guild.id, "normal")
        g = await etat.get_warn_count(membre.id, ctx.guild.id, "grave")
        e = discord.Embed(color=hexc("#5865F2"), title=f"🛡️ Menu de sanction — {membre.name}", description="Choisissez la sanction à appliquer :", timestamp=now())
        e.set_thumbnail(url=membre.display_avatar.url)
        e.add_field(name="⚠️ Warns légers", value=f"{n}/5", inline=True)
        e.add_field(name="🚨 Warns graves", value=f"{g}/3", inline=True)
        e.add_field(name="⛓️ Prison", value="Oui" if membre.get_role(ids.PRISON_ROLE_ID) else "Non", inline=True)
        owner = etat.is_owner(ctx.author.id)
        await ctx.reply(embed=e, view=Composants(
            bouton(f"sanction_warn_{membre.id}", "Warn", B.secondary, "⚠️", row=0),
            bouton(f"sanction_warng_{membre.id}", "Warn grave", B.danger, "🚨", row=0),
            bouton(f"sanction_mute_{membre.id}", "Mute 1h", B.secondary, "🔇", row=0),
            bouton(f"sanction_prison_{membre.id}", "Prison", B.danger, "⛓️", disabled=not etat.has_perm_jail(ctx.author) and not owner, row=0),
            bouton(f"sanction_kick_{membre.id}", "Kick", B.danger, "👢", row=1),
            bouton(f"sanction_ban_{membre.id}", "Ban", B.danger, "🔨", disabled=not etat.has_min_perm(ctx.author, SAINT), row=1)))

    @commands.Cog.listener()
    async def on_interaction(self, inter: discord.Interaction):
        cid = etat.custom_id(inter)
        if not cid.startswith("sanction_") or inter.guild is None:
            return
        _, action, tid = cid.split("_", 2)
        m = inter.user
        await inter.response.defer(ephemeral=True, thinking=True)
        rep = lambda e: inter.followup.send(embed=e, ephemeral=True)
        if not etat.has_min_perm(m, STAFF) and not etat.is_owner(m.id):
            return await rep(err_embed("Permission refusée."))
        t = inter.guild.get_member(int(tid))
        if t is None:
            return await rep(err_embed("Membre introuvable."))
        if not etat.can_target(m, t):
            return await rep(err_embed("Tu ne peux pas sanctionner ce membre (hiérarchie)."))
        r = "Via menu de sanction"
        try:
            if action == "warn":
                c = await etat.add_warn(t.id, inter.guild.id, "normal", r, m.id)
                await send_mod_log("WARN", t, m, r, count=c)
                await rep(ok_embed(f"⚠️ Warn appliqué à <@{t.id}>. Total: {c}/5"))
            elif action == "warng":
                c = await etat.add_warn(t.id, inter.guild.id, "grave", r, m.id)
                await send_mod_log("WARN_GRAVE", t, m, r, count=c)
                await rep(ok_embed(f"🚨 Warn grave appliqué à <@{t.id}>. Total graves: {c}/3"))
            elif action == "mute":
                await t.timeout(timedelta(hours=1), reason=r)
                await send_mod_log("MUTE", t, m, r, duration="1h")
                await rep(ok_embed(f"🔇 <@{t.id}> mute 1h."))
            elif action == "prison":
                if not etat.has_perm_jail(m) and not etat.is_owner(m.id):
                    return await rep(err_embed("Seuls les membres ayant le rôle **Perm Jail** peuvent envoyer quelqu'un en prison."))
                await emprisonner(t, m, r)
                await rep(ok_embed(f"⛓️ <@{t.id}> envoyé en prison."))
            elif action == "kick":
                await t.kick(reason=r)
                await send_mod_log("KICK", t, m, r)
                await rep(ok_embed(f"👢 <@{t.id}> kick."))
            elif action == "ban":
                if not etat.has_min_perm(m, SAINT):
                    return await rep(err_embed("Seul le rôle **Saint** peut bannir."))
                await inter.guild.ban(t, reason=r, delete_message_seconds=86400)
                await send_mod_log("BAN", t, m, r)
                await rep(ok_embed(f"🔨 <@{t.id}> banni."))
        except (discord.HTTPException, RuntimeError):
            await rep(err_embed("Action impossible (permissions / hiérarchie des rôles du bot)."))

    # ─────────────────────────── Actions de masse ───────────────────────────

    async def _masse(self, ctx, attente, action, fin, pause, filtre):
        await ctx.reply(embed=discord.Embed(color=hexc("#f59e0b"), description=attente))
        n = 0
        for m in list(ctx.guild.members):
            if filtre(m):
                try:
                    await action(m)
                except discord.HTTPException:
                    pass
                n += 1
                await asyncio.sleep(pause)
        await ctx.channel.send(embed=ok_embed(fin.format(n=n)))

    @commands.hybrid_command(name="massmute", description="Mute 1h tous les membres (hors staff).", usage="[raison]")
    @niveau(STAFF)
    async def massmute(self, ctx, *, raison: str = "Massmute"):
        await self._masse(ctx, "⏳ Mute en cours...", lambda m: m.timeout(timedelta(hours=1), reason=raison),
                          "🔇 **{n}** membre(s) mute.", 0.3,
                          lambda m: not m.bot and not etat.has_min_perm(m, JUNIOR) and not m.is_timed_out())

    @commands.hybrid_command(name="massunmute", description="Retirer tous les mutes.")
    @niveau(STAFF)
    async def massunmute(self, ctx):
        await self._masse(ctx, "⏳ Unmute en cours...", lambda m: m.timeout(None, reason=f"[MASSUNMUTE] par {ctx.author}"),
                          "🔊 **{n}** membre(s) unmute.", 0.3, lambda m: not m.bot and m.is_timed_out())

    @commands.hybrid_command(name="masskick", description="Kick tous les membres (hors staff). ⚠️ Dangereux.", usage="[raison]")
    @niveau(SAINT)
    async def masskick(self, ctx, *, raison: str = "Masskick"):
        await self._masse(ctx, "⏳ Kick en cours... (Cela peut prendre du temps)", lambda m: m.kick(reason=raison),
                          "👢 **{n}** membre(s) kick.", 0.5,
                          lambda m: not m.bot and not etat.has_min_perm(m, JUNIOR) and m.id != ids.OWNER_ID)

    @commands.hybrid_command(name="massban", description="Bannir tous les membres (hors staff). ⚠️ Dangereux.", usage="[raison]")
    @niveau(SAINT, "Seul le rôle **Saint** peut utiliser massban.")
    async def massban(self, ctx, *, raison: str = "Massban"):
        await self._masse(ctx, "⏳ Ban en cours... (Cela peut prendre du temps)", lambda m: ctx.guild.ban(m, reason=raison),
                          "🔨 **{n}** membre(s) banni(s).", 0.5,
                          lambda m: not m.bot and not etat.has_min_perm(m, JUNIOR) and m.id != ids.OWNER_ID)


async def setup(bot):
    await bot.add_cog(Sanctions(bot))
