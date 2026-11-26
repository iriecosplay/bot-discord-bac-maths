"""Panneaux du serveur (ex irie-bot) postés automatiquement au démarrage et
gestion de leurs boutons/menus : couleurs, réseaux, tickets, dons, classes,
visibilité, tag du serveur (rôle CM), reaction roles, salon vocal de stats,
rôle Perm Jail, catégorie Discussion Privée, rôles du supérieur."""
import asyncio
import logging

import discord
from discord.ext import commands, tasks

from noyau import etat, ids
from noyau.etat import (Composants, bouton, err_embed, get_chan, hexc, lien, now, ok_embed,
                       supprimer_anciens_panneaux, deja_poste)
from cogs.serveur.securite import tag_equipe

logger = logging.getLogger(__name__)
B = discord.ButtonStyle


def build_reaction_role_message(texte, role):
    e = discord.Embed(color=role.color if role and role.color.value else hexc("#5865F2"), description=texte, timestamp=now())
    e.set_footer(text=f"Clique sur le bouton ci-dessous pour obtenir le rôle @{role.name}")
    v = Composants(bouton(f"reactionrole_claim_{role.id}", f"Obtenir le rôle @{role.name}", B.success, "✅"))
    return {"embed": e, "view": v}


class PanneauxServeurCog(commands.Cog, name="Panneaux"):
    def __init__(self, bot):
        self.bot = bot
        self._pret = False

    async def cog_unload(self):
        self.stats_loop.cancel()

    # ══════════════════════ DÉMARRAGE ══════════════════════

    @commands.Cog.listener()
    async def on_ready(self):
        if self._pret:
            return
        self._pret = True
        guild = self.bot.get_guild(ids.MAIN_GUILD_ID)
        if guild is None:
            logger.warning("Serveur principal introuvable")
            return
        for etape in (self._perm_jail, self._categorie_privee, self._stats_vocal, self._roles_sup,
                      self._tag_cm_demarrage, self._reaction_roles, self._panneau_couleurs, self._panneau_liens,
                      self._panneau_tickets, self._panneau_dons, self._panneau_classes, self._panneau_visibilite,
                      self._panneau_tag):
            try:
                await etape(guild)
            except Exception as e:
                logger.exception(f"[PANNEAUX] {etape.__name__} : {e}")

    async def _perm_jail(self, guild):
        role = discord.utils.get(guild.roles, name="Perm Jail")
        if role is None:
            role = await guild.create_role(name="Perm Jail", color=hexc("#4a0000"),
                                           reason="[AUTO] Rôle Perm Jail — seul rôle autorisé à utiliser +prison")
        etat.perm_jail_role_id = role.id

    async def _categorie_privee(self, guild):
        cat = discord.utils.get(guild.categories, name="Discussion Privée")
        if cat is None:
            parent = guild.get_channel(ids.DISCUSSION_CATEGORY_ID)
            ow = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
            for rid in ids.PRIVATE_ACCESS_ROLE_IDS:
                r = guild.get_role(rid)
                if r:
                    ow[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True, read_message_history=True)
            cat = await guild.create_category("Discussion Privée", overwrites=ow,
                                              position=(parent.position + 1) if parent else None,
                                              reason="[AUTO] Catégorie Discussion Privée créée automatiquement")
        etat.private_category_id = cat.id
        async for doc in etat.db.privatediscussions.find({"guildId": str(guild.id)}):
            data = {"guildId": guild.id, "textChannelId": int(doc["textChannelId"]),
                    "voiceChannelId": int(doc["voiceChannelId"]) if doc.get("voiceChannelId") else None,
                    "leaderId": int(doc["leaderId"]), "memberIds": [int(x) for x in doc.get("memberIds", [])]}
            etat.private_discussions[data["textChannelId"]] = data
            if data["voiceChannelId"]:
                etat.private_discussions[data["voiceChannelId"]] = data

    # ── Salon vocal de stats ──
    def _stats_nom(self, guild):
        humains = [m for m in guild.members if not m.bot]
        en_ligne = [m for m in humains if m.status != discord.Status.offline]
        return f"👥 {len(humains)} • 🟢 {len(en_ligne)}"

    async def _stats_vocal(self, guild):
        ch = next((c for c in guild.voice_channels if c.category_id == ids.STATS_CATEGORY_ID
                   and ("membre" in c.name or c.name.startswith("👥"))), None)
        if ch is None:
            cat = guild.get_channel(ids.STATS_CATEGORY_ID)
            ow = {guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=False),
                  guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)}
            admin = guild.get_role(ids.ADMIN_ROLE_ID)
            if admin:
                ow[admin] = discord.PermissionOverwrite(view_channel=True, connect=True)
            ch = await guild.create_voice_channel(self._stats_nom(guild), category=cat, overwrites=ow,
                                                  reason="[AUTO] Salon vocal stats du serveur")
        else:
            try:
                await ch.edit(name=self._stats_nom(guild))
            except discord.HTTPException:
                pass
        etat.stats_voice_channel_id = ch.id
        await self._connexion_vocal(guild)
        if not self.stats_loop.is_running():
            self.stats_loop.start()

    async def _connexion_vocal(self, guild):
        ch = guild.get_channel(etat.stats_voice_channel_id or 0)
        if ch is None:
            return
        vc = guild.voice_client
        if vc and vc.is_connected():
            return
        try:
            await ch.connect(self_deaf=True, self_mute=True, reconnect=True)
            logger.info("[STATS VOC] ✅ Bot connecté au salon vocal stats.")
        except Exception as e:
            logger.warning(f"[STATS VOC] Connexion vocale impossible : {e}")

    @tasks.loop(minutes=10)
    async def stats_loop(self):
        guild = self.bot.get_guild(ids.MAIN_GUILD_ID)
        ch = guild.get_channel(etat.stats_voice_channel_id or 0) if guild else None
        if ch:
            try:
                await ch.edit(name=self._stats_nom(guild), reason="Mise à jour stats serveur")
            except discord.HTTPException as e:
                logger.error(f"[STATS VOC] {e}")
            await self._connexion_vocal(guild)

    # ── Rôles du supérieur ──
    async def _roles_sup(self, guild):
        member_role = guild.get_role(ids.MEMBER_ROLE_ID)
        for cfg in ids.SUP_ROLES_CONFIG:
            role = discord.utils.get(guild.roles, name=cfg["name"])
            if role is None:
                try:
                    role = await guild.create_role(name=cfg["name"], color=hexc("#5865F2"), reason=f"Rôle supérieur automatique — {cfg['name']}")
                    if member_role:
                        await role.edit(position=member_role.position + 1)
                except discord.HTTPException:
                    continue
            etat.dynamic_role_ids[cfg["name"]] = role.id
        import re
        for cfg in ids.SUP_VISIBILITY_ROLES_CONFIG:
            nom = "vis-" + re.sub(r"[^a-z0-9]", "-", cfg["name"].lower())
            role = discord.utils.get(guild.roles, name=nom)
            if role is None:
                try:
                    role = await guild.create_role(name=nom, color=hexc("#99AAB5"), reason=f"Rôle visibilité automatique — {cfg['name']}")
                except discord.HTTPException:
                    continue
            etat.dynamic_visibility_ids[cfg["dynamic_key"]] = role.id

    async def _tag_cm_demarrage(self, guild):
        cm = guild.get_role(ids.CM_ROLE_ID)
        if cm is None:
            return
        for m in guild.members:
            if not m.bot and tag_equipe(m) and cm not in m.roles:
                try:
                    await m.add_roles(cm, reason="[AUTO] Tag du serveur détecté")
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)

    async def _reaction_roles(self, guild):
        async for doc in etat.db.reactionroles.find({"guildId": str(guild.id)}):
            ch = guild.get_channel(int(doc["channelId"]))
            if ch is None:
                continue
            mid = int(doc["messageId"])
            existe = True
            try:
                msg = await ch.fetch_message(mid)
                existe = msg.author.id == self.bot.user.id
                if not existe:
                    await msg.delete()  # posté par l'ancien bot : boutons morts → on remplace
            except discord.NotFound:
                existe = False
            except discord.HTTPException:
                continue
            role = guild.get_role(int(doc["roleId"]))
            if role is None:
                await etat.db.reactionroles.delete_one({"messageId": doc["messageId"]})
                etat.reaction_roles.pop(mid, None)
                continue
            if existe:
                continue
            sent = await ch.send(**build_reaction_role_message(doc["texte"], role))
            await etat.db.reactionroles.update_one({"_id": doc["_id"]}, {"$set": {"messageId": str(sent.id)}})
            data = etat.reaction_roles.pop(mid, None) or {"roleId": role.id, "channelId": ch.id, "guildId": guild.id, "texte": doc["texte"]}
            etat.reaction_roles[sent.id] = data

    # ── Panneaux ──
    async def _panneau_couleurs(self, guild):
        ch = await get_chan(ids.COLOR_CHANNEL_ID)
        if ch is None:
            return
        member_role = guild.get_role(ids.MEMBER_ROLE_ID)
        for c in ids.COLORS:
            if discord.utils.get(guild.roles, name=c["name"]) is None:
                try:
                    r = await guild.create_role(name=c["name"], color=discord.Color(c["hex"]), reason="Rôle couleur")
                    if member_role:
                        await r.edit(position=member_role.position + 1)
                except discord.HTTPException:
                    pass
        await supprimer_anciens_panneaux(ch)
        if await deja_poste(ch):
            return
        items = [bouton(f"color_{c['name']}", c["name"], B.secondary, c["emoji"], row=i // 5) for i, c in enumerate(ids.COLORS)]
        items.append(bouton("color_remove", "Retirer ma couleur", B.danger, "❌", row=len(ids.COLORS) // 5))
        e = discord.Embed(color=hexc("#5865F2"), title="🎨 Choisis la couleur de ton pseudo", timestamp=now(),
                          description="> Choisis la couleur qui te correspond en cliquant sur un bouton ci-dessous.")
        e.set_footer(text="Tu peux changer ou retirer ta couleur à tout moment.")
        await ch.send(embed=e, view=Composants(*items))

    async def _panneau_liens(self, guild):
        ch = await get_chan(ids.LINKS_CHANNEL_ID)
        if ch is None:
            return
        await supprimer_anciens_panneaux(ch)
        if await deja_poste(ch):
            return
        e = discord.Embed(color=hexc("#ffffff"), description="**Retrouve-moi sur les réseaux ↓**")
        e.set_image(url=ids.BANNER)
        await ch.send(embed=e, view=Composants(lien("TikTok", "https://www.tiktok.com/@mathematic_tok", "🎵"),
                                               lien("Instagram", "https://www.instagram.com/mathematic_tok", "📸")))

    async def _panneau_tickets(self, guild):
        ch = await get_chan(ids.TICKET_PANEL_CHANNEL_ID)
        if ch is None:
            return
        await supprimer_anciens_panneaux(ch)
        if await deja_poste(ch):
            return
        e1 = discord.Embed(color=hexc("#5865F2"), title="🎫 Support — Contacter le staff", timestamp=now(),
                           description="**Besoin d'aide ou tu as une question ?**\n\n> Clique sur le bouton ci-dessous pour ouvrir un ticket privé avec le **staff**.\n\n⚠️ **Un seul ticket à la fois par personne.**")
        e1.set_footer(text="Décris ton problème dès l'ouverture du ticket.")
        await ch.send(embed=e1, view=Composants(bouton("ticket_open", "Contacter le staff", B.primary, "🎫")))
        e2 = discord.Embed(color=hexc("#f5a623"), title="🌟 Community Manager — Devenir CM", timestamp=now(),
                           description="**Tu souhaites rejoindre l'équipe en tant que Community Manager ?**\n\n> Clique sur le bouton ci-dessous pour ouvrir une candidature privée.\n\n⚠️ **Un seul ticket à la fois par personne.**")
        e2.set_footer(text="Présente-toi et explique ta motivation dès l'ouverture.")
        await ch.send(embed=e2, view=Composants(bouton("ticket_open_cm", "Candidater CM", B.success, "🌟")))

    async def _panneau_dons(self, guild):
        ch = await get_chan(ids.DONATE_CHANNEL_ID)
        if ch is None:
            return
        await supprimer_anciens_panneaux(ch)
        if await deja_poste(ch):
            return
        e = discord.Embed(color=hexc("#f5c518"), description="## 💛 Soutenir le serveur\nCe serveur est entièrement gratuit.\n\n💛 Don → rôle **Donateur**\n👑 30€+ → rôle **VIP**")
        e.set_image(url=ids.BANNER)
        await ch.send(embed=e, view=Composants(lien("Faire un don via PayPal", "https://paypal.me/iriecosplay", "💸")))

    async def _panneau_classes(self, guild):
        ch = await get_chan(ids.ROLES_CHANNEL_ID)
        if ch is None:
            return
        # Comme l'ancien bot : on vide entièrement le salon puis on reposte le menu.
        try:
            await ch.purge(limit=None, bulk=True, reason="Republication du menu des classes")
        except discord.HTTPException:
            async for m in ch.history(limit=200):
                try:
                    await m.delete()
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.5)
        roles = etat.get_classe_roles()

        def sel(rs, cid, ph):
            return discord.ui.Select(custom_id=cid, placeholder=ph, options=[
                discord.SelectOption(label=r["label"], value=str(r["id"]), emoji=r["emoji"]) for r in rs])

        g1 = [r for r in roles if r["id"] in ids.GROUPE1_IDS]
        g2 = [r for r in roles if r["id"] in ids.GROUPE2_IDS]
        sup_labels = {c["name"] for c in ids.SUP_ROLES_CONFIG}
        g3 = [r for r in roles if r["id"] == ids.SUP_GENERIQUE_ID or (r["label"] in sup_labels and isinstance(r["id"], int) and r["id"] not in ids.GROUPE1_IDS)]
        items = [sel(g1, "classe_select_1", "📐 Collège / Lycée Général")]
        if g2: items.append(sel(g2, "classe_select_2", "🔧 Lycée Techno & Bac Pro"))
        if g3: items.append(sel(g3, "classe_select_3", "🎓 Supérieur (Prépa / BTS / Licence / Ingé…)"))
        e = discord.Embed(color=hexc("#5865F2"), title="🎓 Choisis ta filière", timestamp=now(),
            description="**Sélectionne ta classe dans le menu correspondant à ta filière.**\n\n> Cela te donnera accès aux salons adaptés à ton niveau.\n> N'oublie pas ensuite d'aller dans le salon **visibilité** pour affiner les salons affichés.\n\n─────────────────────────────\n📐 **Collège & Lycée Général** — 4ème → Terminale\n🔧 **Lycée Techno & Bac Pro** — STI2D, STL, STMG, Bac Pro\n🎓 **Supérieur** — Prépa, BTS, Licence, École d'ingé\n─────────────────────────────\n\n⚠️ Sélectionner une classe **déjà attribuée** te **retire** le rôle.\n⚠️ Un seul rôle de classe à la fois.")
        e.set_footer(text="Tu peux changer de classe à tout moment.")
        await ch.send(embed=e, view=Composants(*items))

    async def _panneau_visibilite(self, guild):
        ch = await get_chan(ids.VISIBILITY_CHANNEL_ID)
        if ch is None:
            return
        await supprimer_anciens_panneaux(ch)
        if await deja_poste(ch):
            return
        vis = etat.get_visibility_roles()
        e = discord.Embed(color=hexc("#5865F2"), title="👁️ Quels salons veux-tu voir ?", timestamp=now(),
            description="**Choisis les niveaux dont tu veux voir les salons de cours.**\n\n> Tu peux en sélectionner **plusieurs à la fois**.\n> Sélectionner un niveau **déjà actif** te **retire** l'accès.\n\n"
                        + "\n".join(f"{r['emoji']} **{r['label']}** — {r['description']}" for r in vis))
        e.set_footer(text="Tu peux modifier ta sélection à tout moment.")
        sel = discord.ui.Select(custom_id="visibility_select", placeholder="📂 Sélectionne un ou plusieurs niveaux…",
                                min_values=1, max_values=len(vis), options=[
                discord.SelectOption(label=r["label"], value=str(r["id"]), emoji=r["emoji"], description=r["description"][:100]) for r in vis])
        await ch.send(embed=e, view=Composants(sel))

    async def _panneau_tag(self, guild):
        ch = await get_chan(ids.TAG_CHANNEL_ID)
        if ch is None:
            return
        await supprimer_anciens_panneaux(ch)
        if await deja_poste(ch):
            return
        e = discord.Embed(color=hexc("#5865F2"), title="🏷️ Tag du serveur",
                          description="Tu as équipé le tag du serveur sur ton profil Discord ?\nClique sur le bouton ci-dessous pour recevoir le rôle automatiquement.")
        await ch.send(embed=e, view=Composants(bouton("claim_cm_tag", "J'ai le tag du serveur", B.primary, "🏷️")))

    # ══════════════════════ TAG DU SERVEUR (rôle CM) ══════════════════════

    async def _sync_tag(self, user, member):
        if member is None or member.bot:
            return
        cm = member.guild.get_role(ids.CM_ROLE_ID)
        if cm is None:
            return
        a_tag, a_role = tag_equipe(user), cm in member.roles
        try:
            if a_tag and not a_role:
                await member.add_roles(cm, reason="[AUTO] Tag du serveur détecté")
            elif not a_tag and a_role:
                await member.remove_roles(cm, reason="[AUTO] Tag du serveur retiré")
        except discord.HTTPException as e:
            logger.error(f"[TAG] {e}")

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        guild = self.bot.get_guild(ids.MAIN_GUILD_ID)
        if guild:
            await self._sync_tag(after, guild.get_member(after.id))

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if after.guild.id == ids.MAIN_GUILD_ID:
            await self._sync_tag(after, after)

    # ══════════════════════ INTERACTIONS ══════════════════════

    @commands.Cog.listener()
    async def on_interaction(self, inter: discord.Interaction):
        cid = etat.custom_id(inter)
        if not cid or inter.guild is None:
            return
        try:
            if cid in ("classe_select_1", "classe_select_2", "classe_select_3"):
                await self._classe(inter)
            elif cid == "visibility_select":
                await self._visibilite(inter)
            elif cid.startswith("reactionrole_claim_"):
                await self._toggle_role(inter, int(cid.removeprefix("reactionrole_claim_")), "[REACTION ROLE]",
                                        "✅ Rôle **@{n}** retiré.", "🎉 Rôle **@{n}** attribué !")
            elif cid.startswith("color_"):
                await self._couleur(inter, cid.removeprefix("color_"))
            elif cid == "helper_all":
                await self._helper_all(inter)
            elif cid.startswith("helper_"):
                await self._toggle_role(inter, int(cid.removeprefix("helper_")), None,
                                        "✅ Rôle **{n}** retiré.", "🎉 Tu es maintenant helper pour **{n}** !")
            elif cid == "be_helped":
                await self._toggle_role(inter, ids.NEED_HELP_ROLE_ID, None, "✅ Rôle d'aide retiré.", "🙋 Rôle attribué !")
            elif cid == "notif_yes":
                role = inter.guild.get_role(ids.NOTIF_ROLE_ID)
                if role is None:
                    return await inter.response.send_message("❌ Rôle introuvable.", ephemeral=True)
                if role in inter.user.roles:
                    return await inter.response.send_message("✅ Tu as déjà les notifications.", ephemeral=True)
                await inter.user.add_roles(role)
                await inter.response.send_message("🔔 Notifications activées !", ephemeral=True)
            elif cid == "notif_no":
                await inter.response.send_message("👍 Aucun problème !", ephemeral=True)
            elif cid == "claim_cm_tag":
                await self._claim_tag(inter)
        except discord.HTTPException as e:
            logger.error(f"[PANNEAUX] interaction {cid} : {e}")
            if not inter.response.is_done():
                await inter.response.send_message("❌ Une erreur est survenue.", ephemeral=True)

    async def _classe(self, inter):
        selected = int(etat.valeurs_select(inter)[0])
        member, guild = inter.user, inter.guild
        await inter.response.defer(ephemeral=True, thinking=True)
        if member.get_role(ids.PRISON_ROLE_ID):
            try:
                await etat.mettre_en_prison_roles(member, "[AUTO-PRISON] Tentative de sélection de rôle en prison")
            except Exception:
                pass
            return await inter.followup.send(embed=err_embed("Tu es actuellement en prison et ne peux pas obtenir de rôles."), ephemeral=True)
        all_ids = etat.all_classe_role_ids()
        a_retirer = [r for r in member.roles if r.id in all_ids and r.id != selected and not r.managed]
        if a_retirer:
            await member.remove_roles(*a_retirer)
        info = next((c for c in etat.get_classe_roles() if c["id"] == selected), None)
        label = info["label"] if info else "classe"
        role = guild.get_role(selected)
        member_role = guild.get_role(ids.MEMBER_ROLE_ID)
        if member.get_role(selected):
            if role:
                await member.remove_roles(role)
            if member_role and member_role in member.roles:
                await member.remove_roles(member_role)
            return await inter.followup.send(f"✅ Rôle **{label}** retiré.", ephemeral=True)
        if role:
            await member.add_roles(role)
        premiere = member_role is not None and member_role not in member.roles
        if premiere:
            await member.add_roles(member_role)
        await inter.followup.send(
            f"🎉 Rôle **{label}** attribué ! Bienvenue !" if premiere else f"🎉 Rôle **{label}** attribué !",
            embed=discord.Embed(color=hexc("#5865F2"), description=f"👋 N'oublie pas d'aller dans <#{ids.VISIBILITY_CHANNEL_ID}> pour choisir quels salons tu souhaites voir !"),
            ephemeral=True)

    async def _visibilite(self, inter):
        member, guild = inter.user, inter.guild
        await inter.response.defer(ephemeral=True, thinking=True)
        if member.get_role(ids.PRISON_ROLE_ID):
            return await inter.followup.send(embed=err_embed("Tu es actuellement en prison et ne peux pas modifier ta visibilité."), ephemeral=True)
        vis = {r["id"]: r for r in etat.get_visibility_roles()}
        ajout, retrait = [], []
        for v in etat.valeurs_select(inter):
            role = guild.get_role(int(v))
            if role is None or role.managed:
                continue
            info = vis.get(role.id, {"emoji": "", "label": role.name})
            txt = f"{info['emoji']} **{info['label']}**"
            if role in member.roles:
                await member.remove_roles(role); retrait.append(txt)
            else:
                await member.add_roles(role); ajout.append(txt)
        lignes = []
        if ajout: lignes.append("✅ **Accès activé :**\n" + "\n".join(ajout))
        if retrait: lignes.append("🚫 **Accès retiré :**\n" + "\n".join(retrait))
        await inter.followup.send("\n\n".join(lignes) or "⚠️ Aucune modification.", ephemeral=True)

    async def _toggle_role(self, inter, role_id, reason, msg_retire, msg_ajout):
        role = inter.guild.get_role(role_id)
        if role is None:
            return await inter.response.send_message("❌ Rôle introuvable.", ephemeral=True)
        if role in inter.user.roles:
            await inter.user.remove_roles(role, reason=reason and f"{reason} Retrait via bouton")
            return await inter.response.send_message(msg_retire.format(n=role.name), ephemeral=True)
        await inter.user.add_roles(role, reason=reason and f"{reason} Attribution via bouton")
        await inter.response.send_message(msg_ajout.format(n=role.name), ephemeral=True)

    async def _couleur(self, inter, action):
        noms = {c["name"] for c in ids.COLORS}
        a_retirer = [r for r in inter.user.roles if r.name in noms and r.name != action]
        if a_retirer:
            await inter.user.remove_roles(*a_retirer)
        if action == "remove":
            return await inter.response.send_message("✅ Ta couleur a bien été retirée.", ephemeral=True)
        role = discord.utils.get(inter.guild.roles, name=action)
        if role is None:
            return await inter.response.send_message("❌ Ce rôle de couleur est introuvable.", ephemeral=True)
        if role in inter.user.roles:
            return await inter.response.send_message(f"Tu possèdes déjà la couleur **{action}**.", ephemeral=True)
        await inter.user.add_roles(role)
        await inter.response.send_message(f"🎨 Couleur changée en **{action}** !", ephemeral=True)

    async def _helper_all(self, inter):
        roles = [r for r in (inter.guild.get_role(i) for i in ids.ALL_HELPER_IDS) if r]
        if all(r in inter.user.roles for r in roles):
            await inter.user.remove_roles(*roles)
            return await inter.response.send_message("✅ Tous les rôles helper retirés.", ephemeral=True)
        await inter.user.add_roles(*[r for r in roles if r not in inter.user.roles])
        await inter.response.send_message("🌟 Tu es maintenant helper pour **toutes classes** !", ephemeral=True)

    async def _claim_tag(self, inter):
        await inter.response.defer(ephemeral=True, thinking=True)
        user = inter.user
        try:
            user = await self.bot.fetch_user(inter.user.id)  # profil à jour (tag)
        except discord.HTTPException:
            pass
        if not tag_equipe(user):
            return await inter.followup.send(embed=err_embed("Tag du serveur non détecté sur ton profil. Équipe-le d'abord puis réessaie."), ephemeral=True)
        cm = inter.guild.get_role(ids.CM_ROLE_ID)
        if cm is None:
            return await inter.followup.send(embed=err_embed("Rôle introuvable."), ephemeral=True)
        if cm in inter.user.roles:
            return await inter.followup.send(embed=ok_embed("Tu as déjà le rôle CM !"), ephemeral=True)
        try:
            await inter.user.add_roles(cm, reason="[AUTO] Tag du serveur vérifié via bouton")
        except discord.HTTPException:
            pass
        await inter.followup.send(embed=ok_embed("Rôle CM attribué ! Merci de porter le tag du serveur 🎉"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(PanneauxServeurCog(bot))
