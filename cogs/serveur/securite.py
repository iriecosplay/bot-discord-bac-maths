"""Sécurité (ex irie-bot) : anti-raid via logs d'audit, blacklist, automod
anti-spam, protection de la prison, rôle interdit, logs arrivées/départs,
suivi des invitations, nettoyage du forum d'aide."""
import asyncio
import logging
import time

import discord
from discord.ext import commands, tasks

from noyau import etat, ids
from noyau.etat import hexc, now, send_log

logger = logging.getLogger(__name__)


def tag_equipe(user) -> bool:
    pg = getattr(user, "primary_guild", None)
    return bool(pg and pg.id == ids.MAIN_GUILD_ID and pg.identity_enabled is not False)


class SecuriteCog(commands.Cog, name="Sécurité"):
    def __init__(self, bot):
        self.bot = bot
        self.raid_fast = etat.Fenetre(ids.RAID_FAST_WINDOW)
        self.raid_slow = etat.Fenetre(ids.RAID_SLOW_WINDOW)
        self.bl_ban = etat.Fenetre(ids.BL_BAN_WINDOW)
        self.bl_salon = etat.Fenetre(ids.BL_SALON_WINDOW)
        self.same_chan = etat.Fenetre(ids.SAME_CHAN_WINDOW)
        self.cross_chan = etat.Fenetre(ids.CROSS_MSG_WINDOW)
        self.dup_msg = etat.Fenetre(ids.DUP_MSG_WINDOW)
        self.everyone = etat.Fenetre(ids.EVERYONE_WINDOW)
        self.mentions = etat.Fenetre(ids.MENTION_WINDOW)
        self._pret = False

    async def cog_load(self):
        self.forum_cleanup.start()

    async def cog_unload(self):
        self.forum_cleanup.cancel()

    # ══════════════════════════ ANTI-RAID ══════════════════════════

    async def _apply_sanction(self, member: discord.Member, action_name, window_label, count):
        is_admin = member.guild_permissions.administrator or member.get_role(ids.ADMIN_ROLE_ID) or member.get_role(ids.MOD_ROLE_ID)
        self.raid_fast.delete(member.id)
        self.raid_slow.delete(member.id)
        try:
            if is_admin:
                await member.kick(reason=f'[AUTO-RAID] {count} actions "{action_name}" en {window_label}')
                await send_log(discord.Embed(color=hexc("#ff6600"), title="⚠️ Anti-Raid — Admin/Modo Kick", timestamp=now(),
                    description=f"<@{member.id}> (**{member}**) a été **kick** pour comportement suspect.\n**Action :** {action_name}\n**Détection :** {count} actions en {window_label}\n> ⚠️ Admin/Modo — kick appliqué à la place du ban."))
            else:
                await member.guild.ban(member, reason=f'[AUTO-BAN] {count} actions "{action_name}" en {window_label}')
                await send_log(discord.Embed(color=hexc("#ff0000"), title="🛡️ Anti-Raid — Ban", timestamp=now(),
                    description=f"<@{member.id}> (**{member}**) a été **banni** pour comportement suspect.\n**Action :** {action_name}\n**Détection :** {count} actions en {window_label}"))
        except discord.HTTPException as e:
            logger.error(f"[ANTI-RAID] Échec sanction : {e}")

    async def _track(self, member: discord.Member, action_name):
        uid = member.id
        if uid in (ids.AUTOMOD_IGNORED_BOT_ID, self.bot.user.id, ids.OWNER_ID):
            return
        if member.bot and etat.bots_allowed:
            return
        d = self.raid_fast.get(uid)
        if d is None:
            self.raid_fast.start(uid, count=1)
        else:
            d["count"] += 1
            if d["count"] >= ids.RAID_FAST_THRESHOLD:
                await self._apply_sanction(member, action_name, "3 secondes", d["count"])
                return
        d = self.raid_slow.get(uid)
        if d is None:
            self.raid_slow.start(uid, count=1)
        else:
            d["count"] += 1
            if d["count"] >= ids.RAID_SLOW_THRESHOLD:
                await self._apply_sanction(member, action_name, "5 secondes", d["count"])

    async def _check_blacklist(self, user_id, guild, action):
        if user_id in (ids.AUTOMOD_IGNORED_BOT_ID, ids.OWNER_ID) or user_id not in etat.blacklist:
            return
        member = guild.get_member(user_id)
        if member is None:
            return

        async def ban_bl(reason):
            try:
                await guild.ban(member, reason=f"[BLACKLIST] {reason}", delete_message_seconds=86400)
                await send_log(discord.Embed(color=hexc("#ff0000"), title="⛔ Blacklist — Ban automatique", timestamp=now(),
                    description=f"<@{user_id}> (**{member}**) était en blacklist et a déclenché le seuil.\n**Raison :** {reason}"))
            except discord.HTTPException as e:
                logger.error(f"[BLACKLIST BAN] {e}")

        if action == "bot":
            await ban_bl("Tentative d'ajout de bot par un utilisateur blacklisté")
            return
        fen, seuil, label = ((self.bl_ban, ids.BL_BAN_THRESHOLD, "bans effectués") if action == "ban"
                             else (self.bl_salon, ids.BL_SALON_THRESHOLD, "salons créés"))
        d = fen.get(user_id)
        if d is None:
            fen.start(user_id, count=1)
        else:
            d["count"] += 1
            if d["count"] >= seuil:
                fen.delete(user_id)
                await ban_bl(f"{d['count']} {label} en {int(fen.window)}s")

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        executor_id = entry.user_id
        if not executor_id or executor_id in (self.bot.user.id, ids.AUTOMOD_IGNORED_BOT_ID):
            return
        guild = entry.guild
        executor = guild.get_member(executor_id)
        if executor is None:
            try:
                executor = await guild.fetch_member(executor_id)
            except discord.HTTPException:
                return
        if executor.bot and etat.bots_allowed:
            return
        A = discord.AuditLogAction
        if entry.action == A.ban: await self._check_blacklist(executor_id, guild, "ban")
        if entry.action == A.channel_create: await self._check_blacklist(executor_id, guild, "channel")
        if entry.action == A.bot_add: await self._check_blacklist(executor_id, guild, "bot")
        noms = {
            A.ban: "Ban massif de membre", A.kick: "Kick massif de membre",
            A.channel_create: "Création massive de salon", A.channel_delete: "Suppression massive de salon",
            A.role_create: "Création massive de rôle", A.role_delete: "Suppression massive de rôle",
            A.webhook_create: "Création massive de webhook", A.webhook_delete: "Suppression massive de webhook",
        }
        if entry.action in noms:
            await self._track(executor, noms[entry.action])

    # ══════════════════════════ AUTOMOD MESSAGES ══════════════════════════

    async def scan_message(self, message: discord.Message) -> bool:
        """Anti-spam. Retourne True si l'auteur vient d'être sanctionné.
        Appelé par le cog modération avant de traiter les commandes +."""
        member = message.author if isinstance(message.author, discord.Member) else None
        if member is None:
            return False
        is_owner = etat.is_owner(member.id)
        in_prison = member.get_role(ids.PRISON_ROLE_ID) is not None
        is_bot = member.bot
        staff = etat.has_min_perm(member, 0.5)
        should_scan = not is_owner and not in_prison and ((not is_bot and not staff) or (is_bot and not etat.bots_allowed))
        if not should_scan:
            return False

        uid, cid = member.id, message.channel.id
        state = {"spam": False}

        async def sanctionner(reason, msgs=()):
            if state["spam"]:
                return
            state["spam"] = True
            try:
                for m in msgs:
                    try:
                        await m.delete()
                    except discord.HTTPException:
                        pass
                if is_bot:
                    try:
                        await member.kick(reason=f"[AUTO-MOD] {reason}")
                    except discord.HTTPException:
                        pass
                    await etat.send_mod_log("KICK", member, None, f"AutoMod — {reason}")
                else:
                    await etat.send_to_prison_automod(member, reason, list(msgs))
            except Exception as e:
                logger.error(f"[AUTOMOD] {e}")

        # Même salon (fenêtre glissante sur le dernier message)
        d = self.same_chan.get(uid)
        t = time.monotonic()
        if d is None or t - d["last"] >= ids.SAME_CHAN_WINDOW:
            self.same_chan.start(uid, msgs=[message], last=t)
        else:
            d["msgs"].append(message)
            d["last"] = t
            d["_t0"] = t  # prolonge la fenêtre comme le setTimeout du JS
            if len(d["msgs"]) >= ids.SAME_CHAN_THRESHOLD:
                self.same_chan.delete(uid)
                await sanctionner("Spam massif dans un même salon", d["msgs"])

        if not state["spam"]:
            d = self.cross_chan.get(uid)
            if d is None:
                self.cross_chan.start(uid, chans={cid}, msgs=[message])
            else:
                d["chans"].add(cid)
                d["msgs"].append(message)
                if len(d["chans"]) >= ids.CROSS_MSG_THRESHOLD:
                    self.cross_chan.delete(uid)
                    await sanctionner(f"Spam inter-salons ({ids.CROSS_MSG_THRESHOLD} salons en {int(ids.CROSS_MSG_WINDOW)}s)", d["msgs"])

        if not state["spam"]:
            contenu = message.content.strip().lower()
            if contenu:
                d = self.dup_msg.get(uid)
                if d is None or d["content"] != contenu:
                    self.dup_msg.start(uid, content=contenu, msgs=[message])
                else:
                    d["msgs"].append(message)
                    if len(d["msgs"]) >= ids.DUP_MSG_THRESHOLD:
                        self.dup_msg.delete(uid)
                        await sanctionner(f"Spam de message identique ({ids.DUP_MSG_THRESHOLD}x en {int(ids.DUP_MSG_WINDOW)}s)", d["msgs"])

        if not state["spam"] and ("@everyone" in message.content or "@here" in message.content):
            if not member.guild_permissions.mention_everyone:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                d = self.everyone.get(uid)
                if d is None:
                    self.everyone.start(uid, count=1)
                else:
                    d["count"] += 1
                    if d["count"] >= ids.EVERYONE_THRESHOLD:
                        self.everyone.delete(uid)
                        await sanctionner(f"Spam @everyone/@here sans permission ({d['count']}x en {int(ids.EVERYONE_WINDOW)}s)")

        if not state["spam"]:
            n = len(message.mentions) + len(message.role_mentions)
            if n >= 3:
                d = self.mentions.get(uid)
                if d is None:
                    self.mentions.start(uid, total=n, msgs=[message])
                else:
                    d["total"] += n
                    d["msgs"].append(message)
                    if d["total"] >= ids.MENTION_THRESHOLD:
                        self.mentions.delete(uid)
                        await sanctionner(f"Spam de mentions massives ({d['total']} mentions en {int(ids.MENTION_WINDOW)}s)", d["msgs"])

        return state["spam"]

    # ══════════════════════════ MISE À JOUR MEMBRE ══════════════════════════

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        ajoutes = [r for r in after.roles if r not in before.roles]
        ids_ajoutes = {r.id for r in ajoutes}

        if ids.FORBIDDEN_ROLE_ID in ids_ajoutes:
            try:
                await after.remove_roles(discord.Object(ids.FORBIDDEN_ROLE_ID), reason="[AUTO] Rôle interdit retiré automatiquement")
            except discord.HTTPException:
                pass

        if after.get_role(ids.PRISON_ROLE_ID) is None or after.id in etat.prison_release_whitelist:
            return
        illegaux = [r for r in ajoutes if r.id not in (ids.PRISON_ROLE_ID, after.guild.id) and not r.managed]
        if not illegaux:
            return
        try:
            await etat.mettre_en_prison_roles(after, "[AUTO-PRISON] Tentative d'obtenir des rôles en prison")
            await send_log(discord.Embed(color=hexc("#7c0000"), title="🔒 Prison — Tentative de contournement", timestamp=now(),
                description=f"<@{after.id}> ({after}) a tenté d'obtenir des rôles alors qu'il est en prison.\n**Rôles bloqués :** {', '.join(r.name for r in illegaux)}\n> Les rôles ont été retirés automatiquement."))
        except Exception as e:
            logger.error(f"[PRISON] {e}")

    # ══════════════════════════ INVITATIONS ══════════════════════════

    async def refresh_invite_cache(self, guild):
        try:
            invites = await guild.invites()
            etat.invite_cache[guild.id] = {i.code: {"uses": i.uses or 0, "inviter": i.inviter.id if i.inviter else None} for i in invites}
        except discord.HTTPException as e:
            logger.error(f"[INVITE CACHE] {e}")

    async def find_used_invite(self, guild):
        try:
            old = etat.invite_cache.get(guild.id, {})
            invites = await guild.invites()
            new = {i.code: {"uses": i.uses or 0, "inviter": i.inviter.id if i.inviter else None} for i in invites}
            used = None
            for code, data in new.items():
                o = old.get(code)
                if o is None or data["uses"] > o["uses"]:
                    used = (code, data["inviter"])
                    break
            etat.invite_cache[guild.id] = new
            return used or (None, None)
        except discord.HTTPException:
            return None, None

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild:
            etat.invite_cache.setdefault(invite.guild.id, {})[invite.code] = {
                "uses": invite.uses or 0, "inviter": invite.inviter.id if invite.inviter else None}

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild:
            etat.invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    # ══════════════════════════ ARRIVÉES / DÉPARTS ══════════════════════════

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            e = discord.Embed(color=hexc("#f59e0b"), title="🤖 Nouveau bot sur le serveur", timestamp=now(),
                              description=f"**Bot :** <@{member.id}> (`{member}`)\n**ID :** `{member.id}`\n**Serveur :** {member.guild.name}")
            e.set_thumbnail(url=member.display_avatar.url)
            try:
                owner = await self.bot.fetch_user(ids.OWNER_ID)
                await owner.send(embed=e)
            except discord.HTTPException:
                pass
            await send_log(e)
            return

        code, inviter = await self.find_used_invite(member.guild)
        inviter_txt = "`Lien inconnu`"
        if code:
            inviter_txt = f"<@{inviter}> (`{code}`)" if inviter else f"`{code}`"

        uv = member.guild.get_role(ids.UNVERIFIED_ROLE_ID)
        if uv:
            try:
                await member.add_roles(uv)
            except discord.HTTPException:
                pass

        if member.id in etat.blacklist:
            e = discord.Embed(color=hexc("#ff0000"), title="⛔ Utilisateur blacklist a rejoint", timestamp=now(),
                              description=f"**Membre :** <@{member.id}> (`{member}`)\n**ID :** `{member.id}`\n**Invité par :** {inviter_txt}\n\n> Cet utilisateur est sous surveillance (`+listbl` pour la raison).")
            e.set_thumbnail(url=member.display_avatar.url)
            await send_log(e)

        e = discord.Embed(color=hexc("#22c55e"), title="📥 Nouveau membre", timestamp=now(),
                          description=f"**Membre :** <@{member.id}> (`{member}`)\n**ID :** `{member.id}`\n**Compte créé :** <t:{etat.ts(member.created_at)}:R>\n**Invité par :** {inviter_txt}")
        e.set_thumbnail(url=member.display_avatar.url)
        await send_log(e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        e = discord.Embed(color=hexc("#ef4444"), title="📤 Membre parti", timestamp=now(),
                          description=f"**Membre :** <@{member.id}> (`{member}`)\n**ID :** `{member.id}`")
        e.set_thumbnail(url=member.display_avatar.url)
        await send_log(e)

    # ══════════════════════════ FORUM D'AIDE ══════════════════════════

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.parent_id != ids.FORUM_CHANNEL_ID:
            return
        try:
            owner = thread.guild.get_member(thread.owner_id)
            desc = f"📚 <@{thread.owner_id}> a besoin d'aide !"
            if owner and any(owner.get_role(rid) for rid in ids.CLASS_TO_HELPER):
                desc = f"📚 <@{thread.owner_id}> a besoin d'aide ! Un helper de sa classe est disponible ?"
            await asyncio.sleep(1)  # le 1er message du post doit exister avant qu'on réponde
            await thread.send(embed=discord.Embed(color=hexc("#5865F2"), description=desc, timestamp=now()))
        except discord.HTTPException as e:
            logger.error(f"[FORUM] ThreadCreate : {e}")

    @tasks.loop(hours=1)
    async def forum_cleanup(self):
        guild = self.bot.get_guild(ids.MAIN_GUILD_ID)
        forum = guild.get_channel(ids.FORUM_CHANNEL_ID) if guild else None
        if not isinstance(forum, discord.ForumChannel):
            return
        limite = 4 * 24 * 3600
        maintenant = now()

        async def derniere_activite(th):
            last = th.created_at or maintenant
            try:
                async for m in th.history(limit=1):
                    last = m.created_at
            except discord.HTTPException:
                pass
            return (maintenant - last).total_seconds()

        try:
            for th in list(forum.threads)[:200]:
                if not th.archived and await derniere_activite(th) >= limite:
                    try:
                        await th.edit(archived=True, reason="Inactivité 3 jours")
                    except discord.HTTPException:
                        pass
                await asyncio.sleep(0.5)
            n = 0
            async for th in forum.archived_threads(limit=100):
                n += 1
                if n > 200:
                    break
                if await derniere_activite(th) >= limite:
                    try:
                        await th.delete(reason="Suppression auto 3 jours")
                    except discord.HTTPException:
                        pass
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"[FORUM] Nettoyage : {e}")

    @forum_cleanup.before_loop
    async def _avant_forum(self):
        await self.bot.wait_until_ready()

    # ══════════════════════════ DÉMARRAGE ══════════════════════════

    @commands.Cog.listener()
    async def on_ready(self):
        if self._pret:
            return
        self._pret = True
        guild = self.bot.get_guild(ids.MAIN_GUILD_ID)
        if guild is None:
            return
        await self.refresh_invite_cache(guild)

        # Rôle interdit retiré au démarrage
        forbidden = guild.get_role(ids.FORBIDDEN_ROLE_ID)
        if forbidden:
            for m in list(forbidden.members):
                try:
                    await m.remove_roles(forbidden, reason="[AUTO] Rôle interdit retiré au démarrage")
                except discord.HTTPException:
                    pass

        # Restrictions du salon prison
        prison = guild.get_role(ids.PRISON_ROLE_ID)
        if prison:
            for ch in guild.channels:
                if isinstance(ch, discord.TextChannel) and ch.id != ids.PRISON_CHANNEL_ID:
                    ow = ch.overwrites_for(prison)
                    if ow.view_channel is False and ow.send_messages is False:
                        continue
                    try:
                        await ch.set_permissions(prison, view_channel=False, send_messages=False, reason="[AUTO-PRISON] Restriction salon prison")
                    except discord.HTTPException:
                        pass
            pch = guild.get_channel(ids.PRISON_CHANNEL_ID)
            if pch:
                try:
                    await pch.set_permissions(prison, view_channel=True, send_messages=True, reason="[AUTO-PRISON] Accès salon prison")
                except discord.HTTPException:
                    pass
        logger.info("[SECURITE] prêt")


async def setup(bot):
    await bot.add_cog(SecuriteCog(bot))
