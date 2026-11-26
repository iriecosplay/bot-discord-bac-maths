"""Système d'avis sur les helpers (ex irie-bot)."""
import asyncio
import logging
import math
import time

import discord
from discord.ext import commands

from noyau import etat, ids
from noyau.etat import Composants, Modal, bouton, err_embed, hexc, now

logger = logging.getLogger(__name__)
B = discord.ButtonStyle

_pending: dict[str, dict] = {}       # "{auteur}_{cible}" -> notes en cours
_top_cache: dict[int, tuple] = {}    # guild_id -> (expire, ranked)


def stars10(note):
    filled = max(0, min(5, round(note / 2)))
    return "⭐" * filled + "✦" * (5 - filled)


def note_color(avg):
    return hexc("#22c55e" if avg >= 8.5 else "#84cc16" if avg >= 6.5 else "#f59e0b" if avg >= 4.5 else "#f97316" if avg >= 2.5 else "#ef4444")


def note_emoji(avg):
    return "🏆" if avg >= 8.5 else "😄" if avg >= 6.5 else "😐" if avg >= 4.5 else "😕" if avg >= 2.5 else "💀"


def wilson(moyenne, total):
    if total == 0:
        return 0
    p, z = (moyenne - 1) / 9, 1.96
    return (p + z * z / (2 * total) - z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)) / (1 + z * z / total)


def r1(x):
    return round(x * 10) / 10


def fmt(x):
    return f"{x:g}"


async def find_members(query: str, guild: discord.Guild):
    import re
    q = query.strip()
    m = re.fullmatch(r"<@!?(\d+)>", q) or (re.fullmatch(r"\d{17,20}", q) and re.match(r"(\d+)", q))
    if m:
        try:
            return [guild.get_member(int(m.group(1))) or await guild.fetch_member(int(m.group(1)))]
        except discord.HTTPException:
            return []
    low = q.lower()
    res = [mb for mb in guild.members if not mb.bot and any(
        low in (s or "").lower() for s in (mb.name, mb.display_name, mb.nick, mb.global_name))]
    res.sort(key=lambda mb: not (mb.name.lower().startswith(low) or (mb.nick or "").lower().startswith(low)))
    return res[:10]


def note_components(target_id):
    def sel(ph, cid, row):
        return discord.ui.Select(custom_id=cid, placeholder=ph, row=row, options=[
            discord.SelectOption(label=f"{v}/10", value=str(v), emoji="🟢" if v >= 8 else "🟡" if v >= 5 else "🔴")
            for v in range(1, 11)])
    return [sel("📐 Exactitude mathématique", f"avis_note_exactitude_{target_id}", 0),
            sel("💬 Clarté de l'explication", f"avis_note_clarte_{target_id}", 1),
            sel("🎯 Compréhension de l'élève", f"avis_note_comprehension_{target_id}", 2)]


def embed_noter(member):
    e = discord.Embed(color=hexc("#5865F2"), title=f"📝 Noter {member.name}", timestamp=now(),
        description="**Note les 3 critères ci-dessous puis clique sur \"Continuer\" quand tu as tout rempli.**\n\n📐 **Exactitude mathématique** — Les réponses étaient-elles correctes ?\n💬 **Clarté de l'explication** — Était-ce bien expliqué ?\n🎯 **Compréhension de l'élève** — A-t-il cherché à te comprendre ?")
    e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text="Remplis les 3 menus déroulants pour débloquer le bouton Continuer.")
    return e


def vue_noter(target_id, debloque=False):
    return Composants(*note_components(target_id),
                      bouton(f"avis_continuer_{target_id}", "Continuer →", B.success, "✏️", disabled=not debloque, row=3))


async def dashboard(target_id: int, guild: discord.Guild, page=0):
    avis = await etat.db.avis.find({"targetId": str(target_id), "guildId": str(guild.id)}).sort("createdAt", -1).to_list(None)
    tm = guild.get_member(target_id)
    nom = tm.name if tm else f"Utilisateur ({target_id})"
    if not avis:
        e = discord.Embed(color=hexc("#5865F2"), title=f"📋 Profil d'avis — {nom}", description="> Aucun avis pour le moment.", timestamp=now())
        if tm: e.set_thumbnail(url=tm.display_avatar.url)
        return {"embed": e, "view": None}
    total = len(avis)
    moy = r1(sum(a["note"] for a in avis) / total)
    nouveaux = [a for a in avis if not a.get("isLegacy")]
    sous = ""
    if nouveaux:
        n = len(nouveaux)
        ex = r1(sum(a.get("exactitude") or 0 for a in nouveaux) / n)
        cl = r1(sum(a.get("clarte") or 0 for a in nouveaux) / n)
        co = r1(sum(a.get("comprehension") or 0 for a in nouveaux) / n)
        sous = f"\n\n**Détail des critères** *({n} avis détaillés)*\n📐 Exactitude mathématique : **{fmt(ex)}/10**\n💬 Clarté de l'explication : **{fmt(cl)}/10**\n🎯 Compréhension de l'élève : **{fmt(co)}/10**"
    pages = math.ceil(total / ids.AVIS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    e = discord.Embed(color=note_color(moy), title=f"{note_emoji(moy)} Profil d'avis — {nom}", timestamp=now(),
                      description=f"## {stars10(round(moy))}  **{fmt(moy)}/10**\n> **{total}** avis au total" + sous)
    if tm: e.set_thumbnail(url=tm.display_avatar.url)
    for a in avis[page * ids.AVIS_PER_PAGE:(page + 1) * ids.AVIS_PER_PAGE]:
        titre = f"{stars10(a['note'])} **{fmt(a['note'])}/10** · <t:{etat.ts(a.get('createdAt'))}:R>"
        corps = f"> {a['commentaire']}\n— <@{a['authorId']}>"
        if not a.get("isLegacy"):
            corps = f"📐 `{a.get('exactitude')}/10`  💬 `{a.get('clarte')}/10`  🎯 `{a.get('comprehension')}/10`\n" + corps
        e.add_field(name=titre[:256], value=corps[:1024], inline=False)
    e.set_footer(text=f"Page {page + 1}/{pages} · {total} avis")
    vue = None
    if pages > 1:
        vue = Composants(bouton(f"dashboard_prev_{target_id}_{page}", "Précédent", B.secondary, "⬅️", disabled=page == 0),
                         bouton(f"dashboard_page_{target_id}_{page}", f"{page + 1} / {pages}", B.primary, disabled=True),
                         bouton(f"dashboard_next_{target_id}_{page}", "Suivant", B.secondary, "➡️", disabled=page >= pages - 1))
    return {"embed": e, "view": vue}


async def top_page(ranked, page, guild):
    pages = math.ceil(len(ranked) / ids.TOPAVIS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    medals = ["🥇", "🥈", "🥉"]
    lignes = []
    for i, s in enumerate(ranked[page * ids.TOPAVIS_PER_PAGE:(page + 1) * ids.TOPAVIS_PER_PAGE]):
        rang = page * ids.TOPAVIS_PER_PAGE + i
        m = guild.get_member(int(s["_id"]))
        avg = r1(s["moyenne"])
        lignes.append(f"{medals[rang] if rang < 3 else f'**#{rang + 1}**'} **{m.name if m else 'Utilisateur'}** — {stars10(round(avg))} **{fmt(avg)}/10** *({s['total']} avis)*")
    e = discord.Embed(color=hexc("#f5c518"), title="🏆 Classement des mieux notés", description="\n".join(lignes) or "Aucune donnée.", timestamp=now())
    e.set_footer(text=f"Page {page + 1}/{pages} • Classement par score de confiance (Wilson)")
    vue = None
    if pages > 1:
        vue = Composants(bouton(f"topavis_prev_{page}", "Précédent", B.secondary, "⬅️", disabled=page == 0),
                         bouton(f"topavis_page_{page}", f"{page + 1} / {pages}", B.primary, disabled=True),
                         bouton(f"topavis_next_{page}", "Suivant", B.secondary, "➡️", disabled=page >= pages - 1))
    return {"embed": e, "view": vue}


def options_membres(results, emoji):
    return [discord.SelectOption(
        label=f"{m.name}{f' ({m.nick})' if m.nick else ''}"[:100],
        description=f"ID: …{str(m.id)[-4:]} · {m.global_name or m.name}"[:100], value=str(m.id), emoji=emoji) for m in results]


class AvisCog(commands.Cog, name="Avis"):
    def __init__(self, bot):
        self.bot = bot
        self._pret = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._pret:
            return
        self._pret = True
        ch = await etat.get_chan(ids.AVIS_CHANNEL_ID)
        if ch is None:
            return
        try:
            # supprime les panneaux précédents (du bot unique ET des anciens bots), puis republie
            async for m in ch.history(limit=500):
                if m.author.id == self.bot.user.id or etat.est_ancien_panneau(m) or m.author.id in etat.ANCIENS_BOTS_IDS:
                    try:
                        await m.delete()
                    except discord.HTTPException:
                        pass
                    await asyncio.sleep(0.4)
            await asyncio.sleep(1.5)
            e = discord.Embed(color=hexc("#5865F2"), title="⭐ Laisser un avis — Helpers & Membres", timestamp=now(),
                description="**Tu as été aidé par quelqu'un sur ce serveur ?**\n\n> Laisse-lui un avis pour l'encourager et aider la communauté à identifier les meilleurs helpers !\n\n**📝 Laisser un avis**\n> Clique sur **\"Noter quelqu'un\"** puis mentionne la personne avec **@pseudo** (ou colle son ID).\n> Note 3 critères et laisse un commentaire.\n\n**📊 Voir un profil / Classement**\n> Consulte le profil d'un membre ou le top des mieux notés.\n\n─────────────────────────────\n> ⚠️ Maximum **2 avis** par personne cible.")
            e.set_image(url="https://i.pinimg.com/1200x/90/f1/6a/90f16aa783c0bb624c6af83444890533.jpg")
            e.set_footer(text="Système d'avis • Mathematic")
            await ch.send(embed=e, view=Composants(bouton("avis_formuler", "Noter quelqu'un", B.primary, "📝"),
                                                   bouton("avis_voir", "Voir un profil / Top", B.secondary, "📊")))
        except discord.HTTPException as ex:
            logger.error(f"[AVIS] panneau : {ex}")

    async def _verif_cible(self, inter, target: discord.Member):
        if target.id == inter.user.id:
            await inter.followup.send(embed=err_embed("Tu ne peux pas te noter toi-même."), ephemeral=True); return False
        if target.bot:
            await inter.followup.send(embed=err_embed("Tu ne peux pas noter un bot."), ephemeral=True); return False
        n = await etat.db.avis.count_documents({"targetId": str(target.id), "authorId": str(inter.user.id), "guildId": str(inter.guild.id)})
        if n >= 2:
            await inter.followup.send(embed=err_embed("Tu as déjà laissé **2 avis** sur cette personne. C'est le maximum."), ephemeral=True); return False
        return True

    @commands.Cog.listener()
    async def on_interaction(self, inter: discord.Interaction):
        cid = etat.custom_id(inter)
        if not cid or inter.guild is None:
            return
        try:
            await self._dispatch(inter, cid)
        except Exception as e:
            logger.exception(f"[AVIS] {cid} : {e}")
            try:
                if inter.response.is_done():
                    await inter.followup.send(embed=err_embed("Une erreur est survenue."), ephemeral=True)
                else:
                    await inter.response.send_message(embed=err_embed("Une erreur est survenue."), ephemeral=True)
            except discord.HTTPException:
                pass

    async def _dispatch(self, inter, cid):
        db, guild, user = etat.db, inter.guild, inter.user

        if cid == "avis_formuler":
            await inter.response.send_modal(Modal("modal_avis_cible", "📝 Qui veux-tu noter ?", [discord.ui.TextInput(
                custom_id="avis_cible_query", label="Mentionne la personne ou écris son pseudo", max_length=100,
                placeholder="Ex: @Mathematic  ou  math  ou  123456789012345678")]))
        elif cid == "avis_voir":
            await inter.response.send_message(embed=discord.Embed(color=hexc("#5865F2"), description="Que veux-tu consulter ?"),
                view=Composants(bouton("avis_voir_profil", "Profil d'un membre", B.primary, "👤"),
                                bouton("avis_voir_top", "Classement global", B.secondary, "🏆")), ephemeral=True)
        elif cid == "avis_voir_profil":
            await inter.response.send_modal(Modal("modal_dashboard_search", "🔍 Rechercher un profil", [discord.ui.TextInput(
                custom_id="dashboard_query", label="Pseudo, @mention ou ID Discord", max_length=100,
                placeholder="Ex: @Mathematic  ou  math  ou  123456789012345678")]))
        elif cid == "avis_voir_top":
            await inter.response.defer(ephemeral=True, thinking=True)
            stats = await db.avis.aggregate([{"$match": {"guildId": str(guild.id)}},
                {"$group": {"_id": "$targetId", "moyenne": {"$avg": "$note"}, "total": {"$sum": 1}}}]).to_list(None)
            if not stats:
                return await inter.followup.send(embed=discord.Embed(color=hexc("#5865F2"), title="🏆 Top Avis", description="Pas encore d'avis sur ce serveur."), ephemeral=True)
            ranked = sorted(stats, key=lambda s: wilson(s["moyenne"], s["total"]), reverse=True)
            _top_cache[guild.id] = (time.monotonic() + 300, ranked)
            p = await top_page(ranked, 0, guild)
            await inter.followup.send(embed=p["embed"], view=p["view"] or discord.utils.MISSING, ephemeral=True)
        elif cid.startswith("topavis_prev_") or cid.startswith("topavis_next_"):
            cache = _top_cache.get(guild.id)
            if not cache or cache[0] < time.monotonic():
                return await inter.response.send_message("❌ Session expirée. Clique à nouveau sur \"Classement global\".", ephemeral=True)
            page = int(cid.rsplit("_", 1)[1]) + (-1 if "prev" in cid else 1)
            p = await top_page(cache[1], page, guild)
            await inter.response.edit_message(embed=p["embed"], view=p["view"])
        elif cid.startswith("dashboard_prev_") or cid.startswith("dashboard_next_"):
            parts = cid.split("_")
            page = int(parts[-1]) + (-1 if parts[1] == "prev" else 1)
            p = await dashboard(int(parts[2]), guild, page)
            await inter.response.edit_message(embed=p["embed"], view=p["view"])
        elif cid == "avis_select_membre":
            await inter.response.defer(ephemeral=True, thinking=True)
            tm = guild.get_member(int(etat.valeurs_select(inter)[0]))
            if tm is None:
                return await inter.followup.send(embed=err_embed("Membre introuvable."), ephemeral=True)
            if await self._verif_cible(inter, tm):
                await inter.followup.send(embed=embed_noter(tm), view=vue_noter(tm.id), ephemeral=True)
        elif cid == "dashboard_select_membre":
            await inter.response.defer(ephemeral=True, thinking=True)
            p = await dashboard(int(etat.valeurs_select(inter)[0]), guild, 0)
            await inter.followup.send(embed=p["embed"], view=p["view"] or discord.utils.MISSING, ephemeral=True)
        elif cid.startswith(("avis_note_exactitude_", "avis_note_clarte_", "avis_note_comprehension_")):
            critere = cid.split("_")[2]
            target_id = cid.split("_", 3)[3]
            key = f"{user.id}_{target_id}"
            cur = _pending.setdefault(key, {})
            cur[critere] = int(etat.valeurs_select(inter)[0])
            if all(k in cur for k in ("exactitude", "clarte", "comprehension")):
                await inter.response.edit_message(view=vue_noter(int(target_id), debloque=True))
            else:
                await inter.response.defer()
        elif cid.startswith("avis_continuer_"):
            target_id = cid.removeprefix("avis_continuer_")
            cur = _pending.get(f"{user.id}_{target_id}") or {}
            if not all(k in cur for k in ("exactitude", "clarte", "comprehension")):
                return await inter.response.send_message("❌ Note d'abord les 3 critères avant de continuer.", ephemeral=True)
            await inter.response.send_modal(Modal(f"modal_avis_general_{target_id}", "💬 Commentaire général", [discord.ui.TextInput(
                custom_id="avis_general", label="Ton avis en quelques mots", style=discord.TextStyle.paragraph,
                placeholder="Ex: Très bon helper, explications claires et patientes...", min_length=10, max_length=500)]))
        elif cid == "modal_avis_cible":
            query = etat.valeur_modal(inter, "avis_cible_query").strip()
            await inter.response.defer(ephemeral=True, thinking=True)
            res = await find_members(query, guild)
            if not res:
                return await inter.followup.send(embed=discord.Embed(color=hexc("#ef4444"), title="❌ Aucun membre trouvé",
                    description=f"Impossible de trouver **\"{query}\"** sur ce serveur.\n\n**Conseils :**\n> • Mentionne directement la personne avec **@pseudo**\n> • Utilise une partie de son pseudo\n> • Colle son **ID Discord**"), ephemeral=True)
            if len(res) == 1:
                if await self._verif_cible(inter, res[0]):
                    await inter.followup.send(embed=embed_noter(res[0]), view=vue_noter(res[0].id), ephemeral=True)
                return
            await inter.followup.send(embed=discord.Embed(color=hexc("#f59e0b"), title=f"🔍 Plusieurs membres trouvés pour \"{query}\""[:256],
                description=f"**{len(res)} membres** correspondent à ta recherche.\nSélectionne la bonne personne dans le menu ci-dessous."),
                view=Composants(discord.ui.Select(custom_id="avis_select_membre", placeholder="Choisis la bonne personne…", options=options_membres(res, "👤"))), ephemeral=True)
        elif cid == "modal_dashboard_search":
            query = etat.valeur_modal(inter, "dashboard_query").strip()
            await inter.response.defer(ephemeral=True, thinking=True)
            res = await find_members(query, guild)
            if not res:
                return await inter.followup.send(embed=err_embed(f'Aucun membre trouvé pour "{query}".'), ephemeral=True)
            if len(res) > 1:
                return await inter.followup.send(embed=discord.Embed(color=hexc("#f59e0b"), title=f"🔍 Plusieurs membres trouvés pour \"{query}\""[:256],
                    description=f"**{len(res)} membres** correspondent."),
                    view=Composants(discord.ui.Select(custom_id="dashboard_select_membre", placeholder="Choisis le membre à consulter…", options=options_membres(res, "📊"))), ephemeral=True)
            p = await dashboard(res[0].id, guild, 0)
            await inter.followup.send(embed=p["embed"], view=p["view"] or discord.utils.MISSING, ephemeral=True)
        elif cid.startswith("modal_avis_general_"):
            target_id = cid.removeprefix("modal_avis_general_")
            texte = etat.valeur_modal(inter, "avis_general")
            key = f"{user.id}_{target_id}"
            p = _pending.get(key)
            if not p:
                return await inter.response.send_message("❌ Session expirée. Recommence depuis le bouton.", ephemeral=True)
            ex, cl, co = p["exactitude"], p["clarte"], p["comprehension"]
            note = r1((ex + cl + co) / 3)
            await inter.response.defer(ephemeral=True, thinking=True)
            filtre = {"targetId": target_id, "authorId": str(user.id), "guildId": str(guild.id)}
            n = await db.avis.count_documents(filtre)
            if n >= 2:
                _pending.pop(key, None)
                return await inter.followup.send(embed=err_embed("Tu as déjà laissé **2 avis** sur cet utilisateur."), ephemeral=True)
            idx = n + 1
            await db.avis.update_one({**filtre, "avisIndex": idx},
                {"$set": {"note": note, "commentaire": texte, "exactitude": ex, "clarte": cl, "comprehension": co,
                          "isLegacy": False, "updatedAt": now()}, "$setOnInsert": {"createdAt": now()}}, upsert=True)
            _pending.pop(key, None)
            tous = await db.avis.find({"targetId": target_id, "guildId": str(guild.id)}).to_list(None)
            moy = r1(sum(a["note"] for a in tous) / len(tous)) if tous else note
            tm = guild.get_member(int(target_id))
            e = discord.Embed(color=note_color(note), title="✅ Avis enregistré !", timestamp=now())
            if tm: e.set_thumbnail(url=tm.display_avatar.url)
            e.add_field(name="👤 Pour", value=f"<@{target_id}>", inline=True)
            e.add_field(name="📊 Note globale", value=f"{stars10(round(note))} **{fmt(note)}/10**", inline=True)
            e.add_field(name="📐 Exactitude", value=f"**{ex}/10**", inline=True)
            e.add_field(name="💬 Clarté", value=f"**{cl}/10**", inline=True)
            e.add_field(name="🎯 Compréhension", value=f"**{co}/10**", inline=True)
            e.add_field(name="💭 Avis général", value=f"> {texte}"[:1024], inline=False)
            e.add_field(name="📈 Nouvelle moyenne", value=f"{stars10(round(moy))} **{fmt(moy)}/10** ({len(tous)} avis)", inline=False)
            e.set_footer(text="Avis n°1 — il te reste 1 avis pour cette personne" if idx == 1 else "Avis n°2 — tu as atteint le maximum pour cette personne")
            log = await etat.get_chan(ids.AVIS_LOG_CHANNEL_ID)
            if log:
                try:
                    await log.send(content=f"<@{target_id}>", embed=e)
                except discord.HTTPException:
                    pass
            await inter.followup.send(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AvisCog(bot))
