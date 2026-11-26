"""État partagé + helpers communs aux cogs issus d'irie-bot."""
import logging
import re
import time
from datetime import datetime, timezone

import discord

from noyau import ids

logger = logging.getLogger("irie")

bot: discord.Client | None = None   # défini par bot.py
db = None                            # base Mongo "discord-bot" (collections de l'ancien irie-bot)

# ── État en mémoire ───────────────────────────────────────────────────────────
bots_allowed = False
perm_jail_role_id: int | None = None
private_category_id: int | None = None
stats_voice_channel_id: int | None = None

prison_release_whitelist: set[int] = set()
prison_saved_roles: dict[int, list[int]] = {}
open_tickets: dict[int, int] = {}            # user_id -> channel_id
private_discussions: dict[int, dict] = {}    # channel_id (texte OU vocal) -> données
reaction_roles: dict[int, dict] = {}         # message_id -> données
blacklist: set[int] = set()
dynamic_role_ids: dict[str, int] = {}        # label -> role_id
dynamic_visibility_ids: dict[str, int] = {}  # DYNAMIC_VIS_* -> role_id
invite_cache: dict[int, dict[str, dict]] = {}


def now() -> datetime:
    return datetime.now(timezone.utc)


# ── Fenêtres glissantes (remplace les Map + setTimeout du JS) ────────────────

class Fenetre:
    """Compteur par clé qui expire `window` secondes après sa création."""

    def __init__(self, window: float):
        self.window = window
        self._data: dict = {}

    def get(self, key):
        entry = self._data.get(key)
        if entry and time.monotonic() - entry["_t0"] > self.window:
            self._data.pop(key, None)
            return None
        return entry

    def start(self, key, **values):
        entry = {"_t0": time.monotonic(), **values}
        self._data[key] = entry
        return entry

    def delete(self, key):
        self._data.pop(key, None)

    def clear(self):
        self._data.clear()


# ── Embeds ────────────────────────────────────────────────────────────────────

def hexc(s: str) -> discord.Color:
    return discord.Color(int(s.lstrip("#"), 16))


def err_embed(desc): return discord.Embed(color=hexc("#ef4444"), description=f"❌ {desc}")
def ok_embed(desc): return discord.Embed(color=hexc("#22c55e"), description=f"✅ {desc}")
def info_embed(desc): return discord.Embed(color=hexc("#5865F2"), description=f"ℹ️ {desc}")


def ts(dt) -> int:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    return int(time.time())


# ── Hiérarchie des permissions ────────────────────────────────────────────────

def _has(member, role_id) -> bool:
    return isinstance(member, discord.Member) and member.get_role(role_id) is not None


def is_owner(user_id: int) -> bool: return user_id == ids.OWNER_ID
def is_saint(m): return _has(m, ids.SAINT_ROLE_ID)
def is_staff(m):
    return _has(m, ids.STAFF_ROLE_ID) or _has(m, ids.ADMIN_ROLE_ID) or (
        isinstance(m, discord.Member) and m.guild_permissions.administrator)
def is_pa_test(m): return _has(m, ids.PA_TEST_ROLE_ID)
def is_mod(m): return _has(m, ids.MOD_ROLE_ID)
def is_junior_mod(m): return _has(m, ids.JUNIOR_MOD_ROLE_ID)
def is_admin_perm(m): return isinstance(m, discord.Member) and m.guild_permissions.administrator


def has_perm_jail(m) -> bool:
    return bool(perm_jail_role_id) and _has(m, perm_jail_role_id)


def perm_level(m) -> float:
    if m is None:
        return 0
    if is_owner(m.id): return 5
    if is_saint(m): return 4
    if is_staff(m): return 3
    if is_pa_test(m): return 2
    if is_mod(m): return 1
    if is_junior_mod(m): return 0.5
    return 0


def has_min_perm(m, level) -> bool:
    return perm_level(m) >= level


def can_target(m, target) -> bool:
    if not m or not target:
        return False
    if is_owner(m.id): return True
    if is_owner(target.id): return False
    return perm_level(m) > perm_level(target)


def perm_label(perm) -> str:
    return ("👑 Owner" if perm >= 5 else "⚔️ Saint" if perm >= 4 else "🛡️ Staff/Admin" if perm >= 3
            else "🔷 PA Test" if perm >= 2 else "🔹 Modérateur" if perm >= 1
            else "🔸 Junior Mod" if perm >= 0.5 else "👤 Membre")


def extract_ids(args) -> list[int]:
    out = []
    for a in args:
        m = re.fullmatch(r"<@!?(\d+)>", a)
        if m:
            out.append(int(m.group(1)))
        elif re.fullmatch(r"\d{17,20}", a):
            out.append(int(a))
    return list(dict.fromkeys(out))


# ── Durées ────────────────────────────────────────────────────────────────────

def parse_duration(s: str) -> int | None:
    """Retourne une durée en secondes (10s / 5m / 2h / 1d)."""
    m = re.fullmatch(r"(\d+)([smhd])", s or "", re.I)
    if not m:
        return None
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2).lower()]


def format_duration(sec) -> str:
    if not sec:
        return "Permanent"
    sec = int(sec)
    d, h, m, s = sec // 86400, (sec % 86400) // 3600, (sec % 3600) // 60, sec % 60
    parts = [f"{v}{u}" for v, u in ((d, "j"), (h, "h"), (m, "m"), (s, "s")) if v]
    return " ".join(parts) or "0s"


# ── Rôles dynamiques ──────────────────────────────────────────────────────────

def get_classe_roles() -> list[dict]:
    res = []
    for r in ids.CLASSE_ROLES:
        if isinstance(r["id"], str):
            rid = dynamic_role_ids.get(r["label"])
            if rid:
                res.append({**r, "id": rid})
        else:
            res.append(r)
    return res


def all_classe_role_ids() -> list[int]:
    return [c["id"] for c in get_classe_roles()]


def get_visibility_roles() -> list[dict]:
    res = []
    for r in ids.VISIBILITY_ROLES:
        if isinstance(r["id"], str):
            rid = dynamic_visibility_ids.get(r["id"])
            if rid:
                res.append({**r, "id": rid})
        else:
            res.append(r)
    return res


# ── Salon de logs ─────────────────────────────────────────────────────────────

async def log_channel():
    ch = bot.get_channel(ids.TICKET_LOG_CHANNEL_ID)
    if ch is None:
        try:
            ch = await bot.fetch_channel(ids.TICKET_LOG_CHANNEL_ID)
        except discord.HTTPException:
            return None
    return ch


async def send_log(embed=None, **kw):
    ch = await log_channel()
    if ch:
        try:
            await ch.send(embed=embed, **kw)
        except discord.HTTPException:
            pass


_COLOR_MAP = {
    "BAN": "#ff0000", "UNBAN": "#22c55e", "KICK": "#f97316", "MUTE": "#f59e0b", "UNMUTE": "#22c55e",
    "WARN": "#f59e0b", "WARN_GRAVE": "#ef4444", "PRISON": "#4a0000", "LIBERER": "#22c55e",
    "LOCK": "#ef4444", "UNLOCK": "#22c55e", "CLEAR": "#5865F2", "ADDROLE": "#22c55e",
    "REMOVEROLE": "#f97316", "CREATEROLE": "#5865F2", "DELETEROLE": "#ef4444",
    "SLOWMODE": "#5865F2", "NICKNAME": "#5865F2",
}
_EMOJI_MAP = {
    "BAN": "🔨", "UNBAN": "✅", "KICK": "👢", "MUTE": "🔇", "UNMUTE": "🔊", "WARN": "⚠️",
    "WARN_GRAVE": "🚨", "PRISON": "⛓️", "LIBERER": "🔓", "LOCK": "🔒", "UNLOCK": "🔓",
    "CLEAR": "🗑️", "ADDROLE": "➕", "REMOVEROLE": "➖", "CREATEROLE": "🎭",
    "DELETEROLE": "🗑️", "SLOWMODE": "⏱️", "NICKNAME": "✏️",
}


async def send_mod_log(action, target, moderator, reason, duration=None, count=None, channel=None):
    """target : discord.User/Member, ou tuple (label, id)."""
    try:
        if target is None:
            cible = "N/A"
        elif isinstance(target, tuple):
            cible = f"<@{target[1]}> (`{target[0]}`)"
        else:
            cible = f"<@{target.id}> (`{target}`)"
        e = discord.Embed(color=hexc(_COLOR_MAP.get(action, "#5865F2")),
                          title=f"{_EMOJI_MAP.get(action, '📋')} {action}", timestamp=now())
        e.add_field(name="👤 Cible", value=cible, inline=True)
        e.add_field(name="🛡️ Modérateur", value=moderator.mention if moderator else "AUTO-MOD", inline=True)
        e.add_field(name="📝 Raison", value=(reason or "Non précisé")[:1024], inline=False)
        if duration: e.add_field(name="⏱️ Durée", value=duration, inline=True)
        if count: e.add_field(name="🔢 Total", value=str(count), inline=True)
        if channel: e.add_field(name="📢 Salon", value=f"<#{channel}>", inline=True)
        await send_log(e)
    except Exception as ex:
        logger.error(f"[MOD LOG] {ex}")


# ── Prison ────────────────────────────────────────────────────────────────────

async def save_prison_roles(user_id, guild_id, role_ids, reason="Non précisé", moderator_id=None):
    prison_saved_roles[user_id] = role_ids
    try:
        await db.prisonsaves.update_one(
            {"userId": str(user_id)},
            {"$set": {"guildId": str(guild_id), "roleIds": [str(r) for r in role_ids], "reason": reason,
                      "moderatorId": str(moderator_id) if moderator_id else None, "savedAt": now()}},
            upsert=True)
    except Exception as e:
        logger.error(f"[PRISON SAVE] {e}")


async def get_prison_roles(user_id) -> list[int]:
    if user_id in prison_saved_roles:
        return prison_saved_roles[user_id]
    try:
        doc = await db.prisonsaves.find_one({"userId": str(user_id)})
        if doc:
            roles = [int(r) for r in doc.get("roleIds", [])]
            prison_saved_roles[user_id] = roles
            return roles
    except Exception as e:
        logger.error(f"[PRISON SAVE] {e}")
    return []


async def delete_prison_roles(user_id):
    prison_saved_roles.pop(user_id, None)
    try:
        await db.prisonsaves.delete_one({"userId": str(user_id)})
    except Exception as e:
        logger.error(f"[PRISON SAVE] {e}")


def roles_a_sauver(member: discord.Member) -> list[int]:
    return [r.id for r in member.roles
            if r.id != member.guild.id and r.id != ids.PRISON_ROLE_ID and not r.managed]


async def mettre_en_prison_roles(member: discord.Member, reason: str):
    """Équivalent de member.roles.set([PRISON_ROLE_ID]) (on garde les rôles gérés)."""
    prison = member.guild.get_role(ids.PRISON_ROLE_ID)
    if prison is None:
        raise RuntimeError("Rôle prison introuvable")
    garder = [r for r in member.roles if r.managed]
    await member.edit(roles=[prison, *garder], reason=reason)


async def send_to_prison_automod(member: discord.Member, reason: str, messages_to_delete=()):
    try:
        await save_prison_roles(member.id, member.guild.id, roles_a_sauver(member), reason, "AUTO-MOD")
        await mettre_en_prison_roles(member, f"[AUTO-MOD] {reason}")
        for m in messages_to_delete:
            try:
                await m.delete()
            except discord.HTTPException:
                pass
        await send_log(discord.Embed(
            color=hexc("#7c0000"), title="🚨 AutoMod — Envoi en Prison", timestamp=now(),
            description=f"<@{member.id}> a été envoyé en prison.\n**{len(messages_to_delete)} message(s) supprimé(s).**\n\n**Raison:** {reason}"))
    except Exception as e:
        logger.error(f"[AUTOMOD] {e}")


# ── Warns ─────────────────────────────────────────────────────────────────────

async def add_warn(user_id, guild_id, type_="normal", reason="Non précisé", moderator_id=None) -> int:
    try:
        entry = {"reason": reason, "moderatorId": str(moderator_id) if moderator_id else None,
                 "date": now(), "type": type_}
        champ = "graveCount" if type_ == "grave" else "count"
        doc = await db.warns.find_one_and_update(
            {"userId": str(user_id), "guildId": str(guild_id)},
            {"$inc": {champ: 1}, "$push": {"warns": entry}, "$set": {"updatedAt": now()}},
            upsert=True, return_document=True)
        return int(doc.get(champ, 1))
    except Exception as e:
        logger.error(f"[WARN] {e}")
        return 1


async def reset_warn(user_id, guild_id):
    await db.warns.update_one({"userId": str(user_id), "guildId": str(guild_id)},
                              {"$set": {"count": 0, "graveCount": 0, "warns": [], "updatedAt": now()}},
                              upsert=True)


async def get_warn_doc(user_id, guild_id):
    try:
        return await db.warns.find_one({"userId": str(user_id), "guildId": str(guild_id)})
    except Exception:
        return None


async def get_warn_count(user_id, guild_id, type_="normal") -> int:
    doc = await get_warn_doc(user_id, guild_id)
    if not doc:
        return 0
    return int(doc.get("graveCount" if type_ == "grave" else "count", 0) or 0)


# ── Tickets ───────────────────────────────────────────────────────────────────

async def save_open_ticket(user_id, channel_id, guild_id, type_="staff"):
    await db.opentickets.update_one(
        {"userId": str(user_id)},
        {"$set": {"channelId": str(channel_id), "guildId": str(guild_id), "type": type_},
         "$setOnInsert": {"createdAt": now()}}, upsert=True)


async def delete_open_ticket(user_id):
    await db.opentickets.delete_one({"userId": str(user_id)})


# ── Chargement initial depuis Mongo ───────────────────────────────────────────

async def charger_depuis_db():
    try:
        async for t in db.opentickets.find():
            open_tickets[int(t["userId"])] = int(t["channelId"])
        logger.info(f"✅ {len(open_tickets)} ticket(s) restauré(s)")
    except Exception as e:
        logger.error(f"Erreur restauration tickets : {e}")
    try:
        async for p in db.prisonsaves.find():
            prison_saved_roles[int(p["userId"])] = [int(r) for r in p.get("roleIds", [])]
    except Exception as e:
        logger.error(f"Erreur restauration prison : {e}")
    try:
        n = 0
        async for a in db.avis.find({"exactitude": None, "isLegacy": {"$ne": True}}):
            note = a["note"] * 2 if a["note"] <= 5 else a["note"]
            await db.avis.update_one({"_id": a["_id"]}, {"$set": {"note": note, "isLegacy": True}})
            n += 1
        if n:
            logger.info(f"✅ Migration : {n} anciens avis convertis")
    except Exception as e:
        logger.error(f"Erreur migration avis : {e}")
    try:
        async for d in db.reactionroles.find():
            reaction_roles[int(d["messageId"])] = {"roleId": int(d["roleId"]), "channelId": int(d["channelId"]),
                                                   "guildId": int(d["guildId"]), "texte": d["texte"]}
    except Exception as e:
        logger.error(f"Erreur reaction roles : {e}")
    try:
        async for d in db.blacklists.find():
            blacklist.add(int(d["userId"]))
    except Exception as e:
        logger.error(f"Erreur blacklist : {e}")


# ── Remplacement des panneaux des anciens bots ────────────────────────────────
# Les boutons d'un message ne fonctionnent qu'avec le bot qui l'a posté : une
# fois irie-bot / progressionbot arrêtés, leurs panneaux deviennent morts. On
# les supprime pour que le bot unique reposte les siens.

import os as _os

ANCIENS_BOTS_IDS = {ids.ANCIEN_BOT_IRIE_ID} | {
    int(x) for x in _os.environ.get("ANCIENS_BOTS_IDS", "").replace(" ", "").split(",") if x.isdigit()}

_CUSTOM_IDS_CONNUS = (
    "classe_select_", "visibility_select", "avis_", "color_", "ticket_open", "claim_cm_tag",
    "reactionrole_claim_", "helper_", "be_helped", "notif_", "open_defi_modal_", "open_correction_modal_",
    "role_4e_3e", "role_3e_2nde", "role_2nde_1ere", "role_1ere_term", "role_term_sup", "role_helper",
    "persistent_create_vocal_btn", "persistent_edit_name_btn", "persistent_edit_limit_btn",
    "gw_participate", "resolu_oui", "resolu_non",
)
_URLS_CONNUES = ("tiktok.com/@mathematic_tok", "instagram.com/mathematic_tok", "paypal.me/iriecosplay")


def est_ancien_panneau(msg: discord.Message) -> bool:
    if msg.author.id == bot.user.id or not msg.author.bot:
        return False
    if msg.author.id in ANCIENS_BOTS_IDS:
        return True
    for row in msg.components:
        for c in getattr(row, "children", []):
            cid = getattr(c, "custom_id", None) or ""
            url = getattr(c, "url", None) or ""
            if any(cid.startswith(p) for p in _CUSTOM_IDS_CONNUS) or any(u in url for u in _URLS_CONNUES):
                ANCIENS_BOTS_IDS.add(msg.author.id)  # mémorise ce bot comme « ancien »
                return True
    return False


async def supprimer_anciens_panneaux(channel, limit=50) -> int:
    """Supprime les panneaux des anciens bots dans `channel`. Retourne le nombre supprimé."""
    n = 0
    if channel is None:
        return 0
    try:
        async for msg in channel.history(limit=limit):
            if est_ancien_panneau(msg):
                try:
                    await msg.delete()
                    n += 1
                except discord.HTTPException:
                    pass
    except discord.HTTPException:
        pass
    return n


async def deja_poste(channel, limit=20) -> bool:
    """Vrai si le bot a déjà un message avec composants dans les `limit` derniers."""
    try:
        async for msg in channel.history(limit=limit):
            if msg.author.id == bot.user.id and msg.components:
                return True
    except discord.HTTPException:
        pass
    return False


async def get_chan(cid):
    ch = bot.get_channel(cid)
    if ch is None:
        try:
            ch = await bot.fetch_channel(cid)
        except discord.HTTPException:
            return None
    return ch


class Composants(discord.ui.View):
    """Vue « jetable » : sert juste à envoyer des composants dont les clics sont
    traités par les listeners on_interaction des cogs (comme dans le bot JS)."""

    def __init__(self, *items):
        super().__init__(timeout=1)
        for it in items:
            self.add_item(it)


def bouton(custom_id, label, style=discord.ButtonStyle.secondary, emoji=None, disabled=False, row=None):
    return discord.ui.Button(custom_id=custom_id, label=label, style=style, emoji=emoji, disabled=disabled, row=row)


def lien(label, url, emoji=None, row=None):
    return discord.ui.Button(label=label, url=url, emoji=emoji, style=discord.ButtonStyle.link, row=row)


def custom_id(inter: discord.Interaction) -> str:
    return (inter.data or {}).get("custom_id", "") if inter.type in (
        discord.InteractionType.component, discord.InteractionType.modal_submit) else ""


def valeurs_select(inter: discord.Interaction) -> list[str]:
    return list((inter.data or {}).get("values", []))


def valeur_modal(inter: discord.Interaction, champ: str) -> str:
    for row in (inter.data or {}).get("components", []):
        comps = row.get("components") or ([row["component"]] if "component" in row else [])
        for c in comps:
            if c.get("custom_id") == champ:
                return c.get("value", "")
    return ""


class Modal(discord.ui.Modal):
    """Modal simple dont la soumission est traitée par on_interaction."""

    def __init__(self, custom_id, title, champs):
        super().__init__(title=title, custom_id=custom_id, timeout=None)
        for ch in champs:
            self.add_item(ch)

    async def on_submit(self, interaction):  # traité ailleurs
        pass
