"""🔐 Administration : blacklist, anti-raid des bots, discussions privées, avis, bienvenue."""
import re

import discord
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import err_embed, hexc, info_embed, now, ok_embed
from noyau.permissions import SAINT, STAFF, administrateur, niveau, owner_seulement


class Administration(commands.Cog, name="Administration"):
    """🔐 Sécurité, blacklist, discussions privées."""

    def __init__(self, bot):
        self.bot = bot

    # ── Blacklist ──

    @commands.hybrid_command(name="addbl", description="Mettre un utilisateur sous surveillance (ban auto s'il raide).", usage="@membre|ID [raison]")
    @niveau(SAINT, "Seul le rôle **Saint** peut gérer la blacklist.")
    async def addbl(self, ctx, utilisateur: discord.User, *, raison: str = "Non précisé"):
        if utilisateur.id in etat.blacklist:
            return await ctx.reply(embed=err_embed("Cet utilisateur est déjà en blacklist."))
        await etat.db.blacklists.update_one({"userId": str(utilisateur.id)}, {"$set": {
            "guildId": str(ctx.guild.id), "addedBy": str(ctx.author.id), "reason": raison, "addedAt": now()}}, upsert=True)
        etat.blacklist.add(utilisateur.id)
        await ctx.reply(embed=discord.Embed(color=hexc("#ff0000"), title="⛔ Utilisateur ajouté à la blacklist", timestamp=now(),
            description=f"**ID :** `{utilisateur.id}`\n**Raison :** {raison}\n**Ajouté par :** <@{ctx.author.id}>\n\n> Cet utilisateur sera **automatiquement banni** s'il :\n> • Ban plus de {ids.BL_BAN_THRESHOLD} personnes en {int(ids.BL_BAN_WINDOW)}s\n> • Ajoute un bot sur le serveur\n> • Crée plus de {ids.BL_SALON_THRESHOLD} salons en {int(ids.BL_SALON_WINDOW)}s"))

    @commands.hybrid_command(name="delbl", description="Retirer un utilisateur de la blacklist.", usage="@membre|ID")
    @niveau(SAINT, "Seul le rôle **Saint** peut gérer la blacklist.")
    async def delbl(self, ctx, utilisateur: discord.User):
        if utilisateur.id not in etat.blacklist:
            return await ctx.reply(embed=err_embed("Cet utilisateur n'est pas en blacklist."))
        await etat.db.blacklists.delete_one({"userId": str(utilisateur.id)})
        etat.blacklist.discard(utilisateur.id)
        await ctx.reply(embed=ok_embed(f"`{utilisateur.id}` retiré de la blacklist."))

    @commands.hybrid_command(name="listbl", description="Voir la blacklist.")
    @niveau(SAINT)
    async def listbl(self, ctx):
        docs = await etat.db.blacklists.find({"guildId": str(ctx.guild.id)}).to_list(None)
        if not docs:
            return await ctx.reply(embed=info_embed("La blacklist est vide."))
        lignes = [f"• `{d['userId']}` — {d.get('reason')} — Ajouté par <@{d.get('addedBy')}> — <t:{etat.ts(d.get('addedAt'))}:R>" for d in docs]
        await ctx.reply(embed=discord.Embed(color=hexc("#ff0000"), title=f"⛔ Blacklist — {len(docs)} utilisateur(s)",
                                            description="\n".join(lignes)[:4096], timestamp=now()))

    # ── Anti-raid des bots ──

    @commands.hybrid_command(name="allowbot", description="Autoriser (on) ou surveiller (off) les bots dans l'anti-raid.", usage="[on|off]")
    @owner_seulement()
    async def allowbot(self, ctx, etat_voulu: str | None = None):
        if etat_voulu == "on":
            etat.bots_allowed = True
            return await ctx.reply(embed=discord.Embed(color=hexc("#22c55e"), title="🤖 Bots autorisés — Sécurité allégée", timestamp=now(),
                description="✅ Les bots peuvent désormais créer/supprimer des salons et des rôles librement sans déclencher l'anti-raid.\n\n> Les humains restent surveillés normalement.\n> Désactive avec `+allowbot off` quand tu as terminé."))
        if etat_voulu == "off":
            etat.bots_allowed = False
            sec = self.bot.get_cog("Sécurité")
            if sec:
                sec.raid_fast.clear()
                sec.raid_slow.clear()
            return await ctx.reply(embed=discord.Embed(color=hexc("#ef4444"), title="🛡️ Sécurité maximale — Bots surveillés", timestamp=now(),
                description=f"🔒 Sécurité **réactivée** — tout le monde est surveillé.\n\n**Fenêtre ultra-rapide :** {ids.RAID_FAST_THRESHOLD} actions en {int(ids.RAID_FAST_WINDOW)}s → sanction immédiate\n**Fenêtre rapide :** {ids.RAID_SLOW_THRESHOLD} actions en {int(ids.RAID_SLOW_WINDOW)}s → sanction immédiate"))
        await ctx.reply(embed=discord.Embed(color=hexc("#5865F2"), title="🤖 Statut AllowBot", timestamp=now(),
            description=f"**État actuel :** {'🟢 ON — bots exemptés de l’anti-raid' if etat.bots_allowed else '🔴 OFF — sécurité maximale'}\n\n`+allowbot on` — Autoriser les bots\n`+allowbot off` — Surveiller tout le monde"))

    # ── Avis ──

    @commands.hybrid_command(name="delavis", description="Supprimer les avis reçus par un membre (option : d'un auteur précis).", usage="@cible [@auteur]")
    @niveau(STAFF)
    async def delavis(self, ctx, cible: discord.User, auteur: discord.User | None = None):
        q = {"targetId": str(cible.id), "guildId": str(ctx.guild.id)}
        if auteur:
            q["authorId"] = str(auteur.id)
        res = await etat.db.avis.delete_many(q)
        await ctx.reply(embed=ok_embed(f"**{res.deleted_count}** avis supprimé(s) sur <@{cible.id}>."))

    # ── Discussions privées ──

    @commands.hybrid_command(name="private", description="Créer une discussion privée (texte + vocal). Le 1er membre = chef d'équipe.",
                             usage="<@chef> <@membre2> <@membre3> ...")
    @administrateur()
    async def private(self, ctx, *, membres: str):
        g = ctx.guild
        uids = etat.extract_ids(membres.split())
        if not uids:
            return await ctx.reply(embed=err_embed("Usage : `+private <id_chef_équipe> <id2> <id3> ...`\n\n> Le **premier identifiant** de la liste devient automatiquement le **chef d'équipe**.\n> Tu peux aussi mentionner les membres avec **@pseudo**."))
        cat = g.get_channel(etat.private_category_id or 0)
        if cat is None:
            return await ctx.reply(embed=err_embed("La catégorie \"Discussion Privée\" n'est pas encore prête. Réessaie dans quelques secondes."))
        leader = g.get_member(uids[0])
        if leader is None:
            return await ctx.reply(embed=err_embed("Impossible de trouver le **chef d'équipe** (premier identifiant) sur ce serveur."))
        liste = [m for m in (g.get_member(i) for i in uids) if m]
        p = await ctx.reply(embed=discord.Embed(color=hexc("#f59e0b"), description="⏳ Création de la discussion privée..."))
        try:
            base = re.sub(r"[^a-z0-9]", "", leader.name.lower()) or str(leader.id)
            acces = etat.perms_vocal()
            ow = {g.default_role: discord.PermissionOverwrite(view_channel=False), g.me: acces}
            for rid in ids.PRIVATE_ACCESS_ROLE_IDS:
                r = g.get_role(rid)
                if r:
                    ow[r] = acces
            for m in liste:
                ow[m] = acces
            txt = await g.create_text_channel(f"🔒┃{base}", category=cat, overwrites=ow, reason=f"[PRIVATE] Discussion privée créée par {ctx.author}")
            voc = await g.create_voice_channel(f"🔊 {base}", category=cat, overwrites=ow, reason=f"[PRIVATE] Salon vocal privé créé par {ctx.author}")
            mids = [m.id for m in liste]
            await etat.db.privatediscussions.insert_one({"guildId": str(g.id), "textChannelId": str(txt.id), "voiceChannelId": str(voc.id),
                "leaderId": str(leader.id), "memberIds": [str(i) for i in mids], "createdBy": str(ctx.author.id), "createdAt": now()})
            data = {"guildId": g.id, "textChannelId": txt.id, "voiceChannelId": voc.id, "leaderId": leader.id, "memberIds": mids}
            etat.private_discussions[txt.id] = data
            etat.private_discussions[voc.id] = data
            await txt.send(embed=discord.Embed(color=hexc("#5865F2"), title="🔒 Discussion privée créée", timestamp=now(),
                description=f"**Chef d'équipe :** <@{leader.id}>\n**Membres :** {', '.join(m.mention for m in liste)}\n\n> Le chef d'équipe (ou un administrateur) peut ajouter de nouveaux membres avec `+addprivate <id> ...` directement dans ce salon."))
            await p.edit(embed=ok_embed(f"🔒 Discussion privée créée : {txt.mention} et **{voc.name}** (vocal).\n**Chef d'équipe :** <@{leader.id}>\n**Membres :** {len(liste)}"))
        except discord.HTTPException:
            await p.edit(embed=err_embed("Impossible de créer la discussion privée. Vérifie mes permissions."))

    @commands.hybrid_command(name="addprivate", description="Ajouter des membres à la discussion privée (dans son salon).", usage="<@membre> ...")
    async def addprivate(self, ctx, *, membres: str):
        doc = etat.private_discussions.get(ctx.channel.id)
        if doc is None:
            return await ctx.reply(embed=err_embed("Cette commande doit être utilisée **directement dans le salon textuel** d'une discussion privée."))
        if not (ctx.author.guild_permissions.administrator or etat.is_owner(ctx.author.id) or doc["leaderId"] == ctx.author.id):
            return await ctx.reply(embed=err_embed("Seul le **chef d'équipe** de cette discussion ou un **administrateur** peut ajouter des membres."))
        nouveaux = [i for i in etat.extract_ids(membres.split()) if i != doc["leaderId"] and i not in doc["memberIds"]]
        if not nouveaux:
            return await ctx.reply(embed=err_embed("Usage : `+addprivate <id1> <id2> ...`\n\nAucun nouvel identifiant valide fourni (déjà présent, chef d'équipe, ou introuvable)."))
        txt, voc = ctx.guild.get_channel(doc["textChannelId"]), ctx.guild.get_channel(doc["voiceChannelId"] or 0)
        if txt is None:
            return await ctx.reply(embed=err_embed("Le salon textuel associé est introuvable."))
        ajoutes = []
        for i in nouveaux:
            m = ctx.guild.get_member(i)
            if m is None:
                continue
            for ch in (txt, voc):
                if ch:
                    try:
                        await ch.set_permissions(m, overwrite=etat.perms_vocal(), reason=f"[ADDPRIVATE] par {ctx.author}")
                    except discord.HTTPException:
                        pass
            ajoutes.append(m)
        if not ajoutes:
            return await ctx.reply(embed=err_embed("Aucun des identifiants fournis n'a pu être trouvé sur ce serveur."))
        doc["memberIds"].extend(m.id for m in ajoutes)
        await etat.db.privatediscussions.update_one({"textChannelId": str(doc["textChannelId"])},
                                                    {"$addToSet": {"memberIds": {"$each": [str(m.id) for m in ajoutes]}}})
        await ctx.reply(embed=ok_embed(f"{', '.join(m.mention for m in ajoutes)} {'ont été ajoutés' if len(ajoutes) > 1 else 'a été ajouté'} à cette discussion privée."))


async def setup(bot):
    await bot.add_cog(Administration(bot))
