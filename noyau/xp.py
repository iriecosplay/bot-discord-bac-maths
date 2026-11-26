from datetime import datetime, timezone


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def xp_for_level(level: int) -> int:
    """XP total requis pour atteindre ce niveau."""
    return 150 * (level ** 2)


def level_from_xp(xp: int) -> int:
    """Calcule le niveau à partir de l'XP total."""
    level = 0
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


ROLES_CONFIG = [
    {"name": "🔰 Novice",    "level": 1},
    {"name": "🌱 Apprenti",  "level": 4},
    {"name": "♟️ Stratège",  "level": 8},
    {"name": "📖 Érudit",    "level": 13},
    {"name": "🎵 Virtuose",  "level": 21},
    {"name": "⚡ Titan",     "level": 24},
    {"name": "🔺 Ascendant", "level": 36},
]


def role_for_level(level: int) -> str | None:
    """Retourne le nom du rôle correspondant au niveau (le plus haut applicable)."""
    applicable = [r for r in ROLES_CONFIG if level >= r["level"]]
    if not applicable:
        return None
    return applicable[-1]["name"]


async def get_or_create_member(db, user_id: int, guild_id: int) -> dict:
    doc = await db.members.find_one({"user_id": str(user_id), "guild_id": str(guild_id)})
    if doc is None:
        doc = {
            "user_id": str(user_id),
            "guild_id": str(guild_id),
            "xp": 0,
            "level": 0,
            "xp_messages": 0,
            "xp_vocal": 0,
            "solutions_données": 0,
            "solutions_reçues": 0,
            "vocal_session_start": None,
            "roles_actifs": [],
            "derniere_activite": now_utc(),
            "last_message_xp": None,
            "last_daily": None,
            "monthly_solutions": 0,
            "monthly_reset": datetime.now(timezone.utc).strftime("%Y-%m"),
            "total_messages": 0,
            "total_vocal_minutes": 0,
            "defis_resolus": 0,
            "defis_premier": 0,
        }
        await db.members.insert_one(doc)
    return doc


async def add_xp(db, user_id: int, guild_id: int, amount: int, source: str = "misc") -> tuple[int, int, int]:
    """
    Ajoute de l'XP à un membre.
    Retourne (new_xp, old_level, new_level).
    """
    doc = await get_or_create_member(db, user_id, guild_id)
    old_xp = doc["xp"]
    old_level = level_from_xp(old_xp)
    new_xp = old_xp + amount
    new_level = level_from_xp(new_xp)

    update = {
        "$set": {
            "xp": new_xp,
            "level": new_level,
            "derniere_activite": now_utc(),
        }
    }
    if source == "message":
        update["$inc"] = {"xp_messages": amount}
    elif source == "vocal":
        update["$inc"] = {"xp_vocal": amount}

    await db.members.update_one(
        {"user_id": str(user_id), "guild_id": str(guild_id)},
        update,
    )
    return new_xp, old_level, new_level