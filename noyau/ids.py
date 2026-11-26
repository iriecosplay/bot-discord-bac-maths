"""Tous les IDs / constantes du serveur repris tels quels de irie-bot/index.js."""
import os

# ── Mongo de l'ancien irie-bot (laissé en dur, autorisé par le propriétaire) ──
MONGO_URI_IRIE = os.environ.get(
    "MONGO_URI_IRIE",
    "mongodb+srv://yuzz:7XKDNcpIWFNN3pZu@cluster0.sstnqnv.mongodb.net/discord-bot?appName=Cluster0",
)
MONGO_DB_IRIE = "discord-bot"

BANNER = "https://i.pinimg.com/736x/ef/2d/5f/ef2d5fc6bf0b1fad5645a89a9424d317.jpg"

# Ancien bot irie (ID tiré de son token) : ses vieux panneaux sont remplacés.
ANCIEN_BOT_IRIE_ID = 1487190189003636936

# Bot exempté de l'automodération / anti-raid
AUTOMOD_IGNORED_BOT_ID = 1532702032925032620

# ── Anti-raid ─────────────────────────────────────────────────────────────────
RAID_FAST_THRESHOLD = 3
RAID_FAST_WINDOW = 3.0
RAID_SLOW_THRESHOLD = 5
RAID_SLOW_WINDOW = 5.0
COMMAND_COOLDOWN = 4.0

# ── Rôles ─────────────────────────────────────────────────────────────────────
UNVERIFIED_ROLE_ID = 1487372687671169124
MEMBER_ROLE_ID = 1487181268549374013
DONATOR_ROLE_ID = 1487182627407532112
VIP_ROLE_ID = 1487182930546790601
MOD_ROLE_ID = 1487379835239010354
ADMIN_ROLE_ID = 1496261745495245004
NOTIF_ROLE_ID = 1492571023550447666
OWNER_ID = 1213520541957496852
HELPER_SUP = 1495070939879313458
PRISON_ROLE_ID = 1499077729864257587
PRISON_CHANNEL_ID = 1502010145205387284
JUNIOR_MOD_ROLE_ID = 1487758469066133624
CM_ROLE_ID = 1502724737749749820

DISCUSSION_CATEGORY_ID = 1501633571348021419
PRIVATE_ACCESS_ROLE_IDS = [
    1499494894002241617, 1503488038536220686, 1503488046060798053,
    1503488042437050553, 1503488072384512112, 1503488060707307763,
]

SAINT_ROLE_ID = 1503883257157128205
STAFF_ROLE_ID = 1496261745495245004
PA_TEST_ROLE_ID = 1515002228874936541

FORBIDDEN_ROLE_ID = 1505547467490459751
ENSEIGNANT_ROLE_ID = 1506341518066188520
NEED_HELP_ROLE_ID = 1493642073067356270

WELCOME_CHANNEL_ID = 1487179769866092728
MAIN_GUILD_ID = 1487179769236689068

ROLES_CHANNEL_ID = 1487181193387577364
COLOR_CHANNEL_ID = 1499739574350385233
FORUM_CHANNEL_ID = 1495847597775126680
AVIS_CHANNEL_ID = 1496149092919673023
AVIS_LOG_CHANNEL_ID = 1504070941884551200
TICKET_PANEL_CHANNEL_ID = 1496295536221880454
TICKET_CATEGORY_ID = 1496295401555492864
TICKET_LOG_CHANNEL_ID = 1496296729471877183
VISIBILITY_CHANNEL_ID = 1499497496727126117
STATS_CATEGORY_ID = 1504480502273544202
LINKS_CHANNEL_ID = 1487181948563488768
DONATE_CHANNEL_ID = 1487197637685018695
TAG_CHANNEL_ID = 1507816860379254955

TICKET_SUPPORT_ROLE_IDS = [1487201604364009703, 1496261745495245004, MOD_ROLE_ID, ADMIN_ROLE_ID]

COLORS = [
    {"name": "Rouge", "hex": 0xFF3333, "emoji": "🔴"},
    {"name": "Orange", "hex": 0xFF9933, "emoji": "🟠"},
    {"name": "Jaune", "hex": 0xFFFF33, "emoji": "🟡"},
    {"name": "Vert", "hex": 0x33FF33, "emoji": "🟢"},
    {"name": "Menthe", "hex": 0x00FA9A, "emoji": "🍃"},
    {"name": "Bleu", "hex": 0x3333FF, "emoji": "🔵"},
    {"name": "Cyan", "hex": 0x00FFFF, "emoji": "🩵"},
    {"name": "Violet", "hex": 0x9933FF, "emoji": "🟣"},
    {"name": "Rose", "hex": 0xFF66CC, "emoji": "🌸"},
    {"name": "Gris", "hex": 0xA0A0A0, "emoji": "🌑"},
    {"name": "Blanc", "hex": 0xFFFFFF, "emoji": "⚪"},
    {"name": "Noir", "hex": 0x111111, "emoji": "⚫"},
]

QUATRIEME_ROLE_ID = 1487377932463767624
TROISIEME_ROLE_ID = 1487380314321063976
SECONDE_ROLE_ID = 1491392204558569492
PREMIERE_ROLE_ID = 1491158625023168662
TERMINALE_ROLE_ID = 1491134502867832893
SUP_ROLE_ID = 1487377488127459388

SUP_ROLES_CONFIG = [
    {"name": "Prépa", "emoji": "🔥", "description": "Classes préparatoires (CPGE)"},
    {"name": "BTS", "emoji": "🛠️", "description": "Brevet de Technicien Supérieur"},
    {"name": "Licence", "emoji": "📖", "description": "Licence universitaire (L1/L2/L3)"},
    {"name": "École d'ingé", "emoji": "⚙️", "description": "École d'ingénieurs"},
]

# id = int, ou "DYNAMIC_*" résolu au démarrage
CLASSE_ROLES = [
    {"label": "4ème Maths", "id": 1499364582869958687, "emoji": "📐"},
    {"label": "3ème Maths", "id": 1499364583737917462, "emoji": "📐"},
    {"label": "2nde Générale Maths", "id": 1499364584702738503, "emoji": "📗"},
    {"label": "1ère Spé Maths", "id": 1499364586221207614, "emoji": "📘"},
    {"label": "1ère (spécifique)", "id": 1499364913502486688, "emoji": "📘"},
    {"label": "Terminale Spé Maths", "id": 1499364587256942683, "emoji": "📙"},
    {"label": "Terminale Maths Complémentaires", "id": 1499364588246794250, "emoji": "📙"},
    {"label": "Terminale Maths Expertes", "id": 1499364589329190962, "emoji": "📙"},
    {"label": "Terminale (spécifique)", "id": 1499365008918839326, "emoji": "📙"},
    {"label": "2nde Technologique Maths", "id": 1499364590356529282, "emoji": "🔧"},
    {"label": "1ère STI2D Maths", "id": 1499364591291990108, "emoji": "🔧"},
    {"label": "Terminale STI2D Maths", "id": 1499364592219062272, "emoji": "🔧"},
    {"label": "1ère STL Maths", "id": 1499364592961196136, "emoji": "🔬"},
    {"label": "Terminale STL Maths", "id": 1499364593779081300, "emoji": "🔬"},
    {"label": "1ère STMG Maths", "id": 1499364595326779392, "emoji": "💼"},
    {"label": "Terminale STMG Maths", "id": 1499364596371427488, "emoji": "💼"},
    {"label": "2nde Bac Pro Maths", "id": 1499364597935898786, "emoji": "🏗️"},
    {"label": "1ère Bac Pro Maths", "id": 1499364599391322142, "emoji": "🏗️"},
    {"label": "Terminale Bac Pro Maths", "id": 1499364600519594084, "emoji": "🏗️"},
    {"label": "Supérieur", "id": 1499364601048072233, "emoji": "🎓"},
    {"label": "Prépa", "id": "DYNAMIC_PREPA", "emoji": "🔥"},
    {"label": "BTS", "id": "DYNAMIC_BTS", "emoji": "🛠️"},
    {"label": "Licence", "id": "DYNAMIC_LICENCE", "emoji": "📖"},
    {"label": "École d'ingé", "id": "DYNAMIC_INGE", "emoji": "⚙️"},
]

GROUPE1_IDS = {1499364582869958687, 1499364583737917462, 1499364584702738503, 1499364586221207614,
               1499364913502486688, 1499364587256942683, 1499364588246794250, 1499364589329190962,
               1499365008918839326}
GROUPE2_IDS = {1499364590356529282, 1499364591291990108, 1499364592219062272, 1499364592961196136,
               1499364593779081300, 1499364595326779392, 1499364596371427488, 1499364597935898786,
               1499364599391322142, 1499364600519594084}
SUP_GENERIQUE_ID = 1499364601048072233

CLASS_TO_HELPER = {
    QUATRIEME_ROLE_ID: 1493636195450884096,
    TROISIEME_ROLE_ID: 1493332365383172146,
    SECONDE_ROLE_ID: 1491392204558569492,
    PREMIERE_ROLE_ID: 1491158625023168662,
    TERMINALE_ROLE_ID: 1491134502867832893,
}
ALL_HELPER_IDS = list(CLASS_TO_HELPER.values())

VISIBILITY_ROLES = [
    {"id": 1499494884934029404, "label": "4ème", "emoji": "📐", "description": "Salons réservés aux élèves de 4ème"},
    {"id": 1499494885718364202, "label": "3ème", "emoji": "📐", "description": "Salons réservés aux élèves de 3ème"},
    {"id": 1499494886884380842, "label": "2nde Générale", "emoji": "📗", "description": "Salons réservés aux élèves de 2nde Générale"},
    {"id": 1499494888708898978, "label": "1ère Spé Maths", "emoji": "📘", "description": "Salons réservés aux élèves de 1ère Spé Maths"},
    {"id": 1499494892098027641, "label": "1ère (spécifique)", "emoji": "📘", "description": "Salons réservés aux filières 1ère spécifiques"},
    {"id": 1499494889828913174, "label": "Terminale Spé Maths", "emoji": "📙", "description": "Salons réservés aux élèves de Terminale Spé Maths"},
    {"id": 1499494890814312620, "label": "Terminale Maths Complémentaires", "emoji": "📙", "description": "Salons réservés aux élèves de Terminale Maths Complémentaires"},
    {"id": 1499494893037289493, "label": "Maths Techno (toutes années)", "emoji": "🔧", "description": "Salons réservés aux filières technologiques"},
    {"id": 1499494894002241617, "label": "Supérieur", "emoji": "🎓", "description": "Salons réservés aux étudiants du supérieur"},
    {"id": "DYNAMIC_VIS_PREPA", "label": "Prépa", "emoji": "🔥", "description": "Salons réservés aux étudiants en classe prépa"},
    {"id": "DYNAMIC_VIS_BTS", "label": "BTS", "emoji": "🛠️", "description": "Salons réservés aux étudiants en BTS"},
    {"id": "DYNAMIC_VIS_LICENCE", "label": "Licence", "emoji": "📖", "description": "Salons réservés aux étudiants en Licence"},
    {"id": "DYNAMIC_VIS_INGE", "label": "École d'ingé", "emoji": "⚙️", "description": "Salons réservés aux étudiants en école d'ingénieurs"},
]

SUP_VISIBILITY_ROLES_CONFIG = [
    {"name": "Prépa", "dynamic_key": "DYNAMIC_VIS_PREPA"},
    {"name": "BTS", "dynamic_key": "DYNAMIC_VIS_BTS"},
    {"name": "Licence", "dynamic_key": "DYNAMIC_VIS_LICENCE"},
    {"name": "École d'ingé", "dynamic_key": "DYNAMIC_VIS_INGE"},
]

# ── Anti-spam ─────────────────────────────────────────────────────────────────
CROSS_MSG_THRESHOLD, CROSS_MSG_WINDOW = 3, 10.0
SAME_CHAN_THRESHOLD, SAME_CHAN_WINDOW = 8, 5.0
DUP_MSG_THRESHOLD, DUP_MSG_WINDOW = 3, 10.0
EVERYONE_THRESHOLD, EVERYONE_WINDOW = 2, 10.0
MENTION_THRESHOLD, MENTION_WINDOW = 6, 8.0
SANCTION_THRESHOLD, SANCTION_WINDOW = 5, 10.0

BL_BAN_THRESHOLD, BL_BAN_WINDOW = 5, 30.0
BL_SALON_THRESHOLD, BL_SALON_WINDOW = 3, 10.0

AVIS_PER_PAGE = 5
TOPAVIS_PER_PAGE = 10
