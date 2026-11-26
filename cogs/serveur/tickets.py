"""Tickets support / candidature CM + modals défi / correction (ex irie-bot)."""
import asyncio
import io
import logging
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import Composants, Modal, bouton, err_embed, hexc, now

logger = logging.getLogger(__name__)

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def date_fr():
    d = datetime.now(timezone.utc)
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


class TicketsCog(commands.Cog, name="Tickets"):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, inter: discord.Interaction):
        cid = etat.custom_id(inter)
        if not cid or inter.guild is None:
            return
        try:
            if cid in ("ticket_open", "ticket_open_cm"):
                await self._ouvrir(inter, cm=(cid == "ticket_open_cm"))
            elif cid == "ticket_close":
                await self._fermer(inter)
            elif cid.startswith("open_defi_modal_") or cid.startswith("open_correction_modal_"):
                if not etat.has_min_perm(inter.user, 1):
                    return await inter.response.send_message("❌ Permission refusée.", ephemeral=True)
                defi = cid.startswith("open_defi_modal_")
                chan = cid.rsplit("_", 1)[1]
                await inter.response.send_modal(Modal(
                    f"modal_{'defi' if defi else 'correction'}_{chan}",
                    "📐 Défi quotidien" if defi else "✅ Correction du défi",
                    [discord.ui.TextInput(custom_id="defi_contenu" if defi else "correction_contenu",
                                          label="Contenu du défi" if defi else "Contenu de la correction",
                                          style=discord.TextStyle.paragraph, max_length=4000,
                                          placeholder="Écris le défi ici..." if defi else "Écris la correction ici...")]))
            elif cid.startswith("modal_defi_"):
                await self._defi(inter, int(cid.removeprefix("modal_defi_")))
            elif cid.startswith("modal_correction_"):
                await self._correction(inter, int(cid.removeprefix("modal_correction_")))
        except Exception as e:
            logger.exception(f"[TICKETS] {cid} : {e}")
            try:
                if inter.response.is_done():
                    await inter.followup.send("❌ Une erreur est survenue.", ephemeral=True)
                else:
                    await inter.response.send_message("❌ Une erreur est survenue.", ephemeral=True)
            except discord.HTTPException:
                pass

    async def _ouvrir(self, inter, cm: bool):
        member, guild = inter.user, inter.guild
        if member.id in etat.open_tickets:
            ex = guild.get_channel(etat.open_tickets[member.id])
            if ex:
                return await inter.response.send_message(embed=discord.Embed(color=hexc("#ef4444"),
                    description=f"❌ Tu as déjà un ticket ouvert : {ex.mention}\nFerme-le avant d'en ouvrir un nouveau."), ephemeral=True)
            etat.open_tickets.pop(member.id, None)
            await etat.delete_open_ticket(member.id)
        await inter.response.defer(ephemeral=True, thinking=True)
        cat = guild.get_channel(ids.TICKET_CATEGORY_ID)
        perms_staff = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True,
                                                  manage_messages=True, send_messages_in_threads=True)
        ow = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
              member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, send_messages_in_threads=True),
              guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, embed_links=True, attach_files=True)}
        role_ids = list(ids.TICKET_SUPPORT_ROLE_IDS) + ([ids.CM_ROLE_ID] if cm else [])
        for rid in role_ids:
            r = guild.get_role(rid)
            if r:
                ow[r] = perms_staff
        base = re.sub(r"[^a-z0-9]", "", member.name.lower())
        ch = await guild.create_text_channel(f"{'cm' if cm else 'ticket'}-{base}", category=cat if isinstance(cat, discord.CategoryChannel) else None,
                                             overwrites=ow, reason=f"{'Candidature CM de' if cm else 'Ticket ouvert par'} {member}")
        etat.open_tickets[member.id] = ch.id
        await etat.save_open_ticket(member.id, ch.id, guild.id, "cm" if cm else "staff")
        if cm:
            e = discord.Embed(color=hexc("#f5a623"), title="🌟 Candidature Community Manager", timestamp=now(),
                description=f"Bonjour <@{member.id}> ! 👋\n\nTu souhaites rejoindre l'équipe en tant que **Community Manager** ?\n\nPrésente-toi et explique ta motivation ci-dessous. Un membre de l'équipe CM te répondra dès que possible.\n\n> Pour fermer ce ticket, clique sur le bouton 🔒 ci-dessous.")
            e.add_field(name="👤 Candidat", value=f"<@{member.id}> ({member})", inline=True)
            mentions = f"<@&{ids.CM_ROLE_ID}>"
        else:
            e = discord.Embed(color=hexc("#5865F2"), title="🎫 Nouveau ticket", timestamp=now(),
                description=f"Bonjour <@{member.id}> ! 👋\n\nBienvenue dans ton ticket. **Décris ton problème ci-dessous**, le staff te répondra dès que possible.\n\n> Pour fermer ce ticket, clique sur le bouton 🔒 ci-dessous.")
            e.add_field(name="👤 Membre", value=f"<@{member.id}> ({member})", inline=True)
            mentions = " ".join(f"<@&{rid}>" for rid in dict.fromkeys(ids.TICKET_SUPPORT_ROLE_IDS))
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="📅 Ouvert le", value=f"<t:{etat.ts(now())}:F>", inline=True)
        await ch.send(content=mentions, embed=e, view=Composants(bouton("ticket_close", "Fermer le ticket", discord.ButtonStyle.danger, "🔒")))
        await inter.followup.send(f"✅ {'Ta candidature CM a été ouverte' if cm else 'Ticket créé'} : {ch.mention}", ephemeral=True)

    async def _fermer(self, inter):
        ch, member = inter.channel, inter.user
        if not (ch.name.startswith("ticket-") or ch.name.startswith("cm-")):
            return await inter.response.send_message("❌ Ce bouton ne peut être utilisé que dans un ticket.", ephemeral=True)
        staff = any(member.get_role(r) for r in ids.TICKET_SUPPORT_ROLE_IDS) or member.guild_permissions.administrator
        est_cm = member.get_role(ids.CM_ROLE_ID) is not None
        ouvreur = etat.open_tickets.get(member.id) == ch.id
        if not (staff or est_cm or ouvreur):
            return await inter.response.send_message("❌ Seul le staff, un CM ou l'ouvreur du ticket peut le fermer.", ephemeral=True)
        await inter.response.send_message(embed=discord.Embed(color=hexc("#ef4444"), description="🔒 Fermeture dans 5 secondes..."))
        owner_id, owner_tag = None, "Inconnu"
        for uid, cid in list(etat.open_tickets.items()):
            if cid == ch.id:
                owner_id = uid
                m = inter.guild.get_member(uid)
                if m:
                    owner_tag = str(m)
                etat.open_tickets.pop(uid, None)
                await etat.delete_open_ticket(uid)
                break
        lignes = []
        try:
            async for m in ch.history(limit=100, oldest_first=True):
                lignes.append(f"[{m.created_at.strftime('%d/%m/%Y %H:%M:%S')}] {m.author} : {m.content or '[embed/fichier]'}")
        except discord.HTTPException:
            pass
        est_cm_ticket = ch.name.startswith("cm-")
        e = discord.Embed(color=hexc("#f5a623" if est_cm_ticket else "#ef4444"),
                          title="🌟 Candidature CM fermée" if est_cm_ticket else "🔒 Ticket fermé", timestamp=now())
        e.add_field(name="👤 Membre", value=f"<@{owner_id}> ({owner_tag})" if owner_id else owner_tag, inline=True)
        e.add_field(name="🛠️ Fermé par", value=member.mention, inline=True)
        e.add_field(name="📅 Fermé le", value=f"<t:{etat.ts(now())}:F>", inline=True)
        if lignes:
            f = discord.File(io.BytesIO("\n".join(lignes).encode("utf-8")), filename=f"transcript-{ch.name}.txt")
            await etat.send_log(e, file=f)
        else:
            await etat.send_log(e)
        await asyncio.sleep(5)
        try:
            await ch.delete(reason=f"Ticket fermé par {member}")
        except discord.HTTPException:
            pass

    async def _defi(self, inter, channel_id):
        ch = inter.guild.get_channel(channel_id)
        if ch is None:
            return await inter.response.send_message("❌ Salon introuvable.", ephemeral=True)
        contenu = etat.valeur_modal(inter, "defi_contenu")
        await inter.response.defer(ephemeral=True, thinking=True)
        e = discord.Embed(color=hexc("#f5c518"), title="📐 Défi du jour", description=contenu, timestamp=now())
        e.set_footer(text=f"📅 {date_fr()}")
        await ch.send(embed=e)
        await inter.followup.send(f"✅ Défi envoyé dans <#{channel_id}> !", ephemeral=True)

    async def _correction(self, inter, channel_id):
        ch = inter.guild.get_channel(channel_id)
        if ch is None:
            return await inter.response.send_message("❌ Salon introuvable.", ephemeral=True)
        contenu = etat.valeur_modal(inter, "correction_contenu")
        await inter.response.defer(ephemeral=True, thinking=True)
        # supprime les réponses des membres (tout sauf owner + bot), comme l'ancien bot
        try:
            await ch.purge(limit=5000, check=lambda m: m.author.id not in (ids.OWNER_ID, self.bot.user.id), bulk=True)
        except discord.HTTPException:
            pass
        e = discord.Embed(color=hexc("#22c55e"), title="✅ Correction du défi", description=contenu, timestamp=now())
        e.set_footer(text=f"📅 {date_fr()}")
        await ch.send(embed=e)
        await inter.followup.send(f"✅ Correction envoyée dans <#{channel_id}> !", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
