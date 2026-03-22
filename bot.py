import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import random
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import json

# Import du générateur de carte stats
try:
    from stats_card import make_stats_card
    STATS_CARD_ENABLED = True
except ImportError:
    STATS_CARD_ENABLED = False
    print("⚠️  stats_card.py introuvable — /stats désactivé")

try:
    from welcome_card import make_welcome_gif
    WELCOME_GIF_ENABLED = True
except ImportError:
    WELCOME_GIF_ENABLED = False
    print("⚠️  welcome_card.py introuvable — GIF désactivé")

try:
    from levelup_card import make_levelup_gif
    LEVELUP_GIF_ENABLED = True
except ImportError:
    LEVELUP_GIF_ENABLED = False
    print("⚠️  levelup_card.py introuvable — GIF level-up désactivé")

load_dotenv()

# ── Persistance des données ───────────────────────────────────
# Sur Railway le volume est monté sur /app/data, sinon on utilise le dossier local
_DATA_DIR = "/app/data" if os.path.isdir("/app/data") else os.path.dirname(os.path.abspath(__file__))
DATA_FILE  = os.path.join(_DATA_DIR, "data.json")
_data_dirty = False

# ── Variables de config (écrasées par load_data au démarrage) ──
CONFESSION_CHANNEL_ID: int  = 0
MARVEL_CHANNEL_ID:     int  = 0
DC_CHANNEL_ID:         int  = 0
confession_counter:    int  = 0
BOOST_CHANNEL_ID:      int  = 0      # salon où envoyer les messages de boost
reaction_roles: dict = {}          # {msg_id: {emoji: role_id}}
REGLEMENT_MSG_ID:     int = 0      # ID du message règlement
REGLEMENT_CHANNEL_ID: int = 0      # ID du salon règlement
gacha_profiles: dict[int, dict] = {}
economy_profiles: dict[int, dict] = {}

def save_data():
    """Sauvegarde les données persistantes du bot dans data.json."""
    global _data_dirty
    try:
        payload = {
            "xp_data":        {str(k): v for k, v in xp_data.items()},
            "warns":          {str(k): v for k, v in warns.items()},
            "reaction_roles": {str(k): v for k, v in reaction_roles.items()},
            "open_tickets":   {str(k): v for k, v in open_tickets.items()},
            "announced_games": list(announced_games),
            "comics_last_posted": comics_last_posted,
            "gacha_profiles": {str(k): v for k, v in gacha_profiles.items()},
            "economy_profiles": {str(k): v for k, v in economy_profiles.items()},
            "config": {
                "CONFESSION_CHANNEL_ID": CONFESSION_CHANNEL_ID,
                "BOOST_CHANNEL_ID":       BOOST_CHANNEL_ID,
                "confession_counter":    confession_counter,
                "WELCOME_CHANNEL_ID":    WELCOME_CHANNEL_ID,
                "GOODBYE_CHANNEL_ID":    GOODBYE_CHANNEL_ID,
                "LOG_CHANNEL_ID":        LOG_CHANNEL_ID,
                "FREE_GAMES_CHANNEL_ID": FREE_GAMES_CHANNEL_ID,
                "LEVELUP_CHANNEL_ID":    LEVELUP_CHANNEL_ID,
                "TICKET_CATEGORY_ID":    TICKET_CATEGORY_ID,
                "AUTO_ROLES":            AUTO_ROLES,
                "LEVEL_ROLES":           {str(k): v for k, v in LEVEL_ROLES.items()},
                "REGLEMENT_MSG_ID":      REGLEMENT_MSG_ID,
                "MARVEL_CHANNEL_ID":     MARVEL_CHANNEL_ID,
                "DC_CHANNEL_ID":         DC_CHANNEL_ID,
                "REGLEMENT_CHANNEL_ID":  REGLEMENT_CHANNEL_ID,
            }
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _data_dirty = False
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde : {e}")

def mark_data_dirty():
    global _data_dirty
    _data_dirty = True


def build_welcome_dm_embed(member: discord.Member, *, preview: bool = False) -> discord.Embed:
    guild = member.guild
    title = "✉️ Aperçu du message de bienvenue" if preview else "🍺 Bienvenue à La Taverne"
    embed = discord.Embed(
        title=title,
        description=(
            f"Salut {member.mention}, bienvenue sur **{guild.name}**.\n\n"
            "Avant de commencer, prends 2 minutes pour bien t'installer dans la Taverne."
        ),
        color=0x8B0000,
        timestamp=datetime.utcnow()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(
        name="✅ À faire en arrivant",
        value=(
            "• Lire le règlement et cocher la réaction demandée\n"
            "• Accepter les règles pour débloquer l'accès à tous les salons\n"
            "• Parcourir les catégories et salons importants\n"
            "• Choisir une couleur pour ton rôle et tes notifications si besoin"
        ),
        inline=False
    )
    embed.add_field(
        name="📜 Conseil",
        value="Commence par le salon règlement, valide la réaction demandée puis découvre tranquillement les différentes catégories du serveur.",
        inline=False
    )
    footer = "Aperçu admin du MP de bienvenue" if preview else "Bonne installation dans la Taverne"
    embed.set_footer(text=footer, icon_url=guild.icon.url if guild.icon else None)
    return embed

def load_data():
    """Charge toutes les données depuis data.json au démarrage"""
    global xp_data, warns, reaction_roles
    global open_tickets, announced_games, comics_last_posted
    global gacha_profiles, economy_profiles
    global _data_dirty
    global CONFESSION_CHANNEL_ID, confession_counter
    global WELCOME_CHANNEL_ID, GOODBYE_CHANNEL_ID, LOG_CHANNEL_ID
    global FREE_GAMES_CHANNEL_ID, LEVELUP_CHANNEL_ID, TICKET_CATEGORY_ID
    global AUTO_ROLES, LEVEL_ROLES
    global REGLEMENT_MSG_ID, REGLEMENT_CHANNEL_ID
    global MARVEL_CHANNEL_ID, DC_CHANNEL_ID
    global BOOST_CHANNEL_ID
    if not os.path.exists(DATA_FILE):
        print("ℹ️ Aucun fichier data.json trouvé — démarrage à zéro.")
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        xp_data        = {int(k): v for k, v in payload.get("xp_data", {}).items()}
        warns          = {int(k): v for k, v in payload.get("warns",   {}).items()}
        reaction_roles = {int(k): v for k, v in payload.get("reaction_roles", {}).items()}
        open_tickets   = {int(k): v for k, v in payload.get("open_tickets", {}).items()}
        announced_games = set(payload.get("announced_games", []))
        comics_last_posted = payload.get("comics_last_posted", {})
        gacha_profiles = {int(k): v for k, v in payload.get("gacha_profiles", {}).items()}
        economy_profiles = {int(k): v for k, v in payload.get("economy_profiles", {}).items()}
        cfg = payload.get("config", {})
        CONFESSION_CHANNEL_ID = cfg.get("CONFESSION_CHANNEL_ID", CONFESSION_CHANNEL_ID)
        confession_counter    = cfg.get("confession_counter",    confession_counter)
        WELCOME_CHANNEL_ID    = cfg.get("WELCOME_CHANNEL_ID",    WELCOME_CHANNEL_ID)
        GOODBYE_CHANNEL_ID    = cfg.get("GOODBYE_CHANNEL_ID",    GOODBYE_CHANNEL_ID)
        LOG_CHANNEL_ID        = cfg.get("LOG_CHANNEL_ID",        LOG_CHANNEL_ID)
        FREE_GAMES_CHANNEL_ID = cfg.get("FREE_GAMES_CHANNEL_ID", FREE_GAMES_CHANNEL_ID)
        LEVELUP_CHANNEL_ID    = cfg.get("LEVELUP_CHANNEL_ID",    LEVELUP_CHANNEL_ID)
        TICKET_CATEGORY_ID    = cfg.get("TICKET_CATEGORY_ID",    TICKET_CATEGORY_ID)
        AUTO_ROLES            = cfg.get("AUTO_ROLES",            AUTO_ROLES)
        LEVEL_ROLES           = {int(k): v for k, v in cfg.get("LEVEL_ROLES", {}).items()}
        BOOST_CHANNEL_ID      = cfg.get("BOOST_CHANNEL_ID",      BOOST_CHANNEL_ID)
        REGLEMENT_MSG_ID      = cfg.get("REGLEMENT_MSG_ID",      REGLEMENT_MSG_ID)
        REGLEMENT_CHANNEL_ID  = cfg.get("REGLEMENT_CHANNEL_ID",  REGLEMENT_CHANNEL_ID)
        MARVEL_CHANNEL_ID     = cfg.get("MARVEL_CHANNEL_ID",     MARVEL_CHANNEL_ID)
        DC_CHANNEL_ID         = cfg.get("DC_CHANNEL_ID",         DC_CHANNEL_ID)
        _data_dirty = False
        print(f"✅ Données chargées : {len(xp_data)} joueurs, {len(warns)} avertissements")
    except Exception as e:
        print(f"⚠️ Erreur chargement data.json : {e}")


# ════════════════════════════════════════════════════════════════
#  📋  SOMMAIRE DES SECTIONS
# ════════════════════════════════════════════════════════════════
#  [1]  ⚙️  Configuration & Variables
#  [2]  🤖  Intents & Bot
#  [3]  🔧  Utilitaires & Données (XP, save/load JSON)
#  [4]  🟢  Démarrage (on_ready)
#  [5]  👋  Bienvenue & Au revoir
#  [6]  ⭐  Système XP & Niveaux
#  [7]  🛡️  Anti-spam
#  [8]  ⚔️  Modération  (/ban /kick /mute /warn)
#  [9]  🎫  Système de tickets
#  [10] 🎭  Reaction roles
#  [11] 🤫  Confession anonyme
#  [12] 🔩  Commandes admin — Configuration
#  [13] 🎮  Mini-jeux
#  [14] 🎁  Jeux gratuits
#  [15] 🐺  Jeu — Loup-Garou
#  [16] 🔴  Jeu — Puissance 4
#  [17] 📊  Compteurs de membres
#  [18] 📈  Statistiques serveur
#  [19] ❌  Gestion des erreurs
#  [20] 🚀  Lancement
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
#  ⚙️  [1] CONFIGURATION & VARIABLES
# ════════════════════════════════════════════════════════════════
TOKEN                  = os.getenv("DISCORD_TOKEN", "VOTRE_TOKEN_ICI")
WELCOME_CHANNEL_ID     = int(os.getenv("WELCOME_CHANNEL_ID", 0))
GOODBYE_CHANNEL_ID     = int(os.getenv("GOODBYE_CHANNEL_ID", 0))
FREE_GAMES_CHANNEL_ID  = int(os.getenv("FREE_GAMES_CHANNEL_ID", 0))
LOG_CHANNEL_ID         = int(os.getenv("LOG_CHANNEL_ID", 0))
TICKET_CATEGORY_ID     = int(os.getenv("TICKET_CATEGORY_ID", 0))
AUTO_ROLE_ID           = int(os.getenv("AUTO_ROLE_ID", 0))
FREE_GAMES_CHECK_INTERVAL = 6
LEVELUP_CHANNEL_ID     = int(os.getenv("LEVELUP_CHANNEL_ID", 0))

# ── Salons compteurs (catégorie Membres)
COUNTER_MEMBERS_ID = int(os.getenv("COUNTER_MEMBERS_ID", 0))
COUNTER_BOTS_ID    = int(os.getenv("COUNTER_BOTS_ID", 0))
COUNTER_CREATED_ID = int(os.getenv("COUNTER_CREATED_ID", 0))

# Image de la taverne — remplace par ton URL Discord CDN
TAVERNE_IMAGE_URL = "https://i.imgur.com/placeholder.jpg"

# ── Système de niveaux
XP_PER_MESSAGE    = 15
XP_COOLDOWN       = 60   # secondes entre deux gains d'XP
LEVEL_ROLES: dict[int, int]   = {}   # {niveau: role_id}
xp_data:      dict[int, dict]  = {}   # {user_id: {xp, level, msgs_history, voice_history...}}
xp_cooldowns: dict[int, float] = {}
voice_join_time: dict[int, float] = {}  # {user_id: timestamp join vocal}

# ── Cooldowns mini-jeux
game_cooldowns: dict[str, float] = {}

# ── Tickets ouverts {user_id: channel_id}
open_tickets: dict[int, int] = {}

# ── Jeux déjà annoncés
announced_games: set = set()

# ── Système de modération
warns: dict[int, list] = {}  # {user_id: [{raison, mod, date}]}

# ── Gacha comics / personnages
GACHA_WINDOW_SECONDS = 3600
GACHA_PULLS_PER_HOUR = 10
GACHA_PITY_THRESHOLD = 20
DISBOARD_BOT_ID = 302050872383242240

# ── Quêtes & économie
DAILY_QUEST_TEMPLATES = [
    {"id": "daily_messages", "label": "Envoyer 20 messages", "type": "messages", "target": 20, "reward": 80, "scope": "daily"},
    {"id": "daily_voice", "label": "Passer 30 min en vocal", "type": "voice_seconds", "target": 30 * 60, "reward": 120, "scope": "daily"},
    {"id": "daily_gacha", "label": "Faire 3 pulls gacha", "type": "gacha_pulls", "target": 3, "reward": 70, "scope": "daily"},
]
WEEKLY_QUEST_TEMPLATES = [
    {"id": "weekly_messages", "label": "Envoyer 120 messages", "type": "messages", "target": 120, "reward": 350, "scope": "weekly"},
    {"id": "weekly_voice", "label": "Passer 3h en vocal", "type": "voice_seconds", "target": 3 * 3600, "reward": 450, "scope": "weekly"},
    {"id": "weekly_gacha", "label": "Faire 12 pulls gacha", "type": "gacha_pulls", "target": 12, "reward": 250, "scope": "weekly"},
]
SHOP_ITEMS = {
    "marvel_reset": {"label": "Reset Marvel", "price": 250, "description": "Remet ton quota Marvel à 0/10"},
    "dc_reset": {"label": "Reset DC", "price": 250, "description": "Remet ton quota DC à 0/10"},
    "all_reset": {"label": "Reset total", "price": 450, "description": "Remet Marvel et DC à 0/10"},
    "marvel_pity": {"label": "Boost pity Marvel", "price": 300, "description": "Ajoute +3 pity sur Marvel"},
    "dc_pity": {"label": "Boost pity DC", "price": 300, "description": "Ajoute +3 pity sur DC"},
}

# ════════════════════════════════════════════════════════════════
#  🤖  [2] INTENTS & BOT
# ════════════════════════════════════════════════════════════════
intents = discord.Intents.all()
bot  = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="🍺 Gardienne de La Taverne — https://sienna-bot.up.railway.app"
)
tree = bot.tree
game_group = app_commands.Group(name="jeu", description="Toutes les commandes de jeux")

# ════════════════════════════════════════════════════════════════
#  🔧  [3] UTILITAIRES & DONNÉES
# ════════════════════════════════════════════════════════════════
def xp_needed(level: int) -> int:
    """
    Formule progressive — douce au début, difficile ensuite.
    Niveau 1  →   226 XP  (~15 msgs)
    Niveau 5  →  1175 XP  (~78 msgs)
    Niveau 10 →  2918 XP  (~194 msgs)
    Niveau 20 →  7698 XP  (~513 msgs)
    Niveau 50 → 29000 XP  (~1933 msgs)
    Niveau 80 → 63000 XP  (~4200 msgs)
    """
    return int(80 * (level + 1) ** 1.5)

def get_user_data(user_id: int) -> dict:
    if user_id not in xp_data:
        xp_data[user_id] = {
            "xp": 0, "level": 0,
            "msgs_history": [],   # list of timestamps (14 jours)
            "voice_history": [],  # list of (start, end) tuples
            "top_channel": {}, "top_voice": {},
        }
    d = xp_data[user_id]
    # Ensure new fields exist for old entries
    d.setdefault("msgs_history", [])
    d.setdefault("voice_history", [])
    d.setdefault("top_channel", {})
    d.setdefault("top_voice", {})
    return d

def get_stats_for_days(user_id: int, days: int) -> dict:
    """Calcule msgs et heures vocales sur N derniers jours."""
    d   = get_user_data(user_id)
    now = datetime.utcnow().timestamp()
    cutoff = now - days * 86400
    msgs  = sum(1 for t in d["msgs_history"] if t >= cutoff)
    voice = sum(
        min(end, now) - max(start, cutoff)
        for start, end in d["voice_history"]
        if end >= cutoff
    ) / 3600
    return {"msgs": msgs, "voice": round(voice, 1)}

def get_chart_data(user_id: int) -> dict:
    """Retourne 14 points journaliers pour msgs et vocal."""
    d   = get_user_data(user_id)
    now = datetime.utcnow()
    chart_msgs  = []
    chart_voice = []
    for day_offset in range(13, -1, -1):
        day_start = (now - timedelta(days=day_offset)).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        day_end   = day_start + 86400
        m = sum(1 for t in d["msgs_history"] if day_start <= t < day_end)
        v = sum(
            min(end, day_end) - max(start, day_start)
            for start, end in d["voice_history"]
            if end >= day_start and start < day_end
        ) / 3600
        chart_msgs.append(m)
        chart_voice.append(round(v, 1))
    return {"chart_msgs": chart_msgs, "chart_voice": chart_voice}

def get_rank(guild_id_unused, user_id: int, mode: str) -> int:
    """Retourne le classement msgs (mode=msg) ou vocal (mode=voice) sur 14j."""
    now = datetime.utcnow().timestamp()
    cutoff = now - 14 * 86400
    scores = []
    for uid, d in xp_data.items():
        if mode == "msg":
            scores.append((uid, sum(1 for t in d.get("msgs_history",[]) if t >= cutoff)))
        else:
            total = sum(
                min(end, now) - max(start, cutoff)
                for start, end in d.get("voice_history",[])
                if end >= cutoff
            )
            scores.append((uid, total))
    scores.sort(key=lambda x: x[1], reverse=True)
    for i, (uid, _) in enumerate(scores, 1):
        if uid == user_id:
            return i
    return len(scores)

async def send_log(guild: discord.Guild, embed: discord.Embed):
    if not LOG_CHANNEL_ID:
        return
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def _message_interaction_user_id(message: discord.Message) -> int:
    interaction_meta = getattr(message, "interaction_metadata", None)
    if interaction_meta:
        user = getattr(interaction_meta, "user", None)
        if user:
            return int(user.id)
    interaction = getattr(message, "interaction", None)
    if interaction:
        user = getattr(interaction, "user", None)
        if user:
            return int(user.id)
    return 0

def _extract_user_id_from_bump_message(message: discord.Message) -> int:
    import re as _re

    user_id = _message_interaction_user_id(message)
    if user_id:
        return user_id

    if message.mentions:
        for member in message.mentions:
            if not member.bot:
                return int(member.id)

    chunks = [message.content or ""]
    for embed in message.embeds:
        chunks.extend(
            [
                embed.title or "",
                embed.description or "",
                embed.author.name if embed.author else "",
                embed.footer.text if embed.footer else "",
            ]
        )
    joined = " ".join(chunks)
    mention_match = _re.search(r"<@!?(\d{15,22})>", joined)
    if mention_match:
        return int(mention_match.group(1))

    return 0

def _message_interaction_name(message: discord.Message) -> str:
    interaction_meta = getattr(message, "interaction_metadata", None)
    if interaction_meta:
        name = getattr(interaction_meta, "name", "") or ""
        if name:
            return str(name).lower()
    interaction = getattr(message, "interaction", None)
    if interaction:
        name = getattr(interaction, "name", "") or ""
        if name:
            return str(name).lower()
    return ""

def _is_confirmed_bump_message(message: discord.Message) -> bool:
    if not message.guild or not message.author.bot:
        return False
    interaction_name = _message_interaction_name(message)

    chunks = [message.content or ""]
    for embed in message.embeds:
        chunks.extend(
            [
                embed.title or "",
                embed.description or "",
                embed.footer.text if embed.footer else "",
            ]
        )
    content = " ".join(chunks).lower()
    from_bump_bot = (
        message.author.id == DISBOARD_BOT_ID
        or "disboard" in (message.author.name or "").lower()
        or "bump" in interaction_name
        or "disboard" in content
    )
    if not from_bump_bot:
        return False
    success_markers = [
        "bump done",
        "server bumped",
        "bien été envoyé",
        "a été envoyé",
        "successfully bumped",
        "succès",
        "merci d'avoir bump",
        "thanks for bumping",
        "bump effectué",
        "bump effectué avec succès",
        "le serveur a été bump",
        "the server has been bumped",
    ]
    cooldown_markers = [
        "can be bumped again",
        "essayez à nouveau",
        "try again",
        "wait another",
        "patiente",
        "cooldown",
        "you can bump again",
        "vous pourrez bump",
        "encore attendre",
    ]
    return any(marker in content for marker in success_markers) and not any(marker in content for marker in cooldown_markers)

async def _handle_bump_success(message: discord.Message) -> bool:
    if not _is_confirmed_bump_message(message):
        return False

    user_id = _extract_user_id_from_bump_message(message)
    if not user_id:
        return False

    _gacha_reset_user_counters(user_id)
    member = message.guild.get_member(user_id)
    mention = member.mention if member else f"<@{user_id}>"

    confirm = discord.Embed(
        title="🚀 Bump confirmé",
        description=(
            f"{mention} a bump le serveur.\n"
            f"Les compteurs gacha **Marvel** et **DC** ont été remis à **0/{GACHA_PULLS_PER_HOUR}**."
        ),
        color=0x57F287,
        timestamp=datetime.utcnow(),
    )
    try:
        await message.channel.send(embed=confirm)
    except Exception:
        pass

    log = discord.Embed(title="🚀 Reset gacha après bump", color=0x57F287, timestamp=datetime.utcnow())
    log.add_field(name="Membre", value=f"{mention} (`{user_id}`)", inline=False)
    log.add_field(name="Action", value=f"Quotas Marvel/DC réinitialisés à 0/{GACHA_PULLS_PER_HOUR}", inline=False)
    await send_log(message.guild, log)
    return True

def check_game_cooldown(user_id: int, game: str, seconds: int) -> float:
    key  = f"{game}_{user_id}"
    now  = datetime.utcnow().timestamp()
    left = seconds - (now - game_cooldowns.get(key, 0))
    if left <= 0:
        game_cooldowns[key] = now
        return 0
    return left

# ════════════════════════════════════════════════════════════════
#  🟢  [4] DÉMARRAGE (on_ready)
# ════════════════════════════════════════════════════════════════
@tasks.loop(minutes=5)
async def save_loop():
    """Sauvegarde automatique toutes les 5 minutes"""
    if _data_dirty:
        save_data()


@bot.event
async def on_ready():
    load_data()

    # ── Enregistrer les Views persistantes (boutons qui survivent au redémarrage) ──
    bot.add_view(TicketSelectView())   # Panel tickets
    bot.add_view(TicketView())         # Boutons ticket (prendre en charge + fermer)
    bot.add_view(CouleurRolesView())   # Panel rôles couleurs
    bot.add_view(NotifRolesView())     # Panel rôles notifications
    print("✅  Views persistantes enregistrées (tickets, rôles)")

    print(f"✅  Connecté : {bot.user}  (ID: {bot.user.id})")

    # ── Sync intelligent — uniquement si les commandes ont changé ──
    try:
        # Calcule un hash des commandes actuelles
        import hashlib
        cmd_names  = sorted(c.name for c in tree.get_commands())
        cmd_hash   = hashlib.md5(str(cmd_names).encode()).hexdigest()
        hash_file  = os.path.join(_DATA_DIR, "cmd_hash.txt")

        last_hash = ""
        try:
            with open(hash_file, "r") as f:
                last_hash = f.read().strip()
        except FileNotFoundError:
            pass

        if cmd_hash != last_hash:
            synced = await tree.sync()
            with open(hash_file, "w") as f:
                f.write(cmd_hash)
            print(f"🔄  {len(synced)} commandes slash synchronisées (nouveautés détectées)")
            print(f"   Commandes : {', '.join(cmd_names)}")
        else:
            # Vérifier aussi le nombre réel de commandes enregistrées sur Discord
            registered = await bot.http.get_global_commands(bot.user.id)
            if len(registered) != len(cmd_names):
                print(f"⚠️  Discord a {len(registered)} cmds, local a {len(cmd_names)} — resync forcée")
                synced = await tree.sync()
                with open(hash_file, "w") as f:
                    f.write(cmd_hash)
                print(f"🔄  {len(synced)} commandes slash re-synchronisées")
            else:
                print(f"✅  Commandes slash déjà à jour — pas de sync nécessaire ({len(cmd_names)} cmds)")
    except Exception as e:
        print(f"⚠️ Erreur sync : {e}")

    if not save_loop.is_running():
        save_loop.start()
    if not check_free_games.is_running():
        check_free_games.start()
    if not counter_loop.is_running():
        counter_loop.start()
    if (MARVEL_CHANNEL_ID or DC_CHANNEL_ID) and not comics_auto_loop.is_running():
        comics_auto_loop.start()
    # Cache des invitations pour tracker "qui a invité qui"
    bot._invite_cache = {}
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            for inv in invites:
                bot._invite_cache[inv.code] = inv.uses
        except Exception:
            pass
    for guild in bot.guilds:
        await update_counters(guild)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="la taverne 🍺 | sienna-bot.up.railway.app"
        )
    )

# ════════════════════════════════════════════════════════════════
#  👋  [5] BIENVENUE & AU REVOIR
# ════════════════════════════════════════════════════════════════
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    # Qui a invité ?
    inviter      = None
    invite_code  = None
    invite_uses  = None
    try:
        invites_after = await guild.invites()
        if hasattr(bot, "_invite_cache"):
            for invite in invites_after:
                cached = bot._invite_cache.get(invite.code)
                if cached is not None and invite.uses > cached:
                    inviter     = invite.inviter
                    invite_code = invite.code
                    invite_uses = invite.uses
                    break
        bot._invite_cache = {inv.code: inv.uses for inv in invites_after}
    except Exception:
        pass

    # Âge du compte en jours
    account_age_days = (datetime.utcnow() - member.created_at.replace(tzinfo=None)).days
    new_account_warn = " ⚠️ **Compte récent !**" if account_age_days < 7 else ""

    # Log d'arrivée détaillé
    log = discord.Embed(
        title=f"📥 Nouveau membre{new_account_warn}",
        color=0x57F287 if account_age_days >= 7 else 0xFFA500,
        timestamp=datetime.utcnow()
    )
    log.set_thumbnail(url=member.display_avatar.url)
    log.add_field(name="👤 Membre",       value=f"{member.mention} (`{member.id}`)",                    inline=False)
    log.add_field(name="📛 Pseudo",       value=str(member),                                            inline=True)
    log.add_field(name="🎂 Compte créé",  value=f"<t:{int(member.created_at.timestamp())}:R> ({account_age_days}j)", inline=True)
    log.add_field(name="👥 Total",        value=f"{guild.member_count} membres",                        inline=True)
    if inviter:
        log.add_field(name="✉️ Invité par",      value=f"{inviter.mention} (`{inviter.id}`)", inline=True)
        log.add_field(name="🔗 Code",            value=f"`{invite_code}`",                   inline=True)
        log.add_field(name="📊 Utilisations",    value=f"{invite_uses} fois",                inline=True)
    else:
        log.add_field(name="✉️ Invité par", value="Inconnu (lien vanity ou DM ?)", inline=False)
    # Auto-rôles
    for role_id in AUTO_ROLES:
        role = guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-rôle")
            except Exception:
                pass

    dm_sent = await send_dm(member, build_welcome_dm_embed(member))
    log.add_field(name="📩 MP bienvenue", value="✅ Envoyé" if dm_sent else "❌ DMs fermés", inline=True)
    log.set_footer(text=f"ID : {member.id}")
    await send_log(guild, log)
    await update_counters(guild)

    # Message de bienvenue
    ch_id = WELCOME_CHANNEL_ID
    ch = guild.get_channel(ch_id) if ch_id else None
    if ch:
        try:
            from welcome_card import make_welcome_gif
            buf  = await make_welcome_gif(member, is_welcome=True)
            file = discord.File(buf, filename="bienvenue.gif")
            embed = discord.Embed(
                description=(
                    f"Les portes s'ouvrent pour {member.mention} ! 🍺\n\n"
                    "┣ ✅ Réagis au **règlement** pour accéder à tous les salons\n"
                    "┣ 🧭 Parcours les **catégories et salons**\n"
                    "┗ 🎨 Choisis une **couleur de rôle** et tes rôles"
                ),
                color=0x8B0000
            )
            embed.set_image(url="attachment://bienvenue.gif")
            embed.set_footer(text=f"🍻 Aventurier #{guild.member_count}", icon_url=guild.icon.url if guild.icon else None)
            await ch.send(embed=embed, file=file)
        except Exception:
            embed = discord.Embed(
                title="⚔️ Bienvenue à la Taverne !",
                description=(
                    f"Heureux de t'accueillir {member.mention} ! 🍺\n\n"
                    "Merci de valider la réaction du règlement pour débloquer tous les salons, puis de parcourir les catégories et choisir une couleur de rôle avant de participer."
                ),
                color=0x8B0000
            )
            await ch.send(embed=embed)

    # Mention dans le salon règlement (supprimée après 10 min) — en tâche async pour ne pas bloquer
    if REGLEMENT_CHANNEL_ID:
        reglement_ch = guild.get_channel(REGLEMENT_CHANNEL_ID)
        if reglement_ch:
            async def _mention_and_delete(ch, m):
                try:
                    msg = await ch.send(
                        f"👋 Bienvenue {m.mention} ! "
                        f"Merci de lire et accepter les règles du serveur avant de participer. 📜"
                    )
                    await asyncio.sleep(600)  # 10 minutes
                    await msg.delete()
                except Exception:
                    pass
            asyncio.create_task(_mention_and_delete(reglement_ch, member))

@bot.event
async def on_member_remove(member: discord.Member):
    # Au revoir
    ch = member.guild.get_channel(GOODBYE_CHANNEL_ID)
    if ch:
        try:
            from welcome_card import make_welcome_gif
            buf  = await make_welcome_gif(member, is_welcome=False)
            file = discord.File(buf, filename="aurevoir.gif")
            embed = discord.Embed(
                description=f"*On espère vous revoir bientôt... peut-être.* 🍂",
                color=0x2C2C2C, timestamp=datetime.utcnow()
            )
            embed.set_image(url="attachment://aurevoir.gif")
            embed.set_footer(
                text=f"Il reste {member.guild.member_count} aventuriers",
                icon_url=member.guild.icon.url if member.guild.icon else None
            )
            await ch.send(embed=embed, file=file)
        except Exception:
            embed = discord.Embed(
                title=f"🕯️ {member.display_name} quitte la taverne...",
                description="*On espère vous revoir bientôt... peut-être.* 🍂",
                color=0x2C2C2C, timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await ch.send(embed=embed)
    # Log
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    log = discord.Embed(title="📤 Membre parti", color=0xED4245, timestamp=datetime.utcnow())
    log.set_thumbnail(url=member.display_avatar.url)
    log.add_field(name="Membre", value=f"{member} (`{member.id}`)")
    log.add_field(name="Rôles", value=", ".join(roles) if roles else "Aucun", inline=False)
    log.set_footer(text=f"ID : {member.id}")
    await send_log(member.guild, log)
    await update_counters(member.guild)
@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    embed = discord.Embed(title="🗑️ Message supprimé", color=0xFF6B6B, timestamp=datetime.utcnow())
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    embed.add_field(name="✍️ Auteur",  value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
    embed.add_field(name="📌 Salon",   value=message.channel.mention, inline=True)
    embed.add_field(name="🕐 Envoyé",  value=f"<t:{int(message.created_at.timestamp())}:R>", inline=True)
    if message.content:
        contenu = message.content
        # Tronquer proprement
        if len(contenu) > 1020:
            contenu = contenu[:1020] + "..."
        embed.add_field(name="📝 Contenu", value=f"```{contenu}```", inline=False)
    if message.embeds:
        embed.add_field(name="🖼️ Embeds", value=f"{len(message.embeds)} embed(s) dans le message", inline=False)
    if message.attachments:
        att_list = "\n".join(f"• [{a.filename}]({a.url})" for a in message.attachments)
        embed.add_field(name="📎 Pièces jointes", value=att_list[:1024], inline=False)
        if message.attachments[0].content_type and message.attachments[0].content_type.startswith("image"):
            embed.set_image(url=message.attachments[0].proxy_url)
    if message.reference:
        embed.add_field(name="↩️ Réponse à", value=f"Message ID `{message.reference.message_id}`", inline=False)
    # Qui a supprimé (audit log)
    try:
        entries = [e async for e in message.guild.audit_logs(limit=1, action=discord.AuditLogAction.message_delete)]
        if entries and entries[0].target.id == message.author.id:
            embed.add_field(name="🔨 Supprimé par", value=f"{entries[0].user.mention} (`{entries[0].user.id}`)", inline=False)
    except Exception:
        pass
    embed.set_footer(text=f"Message ID : {message.id} • User ID : {message.author.id}")
    await send_log(message.guild, embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    embed = discord.Embed(title="✏️ Message modifié", color=0xFFA500, timestamp=datetime.utcnow())
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    embed.add_field(name="✍️ Auteur", value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
    embed.add_field(name="📌 Salon",  value=before.channel.mention, inline=True)
    embed.add_field(name="🕐 Envoyé", value=f"<t:{int(before.created_at.timestamp())}:R>", inline=True)
    avant = before.content[:512] if before.content else "*vide*"
    apres = after.content[:512]  if after.content  else "*vide*"
    embed.add_field(name="📝 Avant", value=f"```{avant}```", inline=False)
    embed.add_field(name="✅ Après", value=f"```{apres}```", inline=False)
    embed.add_field(name="🔗 Lien",  value=f"[Aller au message]({after.jump_url})", inline=False)
    embed.set_footer(text=f"Message ID : {before.id} • User ID : {before.author.id}")
    await send_log(before.guild, embed)


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    embed = discord.Embed(title="🔨 Membre banni", color=0x8B0000, timestamp=datetime.utcnow())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="Membre", value=f"{user} (`{user.id}`)")
    try:
        entries = [e async for e in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban)]
        if entries:
            embed.add_field(name="Banni par", value=str(entries[0].user))
            embed.add_field(name="Raison", value=entries[0].reason or "Aucune")
    except Exception:
        pass
    await send_log(guild, embed)


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    embed = discord.Embed(title="✅ Membre débanni", color=0x57F287, timestamp=datetime.utcnow())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="Membre", value=f"{user} (`{user.id}`)")
    await send_log(guild, embed)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    added   = [r for r in after.roles  if r not in before.roles]
    removed = [r for r in before.roles if r not in after.roles]

    # ── Détection Boost via rôle Nitro Booster ─────────────────
    # Méthode fiable : détecter l'ajout/retrait du rôle premium_subscriber
    boosted   = any(r.is_premium_subscriber() for r in added)
    unboosted = any(r.is_premium_subscriber() for r in removed)

    # Double vérification via premium_since si le rôle n'est pas détecté
    if not boosted and not unboosted:
        boosted   = (before.premium_since is None) and (after.premium_since is not None)
        unboosted = (before.premium_since is not None) and (after.premium_since is None)

    if boosted:
        ch = after.guild.get_channel(BOOST_CHANNEL_ID) if BOOST_CHANNEL_ID else None
        if not ch:
            ch = after.guild.system_channel

        if ch:
            boost_count = after.guild.premium_subscription_count or 0
            tier        = after.guild.premium_tier
            boost_path  = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "boost_banner.png")
            if not _os.path.exists(boost_path):
                boost_path = _os.path.join(_os.getcwd(), "boost_banner.png")

            embed = discord.Embed(
                description=(
                    f"✨ {after.mention} vient de **booster La Taverne** ! ✨\n\n"
                    f"Merci infiniment pour ton soutien, aventurier ! 🍺\n"
                    f"La Taverne compte maintenant **{boost_count} boost(s)** "
                    f"et atteint le **niveau {tier}** !\n\n"
                    f"*Tu rejoins les légendes de la Taverne...* ⚔️"
                ),
                color=0xF47FFF,
                timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.set_footer(text=f"La Taverne • Boost #{boost_count}")

            try:
                if _os.path.exists(boost_path):
                    file = discord.File(boost_path, filename="boost_banner.png")
                    embed.set_image(url="attachment://boost_banner.png")
                    await ch.send(embed=embed, file=file)
                else:
                    await ch.send(embed=embed)
            except Exception as e:
                print(f"⚠️ Erreur envoi boost : {e}")

        # Log
        log = discord.Embed(title="💜 Nouveau Boost !", color=0xF47FFF, timestamp=datetime.utcnow())
        log.set_thumbnail(url=after.display_avatar.url)
        log.add_field(name="Boosté par",    value=f"{after.mention} (`{after.id}`)")
        log.add_field(name="Total boosts",  value=str(after.guild.premium_subscription_count))
        log.add_field(name="Niveau serveur",value=str(after.guild.premium_tier))
        await send_log(after.guild, log)

    elif unboosted:
        log = discord.Embed(title="💔 Boost retiré", color=0x9B59B6, timestamp=datetime.utcnow())
        log.set_thumbnail(url=after.display_avatar.url)
        log.add_field(name="Membre", value=f"{after.mention} (`{after.id}`)")
        await send_log(after.guild, log)

    # ── Logs rôles ─────────────────────────────────────────────
    if not added and not removed:
        return
    embed = discord.Embed(title="🎭 Rôles mis à jour", color=0x9B59B6, timestamp=datetime.utcnow())
    embed.set_author(name=str(after), icon_url=after.display_avatar.url)
    embed.add_field(name="Membre", value=f"{after.mention} (`{after.id}`)")
    if added:
        embed.add_field(name="➕ Ajouté(s)",  value="\n".join(r.mention for r in added))
    if removed:
        embed.add_field(name="➖ Retiré(s)", value="\n".join(r.mention for r in removed))
    await send_log(after.guild, embed)


@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(title="📁 Salon créé", color=0x3498DB, timestamp=datetime.utcnow())
    embed.add_field(name="Salon", value=f"{channel.mention} (`{channel.id}`)")
    embed.add_field(name="Type",  value=str(channel.type))
    await send_log(channel.guild, embed)


@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(title="🗑️ Salon supprimé", color=0xE74C3C, timestamp=datetime.utcnow())
    embed.add_field(name="Nom",  value=channel.name)
    embed.add_field(name="Type", value=str(channel.type))
    await send_log(channel.guild, embed)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if before.channel == after.channel:
        return
    now = datetime.utcnow().timestamp()
    uid = member.id

    # ── Suivi vocal pour les stats ──────────────────────────
    if not before.channel and after.channel:
        # Rejoint
        voice_join_time[uid] = now
        d = get_user_data(uid)
        d["top_voice"][after.channel.name] = d["top_voice"].get(after.channel.name, 0) + 1
        mark_data_dirty()
    elif before.channel and not after.channel:
        # Quitté
        if uid in voice_join_time:
            start = voice_join_time.pop(uid)
            duration = max(0, int(now - start))
            d = get_user_data(uid)
            d["voice_history"].append((start, now))
            cutoff = now - 14 * 86400
            d["voice_history"] = [(s, e) for s, e in d["voice_history"] if e >= cutoff]
            _track_quest_progress(uid, "voice_seconds", duration)
            mark_data_dirty()
    elif before.channel and after.channel:
        # Changement de salon
        if uid in voice_join_time:
            start = voice_join_time[uid]
            duration = max(0, int(now - start))
            d = get_user_data(uid)
            d["voice_history"].append((start, now))
            cutoff = now - 14 * 86400
            d["voice_history"] = [(s, e) for s, e in d["voice_history"] if e >= cutoff]
            _track_quest_progress(uid, "voice_seconds", duration)
        voice_join_time[uid] = now
        d = get_user_data(uid)
        d["top_voice"][after.channel.name] = d["top_voice"].get(after.channel.name, 0) + 1
        mark_data_dirty()

    embed = discord.Embed(color=0x1ABC9C, timestamp=datetime.utcnow())
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    if not before.channel and after.channel:
        embed.title = "🔊 Rejoint un vocal"
        embed.add_field(name="Salon", value=after.channel.name)
    elif before.channel and not after.channel:
        embed.title = "🔇 Quitté un vocal"
        embed.add_field(name="Salon", value=before.channel.name)
    else:
        embed.title = "🔀 Changement vocal"
        embed.add_field(name="Avant", value=before.channel.name)
        embed.add_field(name="Après", value=after.channel.name)
    await send_log(member.guild, embed)

# ════════════════════════════════════════════════════════════════
#  ⭐  [6] SYSTÈME XP & NIVEAUX
# ════════════════════════════════════════════════════════════════
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot and message.guild:
        await _handle_bump_success(message)
        await bot.process_commands(message)
        return

    # ── Anti-spam ─────────────────────────────────────────────
    if antispam_enabled and not message.author.bot and message.guild:
        member = message.guild.get_member(message.author.id)
        immune = any(r.id in ANTISPAM_IMMUNE_ROLES for r in getattr(member, "roles", []))
        if not immune and member:
            now = datetime.utcnow().timestamp()
            uid_spam = message.author.id
            spam_tracker[uid_spam].append(now)
            spam_tracker[uid_spam] = [
                t for t in spam_tracker[uid_spam] if now - t <= SPAM_INTERVAL
            ]
            count = len(spam_tracker[uid_spam])

            # ── Étape 1 : Avertissement à mi-chemin (ex: 3 messages sur 5) ──
            SPAM_WARN_THRESHOLD = max(2, SPAM_MAX_MESSAGES - 2)
            if count == SPAM_WARN_THRESHOLD and uid_spam not in spam_warned:
                try:
                    warn_msg = discord.Embed(
                        title="⚠️ Attention !",
                        description=(
                            f"{message.author.mention} tu envoies des messages trop vite !\n\n"
                            f"⛔ Évite le spam sous peine d'être **muté**.\n"
                            f"📜 Pense à relire les règles du serveur !"
                        ),
                        color=0xFFA500,
                        timestamp=datetime.utcnow()
                    )
                    warn_msg.set_thumbnail(url=message.author.display_avatar.url)
                    warn_msg.set_footer(text="Dernier avertissement avant mute automatique")
                    await message.channel.send(embed=warn_msg, delete_after=8)
                except Exception:
                    pass

            # ── Étape 2 : Mute si seuil max atteint ──
            elif count >= SPAM_MAX_MESSAGES and uid_spam not in spam_warned:
                spam_warned.add(uid_spam)
                # Supprime les messages récents
                try:
                    await message.channel.purge(
                        limit=SPAM_MAX_MESSAGES + 2,
                        check=lambda m: m.author.id == uid_spam
                    )
                except Exception:
                    pass
                # Mute
                try:
                    import datetime as dt
                    duration = discord.utils.utcnow() + dt.timedelta(seconds=SPAM_MUTE_DURATION)
                    await member.timeout(duration, reason="Anti-spam automatique")
                except Exception:
                    pass
                # Annonce publique
                mute_embed = discord.Embed(
                    title="🔇 Membre muté pour spam",
                    description=(
                        f"{message.author.mention} a été **muté automatiquement**.\n\n"
                        f"⏰ Durée : **{SPAM_MUTE_DURATION // 60} minute(s)**\n"
                        f"📜 Merci de respecter les règles du serveur !"
                    ),
                    color=0xED4245,
                    timestamp=datetime.utcnow()
                )
                mute_embed.set_thumbnail(url=message.author.display_avatar.url)
                mute_embed.set_footer(text="Anti-spam automatique • La Taverne")
                try:
                    await message.channel.send(embed=mute_embed, delete_after=15)
                except Exception:
                    pass
                # Log
                log_embed = discord.Embed(title="🛡️ Anti-spam déclenché", color=0xED4245, timestamp=datetime.utcnow())
                log_embed.set_thumbnail(url=message.author.display_avatar.url)
                log_embed.add_field(name="👤 Membre",   value=f"{message.author.mention} (`{message.author.id}`)")
                log_embed.add_field(name="📌 Salon",    value=message.channel.mention)
                log_embed.add_field(name="📨 Messages", value=f"{count} en {SPAM_INTERVAL}s")
                log_embed.add_field(name="🔇 Action",   value=f"Mute {SPAM_MUTE_DURATION}s + messages supprimés")
                await send_log(message.guild, log_embed)
                # Reset tracker après la durée du mute
                async def reset_warned(uid):
                    await asyncio.sleep(SPAM_MUTE_DURATION)
                    spam_warned.discard(uid)
                    spam_tracker[uid] = []
                asyncio.create_task(reset_warned(uid_spam))
    # ──────────────────────────────────────────────────────────
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    now = datetime.utcnow().timestamp()
    uid = message.author.id
    _track_quest_progress(uid, "messages", 1)
    if now - xp_cooldowns.get(uid, 0) >= XP_COOLDOWN:
        xp_cooldowns[uid] = now
        data   = get_user_data(uid)
        data["xp"] += XP_PER_MESSAGE
        # Historique messages (garde 14 jours)
        data["msgs_history"].append(now)
        cutoff = now - 14 * 86400
        data["msgs_history"] = [t for t in data["msgs_history"] if t >= cutoff]
        # Top channels
        ch_name = message.channel.name
        data["top_channel"][ch_name] = data["top_channel"].get(ch_name, 0) + 1
        needed  = xp_needed(data["level"])
        leveled = False
        if data["xp"] >= needed:
            data["xp"]    -= needed
            data["level"] += 1
            leveled        = True
        mark_data_dirty()
        lvl = data["level"]
        if not leveled:
            await bot.process_commands(message)
            return

        # ── Notification level-up ──────────────────────
        xp_new   = data["xp"]
        xp_max_n = xp_needed(lvl)

        # Salon de level-up configuré ?
        lvlup_ch = message.guild.get_channel(LEVELUP_CHANNEL_ID) if LEVELUP_CHANNEL_ID else None

        if LEVELUP_GIF_ENABLED and lvlup_ch:
            try:
                buf  = await make_levelup_gif(message.author, lvl, xp_new, xp_max_n)
                file = discord.File(buf, filename="levelup.gif")
                embed = discord.Embed(
                    description=f"🎉 {message.author.mention} vient de passer au **niveau {lvl}** !",
                    color=0xFFD700, timestamp=datetime.utcnow()
                )
                embed.set_image(url="attachment://levelup.gif")
                await lvlup_ch.send(embed=embed, file=file)
            except Exception:
                embed = discord.Embed(
                    title="⬆️ Level Up !",
                    description=f"Félicitations {message.author.mention}, tu passes au **niveau {lvl}** ! 🎉",
                    color=0xFFD700, timestamp=datetime.utcnow()
                )
                embed.set_thumbnail(url=message.author.display_avatar.url)
                await lvlup_ch.send(embed=embed)
        elif lvlup_ch:
            embed = discord.Embed(
                title="⬆️ Level Up !",
                description=f"Félicitations {message.author.mention}, tu passes au **niveau {lvl}** ! 🎉",
                color=0xFFD700, timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            await lvlup_ch.send(embed=embed)
        else:
            embed = discord.Embed(
                title="⬆️ Level Up !",
                description=f"Félicitations {message.author.mention}, tu passes au **niveau {lvl}** ! 🎉",
                color=0xFFD700, timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)
            await message.channel.send(embed=embed, delete_after=20)

        # ── Rôle de niveau ──────────────────────────────
        if lvl in LEVEL_ROLES:
            role = message.guild.get_role(LEVEL_ROLES[lvl])
            if role:
                try:
                    await message.author.add_roles(role, reason=f"Niveau {lvl} atteint")
                except discord.Forbidden:
                    pass
    await bot.process_commands(message)

# ════════════════════════════════════════════════════════════════
#  🎫  [9] SYSTÈME DE TICKETS
# ════════════════════════════════════════════════════════════════
# ── Configs tickets ─────────────────────────────────────────────
TICKET_BANNER_URL  = ""   # sera défini par /ticketpanel si fichier présent
TICKET_CATEGORIES_CONFIG = {
    "aide":        {"emoji": "🆘", "label": "Problème / Aide",      "color": 0xE74C3C, "desc": "Tu rencontres un problème ou tu as besoin d'aide ?"},
    "partenariat": {"emoji": "🤝", "label": "Partenariat",          "color": 0x3498DB, "desc": "Tu veux proposer un partenariat avec notre serveur ?"},
    "staff":       {"emoji": "⚔️",  "label": "Devenir Staff",        "color": 0xF1C40F, "desc": "Tu veux rejoindre l'équipe de la Taverne ?"},
}

# Stocke quel staff a pris en charge quel ticket {channel_id: member}
ticket_claimed: dict[int, discord.Member] = {}

class TicketView(discord.ui.View):
    """Vue principale du ticket : Prendre en charge + Fermer."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✋ Prendre en charge", style=discord.ButtonStyle.success, custom_id="claim_ticket", row=0)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérifie que c'est un staff (manage_messages minimum)
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return

        ch = interaction.channel
        if ch.id in ticket_claimed:
            already = ticket_claimed[ch.id]
            await interaction.response.send_message(
                f"❌ Ce ticket est déjà pris en charge par {already.mention}.", ephemeral=True
            )
            return

        ticket_claimed[ch.id] = interaction.user

        # Désactive le bouton "Prendre en charge"
        button.disabled = True
        button.label    = f"✅ Pris par {interaction.user.display_name}"
        await interaction.message.edit(view=self)

        # Annonce dans le ticket
        embed = discord.Embed(
            title="✋ Ticket pris en charge",
            description=f"{interaction.user.mention} s'occupe de ce ticket !",
            color=0x57F287, timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await ch.send(embed=embed)

        # Log
        log = discord.Embed(title="✋ Ticket pris en charge", color=0x57F287, timestamp=datetime.utcnow())
        log.add_field(name="Staff",  value=f"{interaction.user.mention} (`{interaction.user.id}`)")
        log.add_field(name="Salon",  value=ch.mention)
        await send_log(interaction.guild, log)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket", row=0)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        uid = next((u for u, c in open_tickets.items() if c == channel.id), None)
        if uid:
            del open_tickets[uid]
            save_data()
        ticket_claimed.pop(channel.id, None)

        embed = discord.Embed(
            title="🔒 Ticket fermé",
            description=f"Fermé par {interaction.user.mention}. Suppression dans 5 secondes...",
            color=0xED4245, timestamp=datetime.utcnow()
        )
        await channel.send(embed=embed)
        log = discord.Embed(title="🎫 Ticket fermé", color=0xED4245, timestamp=datetime.utcnow())
        log.add_field(name="Fermé par", value=f"{interaction.user.mention} (`{interaction.user.id}`)")
        log.add_field(name="Salon",     value=channel.name)
        await send_log(interaction.guild, log)
        # ── Retirer l'exemption AutoMod avant suppression ──
        try:
            automod_rules = await interaction.guild.fetch_automod_rules()
            for rule in automod_rules:
                if rule.trigger.type == discord.AutoModRuleTriggerType.keyword_preset:
                    exempt_channels = [c for c in rule.exempt_channels if c.id != channel.id]
                    await rule.edit(exempt_channels=exempt_channels)
                    break
        except Exception as e:
            print(f"⚠️ AutoMod exemption (fermeture ticket) : {e}")

        await asyncio.sleep(5)
        await channel.delete(reason="Ticket fermé")

# Alias pour compatibilité
TicketCloseButton = TicketView


async def _create_ticket(interaction: discord.Interaction, ticket_type: str):
    """Crée un salon ticket d'un type donné."""
    guild = interaction.guild
    user  = interaction.user
    cfg   = TICKET_CATEGORIES_CONFIG[ticket_type]

    if user.id in open_tickets:
        ch = guild.get_channel(open_tickets[user.id])
        await interaction.response.send_message(
            f"❌ Tu as déjà un ticket ouvert : {ch.mention if ch else 'introuvable'}", ephemeral=True
        )
        return

    category = guild.get_channel(TICKET_CATEGORY_ID) if TICKET_CATEGORY_ID else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user:               discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    ch_name   = f"{ticket_type}-{user.name}"
    ticket_ch = await guild.create_text_channel(
        name=ch_name, category=category, overwrites=overwrites, reason=f"Ticket {ticket_type} de {user}"
    )
    open_tickets[user.id] = ticket_ch.id
    save_data()

    # ── Exemption AutoMod : autoriser les liens dans ce salon ticket ──
    try:
        automod_rules = await guild.fetch_automod_rules()
        for rule in automod_rules:
            if rule.trigger.type == discord.AutoModRuleTriggerType.keyword_preset:
                exempt_channels = list(rule.exempt_channels) + [ticket_ch]
                await rule.edit(exempt_channels=exempt_channels)
                break
    except Exception as e:
        print(f"⚠️ AutoMod exemption (création ticket) : {e}")

    embed = discord.Embed(
        title=f"{cfg['emoji']} {cfg['label']}",
        description=(
            f"Bienvenue {user.mention} !\n\n"
            f"_{cfg['desc']}_\n\n\nUn membre de l'équipe va te répondre bientôt.\n\nDécris ta demande ci-dessous en détail.\n\n\n━━━━━━━━━━━━━━━━━━━━━━\n\nClique sur le bouton rouge pour **fermer le ticket**."
        ),
        color=cfg["color"], timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"Ticket {ticket_type} • {guild.name}")
    await ticket_ch.send(embed=embed, view=TicketView())
    await interaction.response.send_message(f"✅ Ton ticket a été créé : {ticket_ch.mention}", ephemeral=True)

    log = discord.Embed(title=f"🎫 Nouveau ticket — {cfg['label']}", color=cfg["color"], timestamp=datetime.utcnow())
    log.add_field(name="Ouvert par", value=f"{user.mention} (`{user.id}`)")
    log.add_field(name="Type",       value=cfg["label"])
    log.add_field(name="Salon",      value=ticket_ch.mention)
    await send_log(guild, log)


class TicketSelectView(discord.ui.View):
    """Panel avec 3 boutons de catégorie."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🆘  Problème / Aide",  style=discord.ButtonStyle.danger,   custom_id="ticket_aide",        row=0)
    async def btn_aide(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _create_ticket(interaction, "aide")

    @discord.ui.button(label="🤝  Partenariat",       style=discord.ButtonStyle.primary,  custom_id="ticket_partenariat", row=0)
    async def btn_partenariat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _create_ticket(interaction, "partenariat")

    @discord.ui.button(label="⚔️   Devenir Staff",    style=discord.ButtonStyle.success,  custom_id="ticket_staff",       row=0)
    async def btn_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _create_ticket(interaction, "staff")

class ReglementModal(discord.ui.Modal, title="📜 Rédiger le Règlement"):
    contenu = discord.ui.TextInput(
        label="Contenu du règlement",
        style=discord.TextStyle.paragraph,
        placeholder="Écris ici les règles du serveur...",
        required=True,
        max_length=3900
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.target_channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        import os as _os
        banner_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "reglement_banner.png")
        if not _os.path.exists(banner_path):
            banner_path = _os.path.join(_os.getcwd(), "reglement_banner.png")

        embed = discord.Embed(
            title="",
            description=self.contenu.value,
            color=0x9B59B6,
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text=f"La Taverne • Règlement mis à jour par {interaction.user.display_name}")

        if _os.path.exists(banner_path):
            file  = discord.File(banner_path, filename="reglement_banner.png")
            embed.set_image(url="attachment://reglement_banner.png")
            await self.target_channel.send(embed=embed, file=file)
        else:
            await self.target_channel.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Règlement publié dans {self.target_channel.mention} !", ephemeral=True
        )


@tree.command(name="reglement", description="[Admin] Publie le règlement avec l'image dans un salon")
@app_commands.describe(salon="Salon où publier le règlement")
@app_commands.checks.has_permissions(administrator=True)
async def slash_reglement(interaction: discord.Interaction, salon: discord.TextChannel = None):
    target = salon or interaction.channel
    await interaction.response.send_modal(ReglementModal(channel=target))


# ════════════════════════════════════════════════════════════════
#  🎮  [13] MINI-JEUX — /jeu ...
# ════════════════════════════════════════════════════════════════
@game_group.command(name="coinflip", description="🪙 Lance une pièce")
async def slash_coinflip(interaction: discord.Interaction):
    result = random.choice(["Pile 🪙", "Face 🎭"])
    embed = discord.Embed(title="🪙 Pile ou Face", description=f"Résultat : **{result}**", color=0xFFD700)
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@game_group.command(name="dice", description="🎲 Lance un dé")
@app_commands.describe(faces="Nombre de faces (défaut : 6)")
async def slash_dice(interaction: discord.Interaction, faces: int = 6):
    if faces < 2:
        await interaction.response.send_message("❌ Minimum 2 faces.", ephemeral=True)
        return
    result = random.randint(1, faces)
    embed = discord.Embed(title=f"🎲 Dé à {faces} faces", description=f"Résultat : **{result}**", color=0x9B59B6)
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@game_group.command(name="rps", description="✂️ Pierre-Papier-Ciseaux contre le bot")
@app_commands.describe(choix="Ton choix")
@app_commands.choices(choix=[
    app_commands.Choice(name="Pierre 🪨",  value="pierre"),
    app_commands.Choice(name="Papier 📄",  value="papier"),
    app_commands.Choice(name="Ciseaux ✂️", value="ciseaux"),
])
async def slash_rps(interaction: discord.Interaction, choix: app_commands.Choice[str]):
    icons    = {"pierre": "🪨", "papier": "📄", "ciseaux": "✂️"}
    wins     = {"pierre": "ciseaux", "papier": "pierre", "ciseaux": "papier"}
    bot_pick = random.choice(["pierre", "papier", "ciseaux"])
    if choix.value == bot_pick:
        result, color = "Égalité ! 🤝", 0xFFA500
    elif wins[choix.value] == bot_pick:
        result, color = "Tu gagnes ! 🎉", 0x57F287
    else:
        result, color = "Tu perds ! 😈", 0xED4245
    embed = discord.Embed(title="✂️ Pierre-Papier-Ciseaux", color=color)
    embed.add_field(name="Ton choix", value=f"{icons[choix.value]} {choix.value.capitalize()}")
    embed.add_field(name="Mon choix", value=f"{icons[bot_pick]} {bot_pick.capitalize()}")
    embed.add_field(name="Résultat",  value=result, inline=False)
    await interaction.response.send_message(embed=embed)


@game_group.command(name="slots", description="🎰 Machine à sous")
async def slash_slots(interaction: discord.Interaction):
    left = check_game_cooldown(interaction.user.id, "slots", 15)
    if left > 0:
        await interaction.response.send_message(f"⏳ Cooldown ! Réessaie dans **{left:.0f}s**.", ephemeral=True)
        return
    symbols = ["🍒", "🍋", "🍊", "⭐", "💎", "🎰"]
    reels   = [random.choice(symbols) for _ in range(3)]
    line    = " | ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        result, color = "🎉 JACKPOT ! Trois identiques !", 0xFFD700
    elif reels[0] == reels[1] or reels[1] == reels[2]:
        result, color = "✨ Deux identiques, presque !", 0xFFA500
    else:
        result, color = "😢 Rien... Tente encore !", 0xED4245
    embed = discord.Embed(title="🎰 Machine à sous", description=f"**{line}**\n\n{result}", color=color)
    embed.set_footer(text=f"Joué par {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@game_group.command(name="guess", description="🔢 Devine un nombre entre 1 et 100 (5 essais)")
async def slash_guess(interaction: discord.Interaction):
    await interaction.response.defer()
    left = check_game_cooldown(interaction.user.id, "guess", 30)
    if left > 0:
        await interaction.followup.send(f"⏳ Cooldown ! Réessaie dans **{left:.0f}s**.", ephemeral=True)
        return
    secret = random.randint(1, 100)
    await interaction.followup.send(
        f"🔢 J'ai choisi un nombre entre **1 et 100**. Tu as **5 tentatives** !\n"
        f"Réponds avec `!guess <nombre>`"
    )
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel and m.content.startswith("!guess ")
    for attempt in range(1, 6):
        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            try:
                n = int(msg.content.split()[1])
            except (ValueError, IndexError):
                await interaction.channel.send("❌ Écris un nombre valide !")
                continue
            if n == secret:
                await interaction.channel.send(f"🎉 Bravo {interaction.user.mention} ! C'était **{secret}** en {attempt} essai(s) !")
                return
            hint = "📈 Plus grand !" if n < secret else "📉 Plus petit !"
            await interaction.channel.send(f"{hint} ({5 - attempt} tentatives restantes)")
        except asyncio.TimeoutError:
            await interaction.channel.send(f"⏰ Temps écoulé ! Le nombre était **{secret}**.")
            return
    await interaction.channel.send(f"💀 Plus de tentatives ! Le nombre était **{secret}**.")

# ════════════════════════════════════════════════════════════════
#  🎁  [14] JEUX GRATUITS — Epic / Steam / GOG
# ════════════════════════════════════════════════════════════════
@tasks.loop(hours=FREE_GAMES_CHECK_INTERVAL)
async def check_free_games():
    await bot.wait_until_ready()
    ch = bot.get_channel(FREE_GAMES_CHANNEL_ID)
    if not ch:
        return
    for game in await fetch_all_free_games():
        gid = f"{game['platform']}_{game['title']}"
        if gid in announced_games:
            continue
        announced_games.add(gid)
        mark_data_dirty()
        await ch.send(embed=build_game_embed(game))


async def fetch_all_free_games() -> list:
    games = []
    games += await fetch_epic_free_games()
    games += await fetch_steam_free_games()
    games += await fetch_gog_free_games()
    return games


async def fetch_epic_free_games() -> list:
    url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=fr&country=FR&allowCountries=FR"
    games = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200: return []
                data = await r.json()
        for item in data.get("data",{}).get("Catalog",{}).get("searchStore",{}).get("elements",[]):
            promo = item.get("promotions") or {}
            for pg in promo.get("promotionalOffers",[]):
                for offer in pg.get("promotionalOffers",[]):
                    if offer.get("discountSetting",{}).get("discountPercentage",-1) != 0: continue
                    slug = item.get("productSlug") or item.get("urlSlug") or ""
                    img  = next((i["url"] for i in item.get("keyImages",[]) if i.get("type") in ("Thumbnail","DieselStoreFrontWide","OfferImageWide")), "")
                    games.append({
                        "platform":"Epic Games","title":item.get("title","?"),
                        "description":item.get("description",""),
                        "url":f"https://store.epicgames.com/fr/p/{slug}" if slug else "https://store.epicgames.com/fr/",
                        "image":img,"end_date":offer.get("endDate",""),"color":0x2C2F33
                    })
    except Exception as e:
        print(f"Epic error: {e}")
    return games


async def fetch_steam_free_games() -> list:
    url = "https://store.steampowered.com/api/featuredcategories?cc=fr&l=french"
    games = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200: return []
                data = await r.json()
        for item in data.get("specials",{}).get("items",[]):
            if item.get("discount_percent",0) < 100: continue
            games.append({
                "platform":"Steam","title":item.get("name","?"),
                "description":"Gratuit à 100% sur Steam !",
                "url":f"https://store.steampowered.com/app/{item.get('id')}/",
                "image":item.get("large_capsule_image",""),"end_date":"","color":0x1B2838
            })
    except Exception as e:
        print(f"Steam error: {e}")
    return games


async def fetch_gog_free_games() -> list:
    url = "https://www.gog.com/games/ajax/filtered?mediaType=game&price=free&page=1"
    games = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200: return []
                data = await r.json()
        for item in data.get("products", [])[:3]:
            slug = item.get("slug","")
            img  = "https:" + item.get("image","") + "_200.jpg" if item.get("image") else ""
            games.append({
                "platform":"GOG","title":item.get("title","?"),
                "description":"Jeu gratuit sur GOG !",
                "url":f"https://www.gog.com/game/{slug}",
                "image":img,"end_date":"","color":0x7B2FBE
            })
    except Exception as e:
        print(f"GOG error: {e}")
    return games


def build_game_embed(game: dict) -> discord.Embed:
    end_info = ""
    if game["end_date"]:
        try:
            dt = datetime.fromisoformat(game["end_date"].replace("Z","+00:00"))
            end_info = f"\n⏰ **Fin :** <t:{int(dt.timestamp())}:R>"
        except Exception:
            end_info = f"\n⏰ **Fin :** {game['end_date']}"
    icons = {"Epic Games":"🟣","Steam":"🎮","GOG":"🟤"}
    embed = discord.Embed(
        title=f"🎁 Jeu gratuit — {game['title']}",
        description=f"{game['description'][:200]}{end_info}\n\n[➡️ Récupérer sur {game['platform']}]({game['url']})",
        url=game["url"], color=game["color"], timestamp=datetime.utcnow()
    )
    embed.set_author(name=f"{icons.get(game['platform'],'🎮')} {game['platform']} — Jeu gratuit !")
    if game["image"]:
        embed.set_image(url=game["image"])
    embed.set_footer(text="Dépêche-toi, l'offre est limitée !")
    return embed

# ════════════════════════════════════════════════════════════════
#  🔩  [12] COMMANDES ADMIN — Configuration
# ════════════════════════════════════════════════════════════════
@tree.command(name="setlog", description="[Admin] Définit le salon des logs")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setlog(interaction: discord.Interaction, channel: discord.TextChannel):
    global LOG_CHANNEL_ID
    LOG_CHANNEL_ID = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Salon logs : {channel.mention}", ephemeral=True)

@tree.command(name="setwelcome", description="[Admin] Définit le salon de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    global WELCOME_CHANNEL_ID
    WELCOME_CHANNEL_ID = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Salon bienvenue : {channel.mention}", ephemeral=True)

@tree.command(name="setgoodbye", description="[Admin] Définit le salon d'au revoir")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setgoodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    global GOODBYE_CHANNEL_ID
    GOODBYE_CHANNEL_ID = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Salon au revoir : {channel.mention}", ephemeral=True)

@tree.command(name="setfreegames", description="[Admin] Définit le salon des jeux gratuits")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setfreegames(interaction: discord.Interaction, channel: discord.TextChannel):
    global FREE_GAMES_CHANNEL_ID
    FREE_GAMES_CHANNEL_ID = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Salon jeux gratuits : {channel.mention}", ephemeral=True)

@tree.command(name="setlevelup", description="[Admin] Définit le salon des notifications de level-up")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setlevelup(interaction: discord.Interaction, channel: discord.TextChannel):
    global LEVELUP_CHANNEL_ID
    LEVELUP_CHANNEL_ID = channel.id
    save_data()
    await interaction.response.send_message(f"✅ Salon level-up : {channel.mention}", ephemeral=True)


def find_member_for_welcome_preview(guild: discord.Guild, lookup: str = "b000o000") -> discord.Member | None:
    needle = lookup.strip().lower()
    for member in guild.members:
        names = {
            member.name.lower(),
            member.display_name.lower(),
        }
        global_name = getattr(member, "global_name", None)
        if global_name:
            names.add(global_name.lower())
        if needle in names:
            return member
    return None


@tree.command(name="previewbienvenue", description="[Admin] Envoie un aperçu du MP de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(membre="Membre qui doit recevoir l'aperçu")
async def slash_previewbienvenue(interaction: discord.Interaction, membre: discord.Member | None = None):
    await interaction.response.defer(ephemeral=True)
    target = membre or find_member_for_welcome_preview(interaction.guild, "b000o000")
    if not target:
        await interaction.followup.send(
            "❌ Impossible de trouver `b000o000`. Mentionne directement le membre dans la commande.",
            ephemeral=True
        )
        return

    dm_sent = await send_dm(target, build_welcome_dm_embed(target, preview=True))
    if not dm_sent:
        await interaction.followup.send(
            f"❌ Impossible d'envoyer le MP à {target.mention} (DMs fermés).",
            ephemeral=True
        )
        return

    await interaction.followup.send(
        f"✅ Aperçu du message de bienvenue envoyé en MP à {target.mention}.",
        ephemeral=True
    )

# Liste des rôles donnés automatiquement à l'arrivée
AUTO_ROLES: list[int] = [AUTO_ROLE_ID] if AUTO_ROLE_ID else []

@tree.command(name="autorole", description="[Admin] Gère les rôles donnés automatiquement à l'arrivée")
@app_commands.describe(role="Rôle à ajouter/retirer", action="Action à effectuer")
@app_commands.choices(action=[
    app_commands.Choice(name="➕ Ajouter",    value="add"),
    app_commands.Choice(name="➖ Retirer",    value="remove"),
    app_commands.Choice(name="📋 Voir liste", value="list"),
])
@app_commands.checks.has_permissions(administrator=True)
async def slash_autorole(interaction: discord.Interaction, role: discord.Role = None, action: str = "add"):
    global AUTO_ROLE_ID, AUTO_ROLES
    if action == "list":
        if not AUTO_ROLES:
            await interaction.response.send_message("❌ Aucun auto-rôle configuré.", ephemeral=True)
            return
        roles_txt = "\n".join(f"• <@&{r}>" for r in AUTO_ROLES)
        await interaction.response.send_message(f"📋 **Auto-rôles actuels :**\n{roles_txt}", ephemeral=True)
        return
    if role is None:
        await interaction.response.send_message("❌ Précise un rôle !", ephemeral=True)
        return
    if action == "add":
        if role.id not in AUTO_ROLES:
            AUTO_ROLES.append(role.id)
        AUTO_ROLE_ID = AUTO_ROLES[0] if AUTO_ROLES else 0
        save_data()
        await interaction.response.send_message(f"✅ {role.mention} ajouté aux auto-rôles !", ephemeral=True)
    elif action == "remove":
        if role.id in AUTO_ROLES:
            AUTO_ROLES.remove(role.id)
        AUTO_ROLE_ID = AUTO_ROLES[0] if AUTO_ROLES else 0
        save_data()
        await interaction.response.send_message(f"✅ {role.mention} retiré des auto-rôles.", ephemeral=True)

@tree.command(name="setticketcategory", description="[Admin] Définit la catégorie des tickets")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setticketcategory(interaction: discord.Interaction, categorie: discord.CategoryChannel):
    global TICKET_CATEGORY_ID
    TICKET_CATEGORY_ID = categorie.id
    save_data()
    await interaction.response.send_message(f"✅ Catégorie tickets : **{categorie.name}**", ephemeral=True)

@tree.command(name="ticketpanel", description="[Admin] Envoie le panel de tickets avec l'image dans ce salon")
@app_commands.checks.has_permissions(administrator=True)
async def slash_ticketpanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    import os as _os
    # Cherche .jpg puis .png
    banner_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ticket_banner.jpg")
    if not _os.path.exists(banner_path):
        banner_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ticket_banner.png")
    if not _os.path.exists(banner_path):
        banner_path = _os.path.join(_os.getcwd(), "ticket_banner.jpg")
    if not _os.path.exists(banner_path):
        banner_path = _os.path.join(_os.getcwd(), "ticket_banner.png")

    embed = discord.Embed(
        title="",
        description=(
            "**Besoin d'aide ? Tu veux nous rejoindre ?**\n\nChoisis la catégorie qui correspond à ta demande\n\net clique sur le bouton ci-dessous. 🛡️\n\n\n🆘 **Problème / Aide** — Un souci sur le serveur ?\n\n🤝 **Partenariat** — Tu veux proposer un partenariat ?\n\n⚔️ **Devenir Staff** — Tu veux rejoindre l'équipe ?"
        ),
        color=0x8B0000
    )
    embed.set_footer(text="Un seul ticket actif par personne • La Taverne")

    if _os.path.exists(banner_path):
        banner_ext  = "jpg" if banner_path.endswith(".jpg") else "png"
        banner_name = f"ticket_banner.{banner_ext}"
        file  = discord.File(banner_path, filename=banner_name)
        embed.set_image(url=f"attachment://{banner_name}")
        await interaction.channel.send(embed=embed, file=file, view=TicketSelectView())
    else:
        await interaction.channel.send(embed=embed, view=TicketSelectView())

    await interaction.followup.send("✅ Panel tickets envoyé !", ephemeral=True)

@tree.command(name="setlevelrole", description="[Admin] Associe un rôle à un niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(niveau="Niveau requis", role="Rôle à attribuer")
async def slash_setlevelrole(interaction: discord.Interaction, niveau: int, role: discord.Role):
    LEVEL_ROLES[niveau] = role.id
    save_data()
    await interaction.response.send_message(
        f"✅ Niveau **{niveau}** → {role.mention}", ephemeral=True
    )

@tree.command(name="levelroles", description="Affiche tous les rôles de niveau configurés")
async def slash_levelroles(interaction: discord.Interaction):
    if not LEVEL_ROLES:
        await interaction.response.send_message("Aucun rôle de niveau configuré.", ephemeral=True)
        return
    embed = discord.Embed(title="🏅 Rôles par niveau", color=0xFFD700)
    for lvl, rid in sorted(LEVEL_ROLES.items()):
        role = interaction.guild.get_role(rid)
        embed.add_field(name=f"Niveau {lvl}", value=role.mention if role else f"Rôle inconnu ({rid})")
    await interaction.response.send_message(embed=embed)

@tree.command(name="rank", description="Affiche ton niveau, XP et heures en vocal")
@app_commands.describe(membre="Membre (optionnel)")
async def slash_rank(interaction: discord.Interaction, membre: discord.Member = None):
    target  = membre or interaction.user
    data    = get_user_data(target.id)
    needed  = xp_needed(data["level"])
    filled  = int((data["xp"] / needed) * 20)
    bar     = "█" * filled + "░" * (20 - filled)
    rank_m  = get_rank(interaction.guild.id, target.id, "msg")
    rank_v  = get_rank(interaction.guild.id, target.id, "voice")

    # Calcul heures vocales totales
    now = datetime.utcnow().timestamp()
    total_voice_sec = sum(
        (e - s) for s, e in data.get("voice_history", [])
    )
    # Ajouter session vocale en cours si le membre est en vocal
    if target.id in voice_join_time:
        total_voice_sec += now - voice_join_time[target.id]

    total_voice_h   = total_voice_sec / 3600
    voice_str       = f"{total_voice_h:.1f}h" if total_voice_h >= 1 else f"{int(total_voice_sec // 60)}min"

    # Stats 7 derniers jours
    stats7 = get_stats_for_days(target.id, 7)
    voice_7j_str = f"{stats7['voice']:.1f}h" if stats7['voice'] >= 1 else f"{int(stats7['voice']*60)}min"

    embed = discord.Embed(
        title=f"📊 Rang de {target.display_name}",
        color=0xFFD700,
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="⭐ Niveau",        value=str(data["level"]),           inline=True)
    embed.add_field(name="✨ XP",            value=f"{data['xp']} / {needed}",   inline=True)
    embed.add_field(name="🏆 Rang messages", value=f"#{rank_m}",                 inline=True)
    embed.add_field(name="🎙️ Rang vocal",    value=f"#{rank_v}",                 inline=True)
    embed.add_field(name="🔊 Temps vocal total", value=voice_str,                inline=True)
    embed.add_field(name="📅 Vocal 7j",      value=voice_7j_str,                 inline=True)
    embed.add_field(name="💬 Messages 7j",   value=str(stats7["msgs"]),          inline=True)
    embed.add_field(name="📈 Progression",   value=f"`{bar}` {data['xp']}/{needed} XP", inline=False)
    embed.set_footer(text=f"La Taverne • {target.id}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="stats", description="🃏 Affiche la carte de stats complète d'un aventurier")
@app_commands.describe(membre="Membre (laisse vide pour toi)")
async def slash_stats(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    await interaction.response.defer(thinking=True)

    if not STATS_CARD_ENABLED:
        await interaction.followup.send("❌ Le module `stats_card.py` est manquant dans le dossier du bot.", ephemeral=True)
        return

    d       = get_user_data(target.id)
    stats1  = get_stats_for_days(target.id, 1)
    stats7  = get_stats_for_days(target.id, 7)
    stats14 = get_stats_for_days(target.id, 14)
    charts  = get_chart_data(target.id)
    rank_m  = get_rank(interaction.guild.id, target.id, "msg")
    rank_v  = get_rank(interaction.guild.id, target.id, "voice")

    top_ch = sorted(d["top_channel"].items(), key=lambda x: x[1], reverse=True)
    top_vc = sorted(d["top_voice"].items(),   key=lambda x: x[1], reverse=True)

    stats_payload = {
        "xp":          d["xp"],
        "level":       d["level"],
        "rank_msg":    rank_m,
        "rank_voice":  rank_v,
        "msgs_1d":     stats1["msgs"],
        "msgs_7d":     stats7["msgs"],
        "msgs_14d":    stats14["msgs"],
        "voice_1d":    stats1["voice"],
        "voice_7d":    stats7["voice"],
        "voice_14d":   stats14["voice"],
        "top_channel": f"#{top_ch[0][0]}" if top_ch else "—",
        "top_voice":   f"🎙 {top_vc[0][0]}" if top_vc else "—",
        **charts,
    }

    buf = await make_stats_card(target, stats_payload)
    file = discord.File(buf, filename=f"stats_{target.id}.png")
    embed = discord.Embed(
        description=f"📊 Carte d'activité de **{target.display_name}**",
        color=0x8B0000
    )
    embed.set_image(url=f"attachment://stats_{target.id}.png")
    await interaction.followup.send(embed=embed, file=file)

@tree.command(name="leaderboard", description="Top 10 des membres les plus actifs")
async def slash_leaderboard(interaction: discord.Interaction):
    top = sorted(xp_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:10]
    embed = discord.Embed(title="🏆 Classement d'activité", color=0xFFD700, timestamp=datetime.utcnow())
    medals = ["🥇","🥈","🥉"] + ["🏅"]*7
    for i, (uid, d) in enumerate(top):
        m = interaction.guild.get_member(uid)
        name = m.display_name if m else f"Utilisateur {uid}"
        embed.add_field(name=f"{medals[i]} #{i+1} — {name}", value=f"Niveau **{d['level']}** · {d['xp']} XP", inline=False)
    if not top:
        embed.description = "Personne n'a encore gagné d'XP !"
    await interaction.response.send_message(embed=embed)

@tree.command(name="freegames", description="Affiche les jeux gratuits maintenant")
async def slash_freegames(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    games = await fetch_all_free_games()
    if not games:
        await interaction.followup.send("😕 Aucun jeu gratuit trouvé en ce moment.")
        return
    for game in games[:6]:
        await interaction.followup.send(embed=build_game_embed(game))

@tree.command(name="giverole", description="[Admin] Donne un rôle à un membre")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_giverole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await interaction.response.send_message(f"✅ {role.mention} → {member.mention}", ephemeral=True)

@tree.command(name="removerole", description="[Admin] Retire un rôle à un membre")
@app_commands.checks.has_permissions(manage_roles=True)
async def slash_removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await interaction.response.send_message(f"✅ Rôle retiré à {member.mention}", ephemeral=True)

@tree.command(name="ping", description="Latence du bot")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong ! **{round(bot.latency*1000)} ms**")

# ════════════════════════════════════════════════════════════════
#  🛡️  [7] ANTI-SPAM
# ════════════════════════════════════════════════════════════════

from collections import defaultdict

# Config anti-spam
SPAM_MAX_MESSAGES  = 5    # nb max de messages
SPAM_INTERVAL      = 5    # dans X secondes
SPAM_MUTE_DURATION = 300  # durée du mute en secondes (5 min)
antispam_enabled   = True

# Whitelist de rôles immunisés au spam (ex: modérateurs)
ANTISPAM_IMMUNE_ROLES: list[int] = []

# Compteur : {user_id: [timestamps]}
spam_tracker: dict[int, list] = defaultdict(list)
spam_warned:  set[int]        = set()   # déjà averti ce cycle

@tree.command(name="antispam", description="[Admin] Active ou désactive l'anti-spam")
@app_commands.describe(actif="True = activé, False = désactivé")
@app_commands.checks.has_permissions(administrator=True)
async def slash_antispam(interaction: discord.Interaction, actif: bool):
    global antispam_enabled
    antispam_enabled = actif
    status = "✅ activé" if actif else "❌ désactivé"
    await interaction.response.send_message(f"🛡️ Anti-spam {status}.", ephemeral=True)

@tree.command(name="antispamconfig", description="[Admin] Configure les seuils de l'anti-spam")
@app_commands.describe(
    messages="Nb de messages déclenchant le spam (défaut: 5)",
    secondes="Fenêtre de temps en secondes (défaut: 5)",
    mute_secondes="Durée du mute en secondes (défaut: 300)"
)
@app_commands.checks.has_permissions(administrator=True)
async def slash_antispamconfig(interaction: discord.Interaction, messages: int = 5, secondes: int = 5, mute_secondes: int = 300):
    global SPAM_MAX_MESSAGES, SPAM_INTERVAL, SPAM_MUTE_DURATION
    SPAM_MAX_MESSAGES  = messages
    SPAM_INTERVAL      = secondes
    SPAM_MUTE_DURATION = mute_secondes
    embed = discord.Embed(title="🛡️ Anti-spam configuré", color=0x8B0000)
    embed.add_field(name="📨 Messages max",    value=str(messages),      inline=True)
    embed.add_field(name="⏱️ Fenêtre",          value=f"{secondes}s",     inline=True)
    embed.add_field(name="🔇 Durée du mute",   value=f"{mute_secondes}s", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="antispamstatus", description="Affiche la configuration de l'anti-spam")
async def slash_antispamstatus(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Anti-spam",
        description=f"Statut : {'✅ Actif' if antispam_enabled else '❌ Désactivé'}",
        color=0x57F287 if antispam_enabled else 0xED4245
    )
    embed.add_field(name="📨 Messages max",  value=str(SPAM_MAX_MESSAGES), inline=True)
    embed.add_field(name="⏱️ Fenêtre",        value=f"{SPAM_INTERVAL}s",    inline=True)
    embed.add_field(name="🔇 Durée mute",    value=f"{SPAM_MUTE_DURATION}s",inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ════════════════════════════════════════════════════════════════
#  ⚔️  [8] MODÉRATION — /ban /kick /mute /warn
# ════════════════════════════════════════════════════════════════

async def send_dm(member: discord.Member, embed: discord.Embed) -> bool:
    """Envoie un MP à un membre, retourne True si succès."""
    try:
        await member.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False

def get_moderation_block_reason(interaction: discord.Interaction, membre: discord.Member) -> str | None:
    guild = interaction.guild
    actor = interaction.user
    bot_member = guild.me

    if membre.id == actor.id:
        return "❌ Tu ne peux pas te modérer toi-même."
    if membre == guild.owner:
        return "❌ Impossible de modérer le propriétaire du serveur."
    if actor != guild.owner and membre.top_role >= actor.top_role:
        return "❌ Tu ne peux pas modérer un membre ayant un rôle égal ou supérieur au tien."
    if bot_member and membre.top_role >= bot_member.top_role:
        return "❌ Je ne peux pas modérer ce membre (rôle trop élevé)."
    return None


@tree.command(name="ban", description="[Mod] Bannit un membre")
@app_commands.describe(membre="Membre à bannir", raison="Raison du ban")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    block_reason = get_moderation_block_reason(interaction, membre)
    if block_reason:
        await interaction.response.send_message(block_reason, ephemeral=True)
        return

    # MP au membre
    dm_embed = discord.Embed(
        title="🔨 Tu as été banni",
        description=f"Tu as été banni du serveur **{interaction.guild.name}**.",
        color=0x8B0000, timestamp=datetime.utcnow()
    )
    dm_embed.add_field(name="Raison", value=raison, inline=False)
    dm_embed.add_field(name="Modérateur", value=str(interaction.user))
    dm_embed.set_footer(text="Si tu penses que c'est une erreur, contacte un administrateur.")
    dm_sent = await send_dm(membre, dm_embed)

    await membre.ban(reason=f"{raison} | Par {interaction.user}")

    embed = discord.Embed(title="🔨 Membre banni", color=0x8B0000, timestamp=datetime.utcnow())
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="Membre",      value=f"{membre} (`{membre.id}`)")
    embed.add_field(name="Modérateur",  value=interaction.user.mention)
    embed.add_field(name="Raison",      value=raison, inline=False)
    embed.add_field(name="MP envoyé",   value="✅ Oui" if dm_sent else "❌ Non (DMs fermés)")
    await interaction.response.send_message(embed=embed)

    # Log
    await send_log(interaction.guild, embed)


@tree.command(name="kick", description="[Mod] Expulse un membre")
@app_commands.describe(membre="Membre à expulser", raison="Raison du kick")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    block_reason = get_moderation_block_reason(interaction, membre)
    if block_reason:
        await interaction.response.send_message(block_reason, ephemeral=True)
        return

    dm_embed = discord.Embed(
        title="👢 Tu as été expulsé",
        description=f"Tu as été expulsé du serveur **{interaction.guild.name}**.",
        color=0xFF6B00, timestamp=datetime.utcnow()
    )
    dm_embed.add_field(name="Raison",      value=raison, inline=False)
    dm_embed.add_field(name="Modérateur",  value=str(interaction.user))
    dm_embed.set_footer(text="Tu peux rejoindre le serveur si tu as un lien d'invitation.")
    dm_sent = await send_dm(membre, dm_embed)

    await membre.kick(reason=f"{raison} | Par {interaction.user}")

    embed = discord.Embed(title="👢 Membre expulsé", color=0xFF6B00, timestamp=datetime.utcnow())
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="Membre",     value=f"{membre} (`{membre.id}`)")
    embed.add_field(name="Modérateur", value=interaction.user.mention)
    embed.add_field(name="Raison",     value=raison, inline=False)
    embed.add_field(name="MP envoyé",  value="✅ Oui" if dm_sent else "❌ Non (DMs fermés)")
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@tree.command(name="mute", description="[Mod] Rend muet un membre")
@app_commands.describe(membre="Membre à muter", duree="Durée en minutes", raison="Raison")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_mute(interaction: discord.Interaction, membre: discord.Member, duree: int = 10, raison: str = "Aucune raison fournie"):
    from datetime import timedelta
    block_reason = get_moderation_block_reason(interaction, membre)
    if block_reason:
        await interaction.response.send_message(block_reason, ephemeral=True)
        return
    if duree < 1 or duree > 40320:
        await interaction.response.send_message("❌ Durée entre 1 min et 40320 min (28 jours).", ephemeral=True)
        return

    until = discord.utils.utcnow() + timedelta(minutes=duree)
    await membre.timeout(until, reason=f"{raison} | Par {interaction.user}")

    dm_embed = discord.Embed(
        title="🔇 Tu as été mis en sourdine",
        description=f"Tu as été rendu muet sur **{interaction.guild.name}**.",
        color=0xFFA500, timestamp=datetime.utcnow()
    )
    dm_embed.add_field(name="Durée",       value=f"{duree} minute(s)", inline=True)
    dm_embed.add_field(name="Modérateur",  value=str(interaction.user), inline=True)
    dm_embed.add_field(name="Raison",      value=raison, inline=False)
    dm_sent = await send_dm(membre, dm_embed)

    embed = discord.Embed(title="🔇 Membre muté", color=0xFFA500, timestamp=datetime.utcnow())
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="Membre",     value=f"{membre} (`{membre.id}`)")
    embed.add_field(name="Durée",      value=f"{duree} min")
    embed.add_field(name="Modérateur", value=interaction.user.mention)
    embed.add_field(name="Raison",     value=raison, inline=False)
    embed.add_field(name="MP envoyé",  value="✅ Oui" if dm_sent else "❌ Non (DMs fermés)")
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@tree.command(name="unmute", description="[Mod] Retire le mute d'un membre")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_unmute(interaction: discord.Interaction, membre: discord.Member):
    block_reason = get_moderation_block_reason(interaction, membre)
    if block_reason:
        await interaction.response.send_message(block_reason, ephemeral=True)
        return
    await membre.timeout(None)
    embed = discord.Embed(title="🔊 Membre démuté", color=0x57F287, timestamp=datetime.utcnow())
    embed.add_field(name="Membre",     value=f"{membre} (`{membre.id}`)")
    embed.add_field(name="Modérateur", value=interaction.user.mention)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@tree.command(name="warn", description="[Mod] Avertit un membre")
@app_commands.describe(membre="Membre à avertir", raison="Raison de l'avertissement")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    block_reason = get_moderation_block_reason(interaction, membre)
    if block_reason:
        await interaction.response.send_message(block_reason, ephemeral=True)
        return
    uid = membre.id
    if uid not in warns:
        warns[uid] = []
    warns[uid].append({
        "raison": raison,
        "mod":    str(interaction.user),
        "date":   datetime.utcnow().strftime("%d/%m/%Y %H:%M")
    })
    count = len(warns[uid])
    save_data()

    dm_embed = discord.Embed(
        title="⚠️ Tu as reçu un avertissement",
        description=f"Tu as été averti sur **{interaction.guild.name}**.",
        color=0xFFCC00, timestamp=datetime.utcnow()
    )
    dm_embed.add_field(name="Raison",          value=raison, inline=False)
    dm_embed.add_field(name="Modérateur",       value=str(interaction.user))
    dm_embed.add_field(name="Total warns",      value=f"{count}/3")
    dm_embed.set_footer(text="3 avertissements = ban automatique.")
    dm_sent = await send_dm(membre, dm_embed)

    embed = discord.Embed(
        title=f"⚠️ Avertissement ({count}/3)",
        color=0xFFCC00, timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="Membre",     value=f"{membre.mention} (`{membre.id}`)")
    embed.add_field(name="Modérateur", value=interaction.user.mention)
    embed.add_field(name="Raison",     value=raison, inline=False)
    embed.add_field(name="MP envoyé",  value="✅ Oui" if dm_sent else "❌ Non (DMs fermés)")
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)

    # Ban auto à 3 warns
    if count >= 3:
        ban_embed = discord.Embed(
            title="🔨 Ban automatique — 3 avertissements",
            description=f"{membre.mention} a été banni automatiquement après 3 warns.",
            color=0x8B0000, timestamp=datetime.utcnow()
        )
        try:
            await membre.ban(reason="3 avertissements atteints")
            warns.pop(uid, None)
            save_data()
            await interaction.channel.send(embed=ban_embed)
            await send_log(interaction.guild, ban_embed)
        except discord.Forbidden:
            pass


@tree.command(name="warns", description="Affiche les avertissements d'un membre")
@app_commands.describe(membre="Membre à consulter")
async def slash_warns(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    user_warns = warns.get(target.id, [])
    embed = discord.Embed(
        title=f"⚠️ Avertissements de {target.display_name}",
        color=0xFFCC00, timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    if not user_warns:
        embed.description = "✅ Aucun avertissement !"
    else:
        for i, w in enumerate(user_warns, 1):
            embed.add_field(
                name=f"Warn #{i} — {w['date']}",
                value=f"**Raison :** {w['raison']}\n**Mod :** {w['mod']}",
                inline=False
            )
    embed.set_footer(text=f"{len(user_warns)}/3 avertissements")
    await interaction.response.send_message(embed=embed)


@tree.command(name="clearwarns", description="[Mod] Efface les avertissements d'un membre")
@app_commands.checks.has_permissions(moderate_members=True)
async def slash_clearwarns(interaction: discord.Interaction, membre: discord.Member):
    block_reason = get_moderation_block_reason(interaction, membre)
    if block_reason:
        await interaction.response.send_message(block_reason, ephemeral=True)
        return
    warns.pop(membre.id, None)
    save_data()
    await interaction.response.send_message(
        f"✅ Avertissements de {membre.mention} effacés.", ephemeral=True
    )



# ════════════════════════════════════════════════════════════════
#  🧹  COMMANDES SUPPRESSION DE MESSAGES
# ════════════════════════════════════════════════════════════════

@tree.command(name="clear", description="[Mod] Supprime plusieurs messages d'un coup")
@app_commands.describe(
    nombre="Nombre de messages à supprimer (1-100)",
    membre="Supprimer seulement les messages de ce membre (optionnel)"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clear(interaction: discord.Interaction, nombre: int, membre: discord.Member = None):
    if nombre < 1 or nombre > 100:
        await interaction.response.send_message("❌ Entre 1 et 100 messages maximum.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    def check(m):
        if membre:
            return m.author.id == membre.id
        return True

    try:
        deleted = await interaction.channel.purge(limit=nombre, check=check)
        count   = len(deleted)

        # Réponse éphémère
        await interaction.followup.send(
            f"✅ **{count} message(s)** supprimé(s)"
            + (f" de {membre.mention}" if membre else "")
            + f" dans {interaction.channel.mention}.",
            ephemeral=True
        )

        # Log
        log_embed = discord.Embed(
            title="🧹 Messages supprimés",
            color=0xFF6B6B,
            timestamp=datetime.utcnow()
        )
        log_embed.add_field(name="🔨 Modérateur", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        log_embed.add_field(name="📌 Salon",       value=interaction.channel.mention,                            inline=True)
        log_embed.add_field(name="🗑️ Supprimés",   value=str(count),                                            inline=True)
        if membre:
            log_embed.add_field(name="👤 Ciblé",   value=f"{membre.mention} (`{membre.id}`)",                   inline=True)
        await send_log(interaction.guild, log_embed)

    except discord.Forbidden:
        await interaction.followup.send("❌ Je n'ai pas la permission de supprimer des messages.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)


@tree.command(name="clearuser", description="[Mod] Supprime tous les messages récents d'un membre dans ce salon")
@app_commands.describe(
    membre="Membre dont supprimer les messages",
    nombre="Nombre de messages à scanner (défaut: 100)"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def slash_clearuser(interaction: discord.Interaction, membre: discord.Member, nombre: int = 100):
    if nombre < 1 or nombre > 200:
        await interaction.response.send_message("❌ Entre 1 et 200 messages maximum.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=nombre, check=lambda m: m.author.id == membre.id)
        count   = len(deleted)

        await interaction.followup.send(
            f"✅ **{count} message(s)** de {membre.mention} supprimé(s).",
            ephemeral=True
        )

        log_embed = discord.Embed(
            title="🧹 Messages d'un membre supprimés",
            color=0xFF6B6B,
            timestamp=datetime.utcnow()
        )
        log_embed.add_field(name="🔨 Modérateur", value=f"{interaction.user.mention}",           inline=True)
        log_embed.add_field(name="👤 Ciblé",       value=f"{membre.mention} (`{membre.id}`)",    inline=True)
        log_embed.add_field(name="📌 Salon",        value=interaction.channel.mention,            inline=True)
        log_embed.add_field(name="🗑️ Supprimés",    value=str(count),                            inline=True)
        await send_log(interaction.guild, log_embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)




import enum, random as _random

class LGRole(enum.Enum):
    VILLAGEOIS  = "Villageois"
    LOUP_GAROU  = "Loup-Garou"
    VOYANTE     = "Voyante"
    SORCIERE    = "Sorcière"
    CHASSEUR    = "Chasseur"
    CUPIDON     = "Cupidon"
    SALVATEUR   = "Salvateur"

LG_ROLE_EMOJI = {
    LGRole.VILLAGEOIS:  "👨‍🌾",
    LGRole.LOUP_GAROU:  "🐺",
    LGRole.VOYANTE:     "🔮",
    LGRole.SORCIERE:    "🧙",
    LGRole.CHASSEUR:    "🏹",
    LGRole.CUPIDON:     "💘",
    LGRole.SALVATEUR:   "🛡️",
}

LG_ROLE_COLOR = {
    LGRole.LOUP_GAROU: 0x8B0000,
    LGRole.VOYANTE:    0x9B59B6,
    LGRole.SORCIERE:   0x27AE60,
    LGRole.CHASSEUR:   0xE67E22,
    LGRole.CUPIDON:    0xE91E8C,
    LGRole.SALVATEUR:  0x3498DB,
    LGRole.VILLAGEOIS: 0xF0C040,
}

LG_ROLE_DESC = {
    LGRole.VILLAGEOIS: "Tu es un simple villageois. Vote le jour pour éliminer les loups !",
    LGRole.LOUP_GAROU: "Tu es un Loup-Garou ! La nuit, coordonne-toi avec tes alliés pour dévorer un villageois.",
    LGRole.VOYANTE:    "Tu es la Voyante. Chaque nuit tu peux révéler le rôle d'un joueur.",
    LGRole.SORCIERE:   "Tu es la Sorcière. Tu possèdes une potion de vie et une potion de mort (une fois chacune).",
    LGRole.CHASSEUR:   "Tu es le Chasseur. En mourant, tu peux emporter quelqu'un avec toi.",
    LGRole.CUPIDON:    "Tu es Cupidon. La 1ère nuit, tu lies deux joueurs. Si l'un meurt, l'autre aussi.",
    LGRole.SALVATEUR:  "Tu es le Salvateur. Chaque nuit tu protèges un joueur de l'attaque des loups.",
}

def lg_assign_roles(n: int) -> list[LGRole]:
    """Distribue les rôles selon le nombre de joueurs."""
    wolves = max(1, n // 4)
    pool   = [LGRole.LOUP_GAROU] * wolves
    specials = [LGRole.VOYANTE, LGRole.SORCIERE, LGRole.CHASSEUR, LGRole.CUPIDON, LGRole.SALVATEUR]
    specials_count = min(len(specials), max(1, (n - wolves) // 3))
    pool += specials[:specials_count]
    while len(pool) < n:
        pool.append(LGRole.VILLAGEOIS)
    _random.shuffle(pool)
    return pool

# État des parties en cours
lg_games: dict[int, dict] = {}  # {channel_id: game}

class LGJoinView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=120)
        self.channel_id = channel_id

    @discord.ui.button(label="⚔️ Rejoindre la partie", style=discord.ButtonStyle.success, custom_id="lg_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = lg_games.get(self.channel_id)
        if not game or game["phase"] != "lobby":
            await interaction.response.send_message("❌ Plus de lobby disponible.", ephemeral=True)
            return
        if interaction.user in game["players"]:
            await interaction.response.send_message("✅ Tu es déjà inscrit !", ephemeral=True)
            return
        game["players"].append(interaction.user)
        count = len(game["players"])
        await interaction.response.send_message(
            f"⚔️ **{interaction.user.display_name}** a rejoint ! ({count} joueur{'s' if count > 1 else ''} inscrit{'s' if count > 1 else ''})",
            ephemeral=False
        )

    @discord.ui.button(label="🎲 Lancer la partie", style=discord.ButtonStyle.primary, custom_id="lg_start")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = lg_games.get(self.channel_id)
        if not game:
            await interaction.response.send_message("❌ Partie introuvable.", ephemeral=True)
            return
        if interaction.user.id != game["host"]:
            await interaction.response.send_message("❌ Seul l'hôte peut lancer la partie.", ephemeral=True)
            return
        if len(game["players"]) < 4:
            await interaction.response.send_message("❌ Il faut au moins 4 joueurs !", ephemeral=True)
            return
        await interaction.response.defer()
        await lg_start_game(self.channel_id, interaction.channel)


async def lg_start_game(channel_id: int, channel):
    game    = lg_games[channel_id]
    players = game["players"]
    roles   = lg_assign_roles(len(players))

    game["roles"]     = {p.id: r for p, r in zip(players, roles)}
    game["alive"]     = [p.id for p in players]
    game["phase"]     = "night"
    game["day"]       = 1
    game["witch_life"]  = True
    game["witch_death"] = True
    game["lover"]       = []
    game["protected"]   = None
    game["votes"]       = {}

    # Envoi des rôles en MP
    wolves = []
    for player, role in zip(players, roles):
        e = discord.Embed(
            title=f"{LG_ROLE_EMOJI[role]} Ton rôle : {role.value}",
            description=LG_ROLE_DESC[role],
            color=LG_ROLE_COLOR[role]
        )
        e.set_footer(text="🤫 Garde ça secret !")
        try:
            await player.send(embed=e)
        except Exception:
            pass
        if role == LGRole.LOUP_GAROU:
            wolves.append(player.display_name)

    # Annonce loups entre eux
    if wolves:
        wolf_players = [p for p in players if game["roles"][p.id] == LGRole.LOUP_GAROU]
        wolf_names   = ", ".join(f"**{p.display_name}**" for p in wolf_players)
        for wp in wolf_players:
            try:
                await wp.send(f"🐺 Tes alliés loups : {wolf_names}")
            except Exception:
                pass

    embed = discord.Embed(
        title="🌙 La nuit tombe sur le village...",
        description=(
            f"**{len(players)} joueurs** ont reçu leur rôle en message privé.\n\n\nLes loups-garous se réveillent et choisissent leur victime...\n\n\n**Composition :**\n" +
            "\n".join(f"{LG_ROLE_EMOJI[r]} {r.value}" for r in set(roles)) +
            "\n\n📨 Vérifiez vos messages privés pour connaître votre rôle !"
        ),
        color=0x2C2F33
    )
    embed.set_footer(text=f"Nuit 1 — Jour {game['day']}")
    await channel.send(embed=embed)
    await lg_night_phase(channel_id, channel)


async def lg_night_phase(channel_id: int, channel):
    game = lg_games.get(channel_id)
    if not game:
        return

    game["phase"]    = "night"
    game["votes"]    = {}
    game["protected"] = None
    alive_players    = [p for p in game["players"] if p.id in game["alive"]]

    # Liste pour vote loups
    alive_list = "\n".join(f"• **{p.display_name}**" for p in alive_players)

    # DM aux loups
    wolf_ids = [uid for uid, r in game["roles"].items() if r == LGRole.LOUP_GAROU and uid in game["alive"]]
    for uid in wolf_ids:
        wolf = next((p for p in alive_players if p.id == uid), None)
        if wolf:
            e = discord.Embed(
                title="🐺 Les loups se réveillent...",
                description=f"Choisissez votre victime parmi les joueurs vivants :\n{alive_list}\n\nUtilise `/lgvote @joueur` dans ce MP ou dans le salon de jeu.",
                color=0x8B0000
            )
            try:
                await wolf.send(embed=e)
            except Exception:
                pass

    # DM voyante
    voyante = next((p for p in alive_players if game["roles"].get(p.id) == LGRole.VOYANTE), None)
    if voyante:
        e = discord.Embed(
            title="🔮 La Voyante se réveille...",
            description=f"Tu peux utiliser `/lgvoir @joueur` pour révéler son rôle.\n\nJoueurs vivants :\n{alive_list}",
            color=0x9B59B6
        )
        try:
            await voyante.send(embed=e)
        except Exception:
            pass

    # Cupidon (jour 1 seulement)
    if game["day"] == 1:
        cupidon = next((p for p in alive_players if game["roles"].get(p.id) == LGRole.CUPIDON), None)
        if cupidon and not game["lover"]:
            e = discord.Embed(
                title="💘 Cupidon se réveille...",
                description=f"Utilise `/lglier @joueur1 @joueur2` pour lier deux âmes.\n\nJoueurs :\n{alive_list}",
                color=0xE91E8C
            )
            try:
                await cupidon.send(embed=e)
            except Exception:
                pass

    embed = discord.Embed(
        title="🌙 Nuit en cours...",
        description=(
            "Les rôles spéciaux agissent en messages privés.\n\n🐺 Les loups votent avec `/lgvote @joueur`\n\n🔮 La Voyante utilise `/lgvoir @joueur`\n\n🛡️ Le Salvateur utilise `/lgsauver @joueur`\n\n🧙 La Sorcière utilise `/lgpotion vie|mort @joueur`\n\n\n⏳ Utilisez `/lgnuit` quand tout le monde a joué."
        ),
        color=0x2C2F33
    )
    embed.set_footer(text=f"Nuit {game['day']}")
    await channel.send(embed=embed)


async def lg_check_win(channel_id: int, channel) -> bool:
    """Vérifie si la partie est terminée. Retourne True si fin."""
    game  = lg_games.get(channel_id)
    if not game:
        return True
    alive       = game["alive"]
    wolf_count  = sum(1 for uid in alive if game["roles"].get(uid) == LGRole.LOUP_GAROU)
    vill_count  = len(alive) - wolf_count

    if wolf_count == 0:
        embed = discord.Embed(
            title="🎉 Le Village a gagné !",
            description="Tous les loups-garous ont été éliminés ! Le village est sauvé. 🏡",
            color=0x57F287
        )
        embed.add_field(name="Survivants", value="\n".join(
            f"• {next((p.display_name for p in game['players'] if p.id == uid), str(uid))} — {LG_ROLE_EMOJI[game['roles'][uid]]} {game['roles'][uid].value}"
            for uid in alive
        ))
        await channel.send(embed=embed)
        del lg_games[channel_id]
        return True
    if wolf_count >= vill_count:
        embed = discord.Embed(
            title="🐺 Les Loups ont gagné !",
            description="Les loups-garous ont pris le contrôle du village ! 🌕",
            color=0x8B0000
        )
        await channel.send(embed=embed)
        del lg_games[channel_id]
        return True
    return False


@tree.command(name="loupgarou", description="🐺 Lance une partie de Loup-Garou")
async def slash_loupgarou(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    if ch_id in lg_games:
        await interaction.response.send_message("❌ Une partie est déjà en cours ici !", ephemeral=True)
        return
    lg_games[ch_id] = {
        "host":    interaction.user.id,
        "players": [interaction.user],
        "phase":   "lobby",
        "roles":   {}, "alive": [], "day": 1,
        "witch_life": True, "witch_death": True,
        "lover": [], "protected": None, "votes": {},
        "wolf_vote": {},
    }
    embed = discord.Embed(
        title="🐺 Loup-Garou — Lobby",
        description=(
            f"**{interaction.user.display_name}** ouvre une partie de Loup-Garou !\n\n"
            "🎮 Clique sur **Rejoindre** pour participer.\n"
            "▶️ L'hôte lance la partie quand tout le monde est prêt.\n\n"
            "**Minimum 4 joueurs requis.**\n\n"
            "**Rôles possibles :**\n"
            "🐺 Loup-Garou | 👨‍🌾 Villageois | 🔮 Voyante\n"
            "🧙 Sorcière | 🏹 Chasseur | 💘 Cupidon | 🛡️ Salvateur"
        ),
        color=0x8B0000
    )
    embed.set_footer(text="Le lobby ferme dans 2 minutes.")
    await interaction.response.send_message(embed=embed, view=LGJoinView(ch_id))


@tree.command(name="lgvote", description="🐺 [Loup-Garou] Vote pour dévorer un joueur (loups) ou éliminer (jour)")
@app_commands.describe(joueur="Joueur ciblé")
async def slash_lgvote(interaction: discord.Interaction, joueur: discord.Member):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game:
        await interaction.response.send_message("❌ Aucune partie en cours ici.", ephemeral=True)
        return
    uid = interaction.user.id
    if uid not in game["alive"]:
        await interaction.response.send_message("❌ Tu n'es pas (ou plus) dans la partie.", ephemeral=True)
        return
    if joueur.id not in game["alive"]:
        await interaction.response.send_message("❌ Ce joueur n'est pas en vie.", ephemeral=True)
        return
    if joueur.id == uid:
        await interaction.response.send_message("❌ Tu ne peux pas voter contre toi-même.", ephemeral=True)
        return

    game["votes"][uid] = joueur.id

    if game["phase"] == "night":
        role = game["roles"].get(uid)
        if role != LGRole.LOUP_GAROU:
            await interaction.response.send_message("❌ Seuls les loups votent la nuit.", ephemeral=True)
            return
        wolf_ids    = [i for i in game["alive"] if game["roles"].get(i) == LGRole.LOUP_GAROU]
        wolves_voted = sum(1 for i in wolf_ids if i in game["votes"])
        await interaction.response.send_message(
            f"🐺 Vote enregistré contre **{joueur.display_name}** ({wolves_voted}/{len(wolf_ids)} loups ont voté).",
            ephemeral=True
        )
    else:
        alive_ids    = game["alive"]
        voted_count  = len(game["votes"])
        await interaction.response.send_message(
            f"🗳️ Vote enregistré contre **{joueur.display_name}** ({voted_count}/{len(alive_ids)} votes).",
            ephemeral=True
        )


@tree.command(name="lgnuit", description="🌙 [Loup-Garou] Passe à la résolution de nuit")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_lgnuit(interaction: discord.Interaction):
    await interaction.response.defer()
    ch_id  = interaction.channel_id
    game   = lg_games.get(ch_id)
    if not game or game["phase"] != "night":
        await interaction.response.send_message("❌ Pas de phase nuit active.", ephemeral=True)
        return

    # Résolution vote loups
    wolf_ids = [i for i in game["alive"] if game["roles"].get(i) == LGRole.LOUP_GAROU]
    wolf_votes = {uid: game["votes"].get(uid) for uid in wolf_ids if game["votes"].get(uid)}

    victim_id = None
    if wolf_votes:
        from collections import Counter
        counts   = Counter(wolf_votes.values())
        victim_id = counts.most_common(1)[0][0]

    game["votes"] = {}
    players_map   = {p.id: p for p in game["players"]}

    deaths = []
    if victim_id and victim_id != game.get("protected"):
        deaths.append(victim_id)

    # Résolution sorcière (si elle a utilisé ses potions → géré séparément)
    witch_kill = game.pop("witch_kill_target", None)
    witch_save = game.pop("witch_save_target", None)

    if witch_save and victim_id in deaths:
        deaths.remove(victim_id)
    if witch_kill and witch_kill in game["alive"] and witch_kill not in deaths:
        deaths.append(witch_kill)

    # Amoureux
    for uid in list(deaths):
        for pair in game["lover"]:
            if uid in pair:
                other = [x for x in pair if x != uid]
                for o in other:
                    if o in game["alive"] and o not in deaths:
                        deaths.append(o)

    # Annonce
    embed = discord.Embed(title="🌅 L'aube se lève...", color=0xFFA500, timestamp=datetime.utcnow())
    if deaths:
        death_list = "\n".join(
            f"💀 **{players_map[uid].display_name}** — {LG_ROLE_EMOJI[game['roles'][uid]]} {game['roles'][uid].value}"
            for uid in deaths if uid in players_map
        )
        embed.description = f"Cette nuit, le village pleure ses morts :\n{death_list}"
        for uid in deaths:
            if uid in game["alive"]:
                game["alive"].remove(uid)
        # Chasseur
        for uid in deaths:
            if game["roles"].get(uid) == LGRole.CHASSEUR:
                embed.description += f"\n\n🏹 **{players_map[uid].display_name}** est le Chasseur ! Il peut emporter quelqu'un avec `/lgchasser @joueur`."
    else:
        embed.description = "✨ Miracle ! Personne n'est mort cette nuit."

    game["day"]   += 1
    game["phase"]  = "day"
    await interaction.response.send_message(embed=embed)

    if not await lg_check_win(ch_id, interaction.channel):
        alive_list = "\n".join(f"• **{players_map[uid].display_name}**" for uid in game["alive"])
        day_embed  = discord.Embed(
            title=f"☀️ Jour {game['day']} — Le village délibère",
            description=(
                f"**{len(game['alive'])} joueurs en vie :**\n{alive_list}\n\n"
                "🗳️ Votez pour éliminer un suspect avec `/lgvote @joueur`\n"
                "Quand tout le monde a voté, utilisez `/lgjour` pour résoudre le vote."
            ),
            color=0xF0C040
        )
        await interaction.channel.send(embed=day_embed)


@tree.command(name="lgjour", description="☀️ [Loup-Garou] Résout le vote du jour")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_lgjour(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game or game["phase"] != "day":
        await interaction.response.send_message("❌ Pas de phase jour active.", ephemeral=True)
        return
    from collections import Counter
    votes      = game["votes"]
    players_map = {p.id: p for p in game["players"]}

    if not votes:
        await interaction.response.send_message("❌ Personne n'a encore voté !", ephemeral=True)
        return

    counts  = Counter(votes.values())
    top_id  = counts.most_common(1)[0][0]
    role    = game["roles"].get(top_id, LGRole.VILLAGEOIS)

    game["alive"].remove(top_id) if top_id in game["alive"] else None
    game["votes"] = {}
    game["phase"] = "night"

    embed = discord.Embed(
        title="⚖️ Le village a voté !",
        description=(
            f"💀 **{players_map[top_id].display_name}** est éliminé !\n"
            f"Son rôle était : {LG_ROLE_EMOJI[role]} **{role.value}**"
        ),
        color=0xE74C3C, timestamp=datetime.utcnow()
    )

    # Chasseur éliminé de jour
    if role == LGRole.CHASSEUR:
        embed.description += f"\n🏹 Il peut emporter quelqu'un avec `/lgchasser @joueur`."

    # Amoureux
    for pair in game["lover"]:
        if top_id in pair:
            for o in pair:
                if o != top_id and o in game["alive"]:
                    game["alive"].remove(o)
                    embed.description += f"\n💔 **{players_map[o].display_name}** meurt de chagrin (amoureux)."

    await interaction.response.send_message(embed=embed)

    if not await lg_check_win(ch_id, interaction.channel):
        await lg_night_phase(ch_id, interaction.channel)


@tree.command(name="lgvoir", description="🔮 [Voyante] Révèle le rôle d'un joueur")
@app_commands.describe(joueur="Joueur à espionner")
async def slash_lgvoir(interaction: discord.Interaction, joueur: discord.Member):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game:
        await interaction.response.send_message("❌ Aucune partie en cours.", ephemeral=True)
        return
    if game["roles"].get(interaction.user.id) != LGRole.VOYANTE:
        await interaction.response.send_message("❌ Tu n'es pas la Voyante.", ephemeral=True)
        return
    role = game["roles"].get(joueur.id)
    if not role:
        await interaction.response.send_message("❌ Ce joueur n'est pas dans la partie.", ephemeral=True)
        return
    e = discord.Embed(
        title="🔮 Vision de la Voyante",
        description=f"**{joueur.display_name}** est {LG_ROLE_EMOJI[role]} **{role.value}**",
        color=0x9B59B6
    )
    await interaction.response.send_message(embed=e, ephemeral=True)


@tree.command(name="lgsauver", description="🛡️ [Salvateur] Protège un joueur cette nuit")
@app_commands.describe(joueur="Joueur à protéger")
async def slash_lgsauver(interaction: discord.Interaction, joueur: discord.Member):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game or game["roles"].get(interaction.user.id) != LGRole.SALVATEUR:
        await interaction.response.send_message("❌ Tu n'es pas le Salvateur.", ephemeral=True)
        return
    game["protected"] = joueur.id
    await interaction.response.send_message(f"🛡️ Tu protèges **{joueur.display_name}** cette nuit.", ephemeral=True)


@tree.command(name="lgpotion", description="🧙 [Sorcière] Utilise une potion")
@app_commands.describe(type="vie = sauver la victime, mort = tuer un joueur", joueur="Cible de la potion")
@app_commands.choices(type=[
    app_commands.Choice(name="💚 Vie  (sauver la victime des loups)", value="vie"),
    app_commands.Choice(name="💀 Mort (tuer un joueur)",              value="mort"),
])
async def slash_lgpotion(interaction: discord.Interaction, type: str, joueur: discord.Member):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game or game["roles"].get(interaction.user.id) != LGRole.SORCIERE:
        await interaction.response.send_message("❌ Tu n'es pas la Sorcière.", ephemeral=True)
        return
    if type == "vie":
        if not game["witch_life"]:
            await interaction.response.send_message("❌ Tu as déjà utilisé ta potion de vie.", ephemeral=True)
            return
        game["witch_life"]        = False
        game["witch_save_target"] = joueur.id
        await interaction.response.send_message(f"💚 Tu as utilisé ta potion de **vie** sur {joueur.mention}.", ephemeral=True)
    else:
        if not game["witch_death"]:
            await interaction.response.send_message("❌ Tu as déjà utilisé ta potion de mort.", ephemeral=True)
            return
        game["witch_death"]       = False
        game["witch_kill_target"] = joueur.id
        await interaction.response.send_message(f"☠️ Tu as utilisé ta potion de **mort** sur {joueur.mention}.", ephemeral=True)


@tree.command(name="lglier", description="💘 [Cupidon] Lie deux joueurs")
@app_commands.describe(joueur1="Premier amoureux", joueur2="Second amoureux")
async def slash_lglier(interaction: discord.Interaction, joueur1: discord.Member, joueur2: discord.Member):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game or game["roles"].get(interaction.user.id) != LGRole.CUPIDON:
        await interaction.response.send_message("❌ Tu n'es pas Cupidon.", ephemeral=True)
        return
    if game["lover"]:
        await interaction.response.send_message("❌ Tu as déjà lié deux joueurs.", ephemeral=True)
        return
    game["lover"] = [{joueur1.id, joueur2.id}]
    try:
        await joueur1.send(f"💘 Tu es lié(e) à **{joueur2.display_name}**. Si l'un de vous meurt, l'autre aussi !")
        await joueur2.send(f"💘 Tu es lié(e) à **{joueur1.display_name}**. Si l'un de vous meurt, l'autre aussi !")
    except Exception:
        pass
    await interaction.response.send_message(
        f"💘 Tu as lié **{joueur1.display_name}** et **{joueur2.display_name}**.", ephemeral=True
    )


@tree.command(name="lgchasser", description="🏹 [Chasseur] Emporte quelqu'un avec toi")
@app_commands.describe(joueur="Joueur à emporter")
async def slash_lgchasser(interaction: discord.Interaction, joueur: discord.Member):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game or game["roles"].get(interaction.user.id) != LGRole.CHASSEUR:
        await interaction.response.send_message("❌ Tu n'es pas le Chasseur.", ephemeral=True)
        return
    if interaction.user.id in game["alive"]:
        await interaction.response.send_message("❌ Tu dois être mort pour utiliser ce pouvoir.", ephemeral=True)
        return
    if joueur.id in game["alive"]:
        game["alive"].remove(joueur.id)
    role = game["roles"].get(joueur.id, LGRole.VILLAGEOIS)
    embed = discord.Embed(
        title="🏹 Le Chasseur tire !",
        description=f"💀 **{joueur.display_name}** est emporté par le Chasseur ! Son rôle : {LG_ROLE_EMOJI[role]} **{role.value}**",
        color=0xE67E22
    )
    await interaction.response.send_message(embed=embed)
    await lg_check_win(ch_id, interaction.channel)


@tree.command(name="lgstatus", description="🐺 Affiche l'état de la partie Loup-Garou en cours")
async def slash_lgstatus(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    game  = lg_games.get(ch_id)
    if not game:
        await interaction.response.send_message("❌ Aucune partie en cours.", ephemeral=True)
        return
    players_map = {p.id: p for p in game["players"]}
    alive_list  = "\n".join(f"✅ **{players_map[uid].display_name}**" for uid in game["alive"] if uid in players_map)
    dead_list   = "\n".join(
        f"💀 {players_map[uid].display_name} — {LG_ROLE_EMOJI[game['roles'][uid]]} {game['roles'][uid].value}"
        for uid in [p.id for p in game["players"]] if uid not in game["alive"] and uid in players_map
    )
    embed = discord.Embed(title="🐺 État de la partie", color=0x8B0000, timestamp=datetime.utcnow())
    embed.add_field(name=f"🟢 Vivants ({len(game['alive'])})", value=alive_list or "—", inline=False)
    if dead_list:
        embed.add_field(name="💀 Éliminés", value=dead_list, inline=False)
    embed.add_field(name="Phase", value=f"{'☀️ Jour' if game['phase'] == 'day' else '🌙 Nuit'} {game['day']}", inline=True)
    wolf_count = sum(1 for uid in game["alive"] if game["roles"].get(uid) == LGRole.LOUP_GAROU)
    embed.add_field(name="Loups restants", value=f"{'❓' * wolf_count}", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="lgarreter", description="🐺 [Admin] Arrête la partie de Loup-Garou en cours")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_lgarreter(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    if ch_id in lg_games:
        del lg_games[ch_id]
        await interaction.response.send_message("✅ Partie arrêtée.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucune partie en cours.", ephemeral=True)


# ════════════════════════════════════════════════════════════════
#  🔴  [16] JEU — PUISSANCE 4
# ════════════════════════════════════════════════════════════════

EMPTY  = "⬛"
RED    = "🔴"
YELLOW = "🟡"
ROWS, COLS = 6, 7

p4_games: dict[int, dict] = {}  # {channel_id: game_state}


def p4_create_board():
    return [[EMPTY]*COLS for _ in range(ROWS)]


def p4_drop(board, col, piece):
    for row in range(ROWS-1, -1, -1):
        if board[row][col] == EMPTY:
            board[row][col] = piece
            return row
    return -1


def p4_check_win(board, piece):
    # Horizontal
    for r in range(ROWS):
        for c in range(COLS-3):
            if all(board[r][c+i] == piece for i in range(4)):
                return True
    # Vertical
    for r in range(ROWS-3):
        for c in range(COLS):
            if all(board[r+i][c] == piece for i in range(4)):
                return True
    # Diagonale /
    for r in range(3, ROWS):
        for c in range(COLS-3):
            if all(board[r-i][c+i] == piece for i in range(4)):
                return True
    # Diagonale \
    for r in range(ROWS-3):
        for c in range(COLS-3):
            if all(board[r+i][c+i] == piece for i in range(4)):
                return True
    return False


def p4_is_full(board):
    return all(board[0][c] != EMPTY for c in range(COLS))


def p4_render(board, game):
    """Retourne l'affichage du plateau."""
    header = "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
    rows   = "\n".join("".join(row) for row in board)
    turn   = game["players"][game["turn"]]
    piece  = RED if game["turn"] == 0 else YELLOW
    status = f"\n{piece} Au tour de **{turn.display_name}**"
    return f"{header}\n{rows}{status}"


class P4View(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        # Boutons colonnes 1-7
        for col in range(COLS):
            btn = discord.ui.Button(
                label=str(col+1),
                style=discord.ButtonStyle.primary,
                custom_id=f"p4_{col}",
                row=0 if col < 4 else 1
            )
            btn.callback = self.make_callback(col)
            self.add_item(btn)

    def make_callback(self, col: int):
        async def callback(interaction: discord.Interaction):
            game = p4_games.get(self.channel_id)
            if not game:
                await interaction.response.send_message("❌ Partie introuvable.", ephemeral=True)
                return

            current_player = game["players"][game["turn"]]
            if interaction.user.id != current_player.id:
                await interaction.response.send_message(
                    f"❌ Ce n'est pas ton tour ! C'est le tour de **{current_player.display_name}**.",
                    ephemeral=True
                )
                return

            board = game["board"]
            piece = RED if game["turn"] == 0 else YELLOW

            row = p4_drop(board, col, piece)
            if row == -1:
                await interaction.response.send_message("❌ Cette colonne est pleine !", ephemeral=True)
                return

            # Victoire ?
            if p4_check_win(board, piece):
                header = "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
                board_str = "\n".join("".join(r) for r in board)
                embed = discord.Embed(
                    title=f"🏆 {current_player.display_name} gagne !",
                    description=f"{header}\n{board_str}\n\n{piece} **{current_player.display_name}** remporte la partie !",
                    color=0xFFD700
                )
                embed.set_thumbnail(url=current_player.display_avatar.url)
                del p4_games[self.channel_id]
                view = discord.ui.View()
                await interaction.response.edit_message(embed=embed, view=view)
                return

            # Match nul ?
            if p4_is_full(board):
                header = "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
                board_str = "\n".join("".join(r) for r in board)
                embed = discord.Embed(
                    title="🤝 Match nul !",
                    description=f"{header}\n{board_str}\n\nLe plateau est plein — aucun gagnant !",
                    color=0x95a5a6
                )
                del p4_games[self.channel_id]
                view = discord.ui.View()
                await interaction.response.edit_message(embed=embed, view=view)
                return

            # Prochain tour
            game["turn"] = 1 - game["turn"]
            embed = discord.Embed(
                title="🔴🟡 Puissance 4",
                description=p4_render(board, game),
                color=0x3498db
            )
            p1, p2 = game["players"]
            embed.set_footer(text=f"🔴 {p1.display_name}  vs  🟡 {p2.display_name}")
            await interaction.response.edit_message(embed=embed, view=P4View(self.channel_id))

        return callback

    async def on_timeout(self):
        game = p4_games.pop(self.channel_id, None)
        if game:
            pass  # La partie expire silencieusement


# ── IA Puissance 4 ──────────────────────────────────────────────

def p4_score_window(window, piece, opp):
    """Score une fenêtre de 4 cases."""
    score = 0
    if window.count(piece) == 4:
        score += 100
    elif window.count(piece) == 3 and window.count(EMPTY) == 1:
        score += 5
    elif window.count(piece) == 2 and window.count(EMPTY) == 2:
        score += 2
    if window.count(opp) == 3 and window.count(EMPTY) == 1:
        score -= 4
    return score


def p4_score_board(board, piece):
    """Évalue le plateau pour la pièce donnée."""
    opp   = RED if piece == YELLOW else YELLOW
    score = 0
    # Centre favorisé
    center = [board[r][COLS//2] for r in range(ROWS)]
    score += center.count(piece) * 3
    # Horizontal
    for r in range(ROWS):
        for c in range(COLS-3):
            score += p4_score_window([board[r][c+i] for i in range(4)], piece, opp)
    # Vertical
    for c in range(COLS):
        for r in range(ROWS-3):
            score += p4_score_window([board[r+i][c] for i in range(4)], piece, opp)
    # Diagonales
    for r in range(ROWS-3):
        for c in range(COLS-3):
            score += p4_score_window([board[r+i][c+i] for i in range(4)], piece, opp)
    for r in range(3, ROWS):
        for c in range(COLS-3):
            score += p4_score_window([board[r-i][c+i] for i in range(4)], piece, opp)
    return score


def p4_get_valid_cols(board):
    return [c for c in range(COLS) if board[0][c] == EMPTY]


def p4_minimax(board, depth, alpha, beta, maximizing, ai_piece):
    """Minimax avec élagage alpha-beta."""
    opp = RED if ai_piece == YELLOW else YELLOW
    valid = p4_get_valid_cols(board)

    if p4_check_win(board, ai_piece):
        return (None, 100000 + depth)
    if p4_check_win(board, opp):
        return (None, -100000 - depth)
    if not valid or depth == 0:
        return (None, p4_score_board(board, ai_piece))

    if maximizing:
        best = (None, -float("inf"))
        for col in valid:
            b2 = [row[:] for row in board]
            p4_drop(b2, col, ai_piece)
            _, sc = p4_minimax(b2, depth-1, alpha, beta, False, ai_piece)
            if sc > best[1]:
                best = (col, sc)
            alpha = max(alpha, sc)
            if alpha >= beta:
                break
        return best
    else:
        best = (None, float("inf"))
        for col in valid:
            b2 = [row[:] for row in board]
            p4_drop(b2, col, opp)
            _, sc = p4_minimax(b2, depth-1, alpha, beta, True, ai_piece)
            if sc < best[1]:
                best = (col, sc)
            beta = min(beta, sc)
            if alpha >= beta:
                break
        return best


def p4_ai_move(board, ai_piece, difficulty="hard"):
    """Retourne la colonne choisie par l'IA."""
    import random
    valid = p4_get_valid_cols(board)
    if difficulty == "easy":
        return random.choice(valid)
    depth = 4 if difficulty == "medium" else 6
    col, _ = p4_minimax(board, depth, -float("inf"), float("inf"), True, ai_piece)
    return col if col is not None else random.choice(valid)

KAKEGURUI_GIF = "https://giffiles.alphacoders.com/138/138177.gif"


class P4ViewAI(discord.ui.View):
    """Vue Puissance 4 contre l'IA."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        for col in range(COLS):
            btn = discord.ui.Button(
                label=str(col+1),
                style=discord.ButtonStyle.primary,
                custom_id=f"p4ai_{col}",
                row=0 if col < 4 else 1
            )
            btn.callback = self.make_callback(col)
            self.add_item(btn)

    def make_callback(self, col: int):
        async def callback(interaction: discord.Interaction):
            game = p4_games.get(self.channel_id)
            if not game or not game.get("vs_ai"):
                await interaction.response.send_message("❌ Partie introuvable.", ephemeral=True)
                return

            player = game["players"][0]
            if interaction.user.id != player.id:
                await interaction.response.send_message("❌ Ce n'est pas ta partie !", ephemeral=True)
                return

            board     = game["board"]
            ai_piece  = game["ai_piece"]
            usr_piece = game["usr_piece"]

            # ── Tour du joueur ───────────────────────────
            row = p4_drop(board, col, usr_piece)
            if row == -1:
                await interaction.response.send_message("❌ Colonne pleine !", ephemeral=True)
                return

            if p4_check_win(board, usr_piece):
                board_str = "\n".join("".join(r) for r in board)
                embed = discord.Embed(
                    title=f"🏆 {player.display_name} gagne !",
                    description=f"1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n{board_str}\n\n{usr_piece} Tu as battu le bot, bravo !",
                    color=0xFFD700
                )
                embed.set_thumbnail(url=player.display_avatar.url)
                del p4_games[self.channel_id]
                await interaction.response.edit_message(embed=embed, view=discord.ui.View())
                return

            if p4_is_full(board):
                board_str = "\n".join("".join(r) for r in board)
                embed = discord.Embed(title="🤝 Match nul !", description=f"1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n{board_str}", color=0x95a5a6)
                del p4_games[self.channel_id]
                await interaction.response.edit_message(embed=embed, view=discord.ui.View())
                return

            # ── Tour de l'IA ─────────────────────────────
            ai_col = p4_ai_move(board, ai_piece, game.get("difficulty", "hard"))
            p4_drop(board, ai_col, ai_piece)

            if p4_check_win(board, ai_piece):
                board_str = "\n".join("".join(r) for r in board)
                embed = discord.Embed(
                    title="🤖 Le bot gagne !",
                    description=f"1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n{board_str}\n\n**KAKEGURUI MASHOOOOOOO** 🎰",
                    color=0x8B0000
                )
                embed.set_image(url=KAKEGURUI_GIF)
                embed.set_footer(text="Tu n'étais pas de taille... 😈")
                del p4_games[self.channel_id]
                await interaction.response.edit_message(embed=embed, view=discord.ui.View())
                return

            if p4_is_full(board):
                board_str = "\n".join("".join(r) for r in board)
                embed = discord.Embed(title="🤝 Match nul !", description=f"1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n{board_str}", color=0x95a5a6)
                del p4_games[self.channel_id]
                await interaction.response.edit_message(embed=embed, view=discord.ui.View())
                return

            # ── Affiche le plateau mis à jour ─────────────
            board_str = "\n".join("".join(r) for r in board)
            embed = discord.Embed(
                title="🔴🟡 Puissance 4 — vs Bot",
                description=f"1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n{board_str}\n\n{usr_piece} À toi de jouer, **{player.display_name}** !",
                color=0x3498db
            )
            embed.set_footer(text=f"🔴 {player.display_name}  vs  🟡 Bot | Difficulté : {game.get('difficulty','hard')}")
            await interaction.response.edit_message(embed=embed, view=P4ViewAI(self.channel_id))

        return callback

    async def on_timeout(self):
        p4_games.pop(self.channel_id, None)


@game_group.command(name="puissance4", description="🔴🟡 Lance une partie de Puissance 4")
@app_commands.describe(
    adversaire="Un joueur à défier (laisse vide pour jouer contre le bot)",
    difficulte="Difficulté du bot (facile/moyen/difficile)"
)
@app_commands.choices(difficulte=[
    app_commands.Choice(name="Facile",    value="easy"),
    app_commands.Choice(name="Moyen",     value="medium"),
    app_commands.Choice(name="Difficile", value="hard"),
])
async def slash_puissance4(
    interaction: discord.Interaction,
    adversaire: discord.Member = None,
    difficulte: str = "hard"
):
    ch_id = interaction.channel_id
    if ch_id in p4_games:
        await interaction.response.send_message("❌ Une partie est déjà en cours dans ce salon !", ephemeral=True)
        return

    board = p4_create_board()

    # ── Contre le bot ────────────────────────────────────
    if adversaire is None or adversaire.bot:
        game = {
            "board":      board,
            "players":    [interaction.user],
            "vs_ai":      True,
            "usr_piece":  RED,
            "ai_piece":   YELLOW,
            "difficulty": difficulte,
        }
        p4_games[ch_id] = game
        board_str = "\n".join("".join(r) for r in board)
        embed = discord.Embed(
            title="🔴🟡 Puissance 4 — vs Bot",
            description=f"1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣\n{board_str}\n\n{RED} À toi de commencer, **{interaction.user.display_name}** !",
            color=0x3498db
        )
        embed.set_footer(text=f"🔴 {interaction.user.display_name}  vs  🟡 Bot | Difficulté : {difficulte}")
        await interaction.response.send_message(embed=embed, view=P4ViewAI(ch_id))
        return

    # ── Contre un joueur ─────────────────────────────────
    if adversaire.id == interaction.user.id:
        await interaction.response.send_message("❌ Tu ne peux pas jouer contre toi-même !", ephemeral=True)
        return

    game = {
        "board":   board,
        "players": [interaction.user, adversaire],
        "turn":    0,
        "vs_ai":   False,
    }
    p4_games[ch_id] = game
    embed = discord.Embed(
        title="🔴🟡 Puissance 4",
        description=p4_render(board, game),
        color=0x3498db
    )
    embed.set_footer(text=f"🔴 {interaction.user.display_name}  vs  🟡 {adversaire.display_name}")
    await interaction.response.send_message(
        content=f"{interaction.user.mention} 🆚 {adversaire.mention}",
        embed=embed,
        view=P4View(ch_id)
    )



# ════════════════════════════════════════════════════════════════
#  🎮  JEUX SUPPLÉMENTAIRES
# ════════════════════════════════════════════════════════════════

# ── PENDU ───────────────────────────────────────────────────────
PENDU_MOTS = [
    "taverne","dragon","chevalier","magicien","elfe","nain","trésor",
    "épée","bouclier","potion","donjon","château","aventurier","quête",
    "armure","forêt","montagne","sorcier","guerrier","rôdeur","paladin",
    "vampire","loup-garou","fantôme","golem","grotte","parchemin","baguette",
    "arc","flèche","hache","marteau","dague","sort","magie","oracle",
    "basilic","griffon","phénix","licorne","gobelins","trolls","ogre",
]

pendu_parties: dict[int, dict] = {}  # {channel_id: état}

PENDU_HANGMAN = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]

def pendu_afficher(etat: dict) -> str:
    mot     = etat["mot"]
    trouve  = etat["trouve"]
    affiche = " ".join(l if l in trouve else "_" for l in mot)
    erreurs = etat["erreurs"]
    lettres = etat["lettres_essayees"]
    return (
        f"{PENDU_HANGMAN[erreurs]}\n"
        f"**Mot :** `{affiche}`\n"
        f"**Erreurs :** {erreurs}/6\n"
        f"**Lettres essayées :** {', '.join(sorted(lettres)) or 'Aucune'}"
    )

@game_group.command(name="pendu", description="🪢 Lance une partie de Pendu")
async def slash_pendu(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    if ch_id in pendu_parties:
        partie = pendu_parties[ch_id]
        await interaction.response.send_message(
            f"❌ Une partie de pendu est déjà en cours dans ce salon avec <@{partie['user_id']}>.",
            ephemeral=True
        )
        return
    import random as _r
    mot = _r.choice(PENDU_MOTS).lower()
    pendu_parties[ch_id] = {
        "mot": mot, "trouve": set(), "erreurs": 0,
        "lettres_essayees": set(), "user_id": interaction.user.id
    }
    etat  = pendu_parties[ch_id]
    embed = discord.Embed(title="🪢 Pendu — La Taverne", description=pendu_afficher(etat), color=0x8B0000)
    embed.add_field(name="Joueur", value=interaction.user.mention, inline=True)
    embed.add_field(name="Contrôle", value="`/jeu pendu_lettre` ou `/jeu pendu_stop`", inline=True)
    embed.set_footer(text="Seul le joueur ayant lancé la partie peut proposer une lettre.")
    await interaction.response.send_message(embed=embed)

@game_group.command(name="pendu_lettre", description="🪢 Propose une lettre au Pendu")
@app_commands.describe(lettre="Une lettre à proposer")
async def slash_pendu_lettre(interaction: discord.Interaction, lettre: str):
    ch_id = interaction.channel_id
    if ch_id not in pendu_parties:
        await interaction.response.send_message("❌ Aucune partie en cours. Lance `/pendu` !", ephemeral=True)
        return
    etat   = pendu_parties[ch_id]
    if interaction.user.id != etat["user_id"]:
        await interaction.response.send_message("❌ Cette partie ne t'appartient pas.", ephemeral=True)
        return
    lettre = lettre.lower().strip()
    if len(lettre) != 1 or not lettre.isalpha():
        await interaction.response.send_message("❌ Entre une seule lettre !", ephemeral=True)
        return
    if lettre in etat["lettres_essayees"]:
        await interaction.response.send_message(f"❌ Tu as déjà essayé **{lettre}** !", ephemeral=True)
        return
    etat["lettres_essayees"].add(lettre)
    if lettre in etat["mot"]:
        etat["trouve"].add(lettre)
    else:
        etat["erreurs"] += 1
    mot_complet = all(l in etat["trouve"] for l in etat["mot"])
    perdu       = etat["erreurs"] >= 6
    if mot_complet:
        del pendu_parties[ch_id]
        embed = discord.Embed(title="🎉 Gagné !", description=f"Bravo {interaction.user.mention} ! Le mot était **{etat['mot']}** !", color=0x57F287)
    elif perdu:
        del pendu_parties[ch_id]
        embed = discord.Embed(title="💀 Perdu !", description=f"{PENDU_HANGMAN[6]}\nLe mot était **{etat['mot']}**. Dommage !", color=0xED4245)
    else:
        embed = discord.Embed(title="🪢 Pendu — La Taverne", description=pendu_afficher(etat), color=0x8B0000)
        embed.set_footer(text="Tape /jeu pendu_lettre [lettre] pour continuer !")
    await interaction.response.send_message(embed=embed)

@game_group.command(name="pendu_stop", description="🪢 Arrête la partie de Pendu en cours")
async def slash_pendu_stop(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    if ch_id in pendu_parties:
        partie = pendu_parties[ch_id]
        if interaction.user.id != partie["user_id"] and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Seul le joueur ayant lancé la partie peut l'arrêter.", ephemeral=True)
            return
        mot = pendu_parties.pop(ch_id)["mot"]
        await interaction.response.send_message(f"🛑 Partie arrêtée. Le mot était **{mot}**.")
    else:
        await interaction.response.send_message("❌ Aucune partie en cours.", ephemeral=True)


# ── MORPION ─────────────────────────────────────────────────────
morpion_parties: dict[int, dict] = {}

def morpion_afficher(grille: list) -> str:
    lignes = []
    symboles = {0: "⬜", 1: "❌", 2: "⭕"}
    for i in range(3):
        lignes.append("".join(symboles[grille[i*3+j]] for j in range(3)))
    return "\n".join(lignes)

def morpion_verifier(grille: list) -> int:
    combos = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in combos:
        if grille[a] == grille[b] == grille[c] != 0:
            return grille[a]
    return 0

def morpion_embed(partie: dict, description: str = None, color: int = 0x8B0000, title: str = "⭕❌ Morpion") -> discord.Embed:
    if description is None:
        symbole = "❌" if partie["tour"] == 1 else "⭕"
        prochain = partie["joueurs"][partie["tour"] - 1]
        description = f"{morpion_afficher(partie['grille'])}\n\nTour de <@{prochain}> {symbole}"
    embed = discord.Embed(title=title, description=description, color=color)
    embed.add_field(name="Joueurs", value=f"❌ <@{partie['joueurs'][0]}> | ⭕ <@{partie['joueurs'][1]}>", inline=False)
    return embed

class MorpionView(discord.ui.View):
    def __init__(self, ch_id: int):
        super().__init__(timeout=120)
        self.ch_id = ch_id
        self.message = None
        partie = morpion_parties[ch_id]
        for i in range(9):
            val = partie["grille"][i]
            label = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"][i] if val == 0 else ("❌" if val == 1 else "⭕")
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=i//3, custom_id=f"morp_{i}")
            btn.disabled = (val != 0)
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, idx: int):
        async def callback(interaction: discord.Interaction):
            ch_id   = self.ch_id
            partie  = morpion_parties.get(ch_id)
            if not partie:
                await interaction.response.send_message("❌ Partie terminée.", ephemeral=True)
                return
            tour = partie["tour"]
            joueurs = partie["joueurs"]
            if interaction.user.id != joueurs[tour - 1]:
                await interaction.response.send_message(f"❌ C'est au tour de {'❌' if tour==1 else '⭕'} !", ephemeral=True)
                return
            if partie["grille"][idx] != 0:
                await interaction.response.send_message("❌ Cette case est déjà prise.", ephemeral=True)
                return
            partie["grille"][idx] = tour
            gagnant = morpion_verifier(partie["grille"])
            nul     = all(c != 0 for c in partie["grille"])
            if gagnant or nul:
                del morpion_parties[ch_id]
                for item in self.children:
                    item.disabled = True
                if gagnant:
                    desc = f"{morpion_afficher(partie['grille'])}\n\n🏆 {'❌' if gagnant==1 else '⭕'} {interaction.user.mention} **gagne !**"
                    color = 0x57F287
                else:
                    desc = f"{morpion_afficher(partie['grille'])}\n\n🤝 **Match nul !**"
                    color = 0xFFA500
                embed = morpion_embed(partie, description=desc, color=color)
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                partie["tour"] = 2 if tour == 1 else 1
                new_view = MorpionView(ch_id)
                new_view.message = interaction.message
                embed = morpion_embed(partie)
                await interaction.response.edit_message(embed=embed, view=new_view)
        return callback

    async def on_timeout(self):
        partie = morpion_parties.pop(self.ch_id, None)
        if not partie or not self.message:
            return
        for item in self.children:
            item.disabled = True
        embed = morpion_embed(
            partie,
            description=f"{morpion_afficher(partie['grille'])}\n\n⌛ La partie a expiré faute d'activité.",
            color=0x95A5A6,
            title="⭕❌ Morpion — Expiré"
        )
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

@game_group.command(name="morpion", description="⭕❌ Lance une partie de Morpion contre un ami")
@app_commands.describe(adversaire="Ton adversaire")
async def slash_morpion(interaction: discord.Interaction, adversaire: discord.Member):
    if adversaire.bot or adversaire.id == interaction.user.id:
        await interaction.response.send_message("❌ Choisis un vrai adversaire !", ephemeral=True)
        return
    ch_id = interaction.channel_id
    if ch_id in morpion_parties:
        await interaction.response.send_message("❌ Une partie de Morpion est déjà en cours dans ce salon.", ephemeral=True)
        return
    morpion_parties[ch_id] = {
        "grille": [0]*9, "tour": 1,
        "joueurs": [interaction.user.id, adversaire.id]
    }
    embed = morpion_embed(morpion_parties[ch_id])
    view = MorpionView(ch_id)
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()

@game_group.command(name="morpion_stop", description="⭕❌ Arrête la partie de Morpion en cours")
async def slash_morpion_stop(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    partie = morpion_parties.get(ch_id)
    if not partie:
        await interaction.response.send_message("❌ Aucune partie de Morpion en cours.", ephemeral=True)
        return
    if interaction.user.id not in partie["joueurs"] and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Seuls les joueurs peuvent arrêter cette partie.", ephemeral=True)
        return
    morpion_parties.pop(ch_id, None)
    await interaction.response.send_message("🛑 Partie de Morpion arrêtée.")


# ── BLACKJACK ────────────────────────────────────────────────────
import random as _bj_random

def bj_deck():
    cartes = ["2","3","4","5","6","7","8","9","10","V","D","R","A"] * 4
    _bj_random.shuffle(cartes)
    return cartes

def bj_valeur(carte: str) -> int:
    if carte in ("V","D","R"): return 10
    if carte == "A": return 11
    return int(carte)

def bj_score(main: list) -> int:
    total = sum(bj_valeur(c) for c in main)
    aces  = main.count("A")
    while total > 21 and aces:
        total -= 10; aces -= 1
    return total

def bj_afficher(main: list, cacher: bool = False) -> str:
    if cacher:
        return f"🂠 {main[1]} | Score: ?"
    return f"{' '.join(main)} | Score: **{bj_score(main)}**"

bj_parties: dict[int, dict] = {}

def bj_build_embed(p: dict, title: str = "🃏 Blackjack", message: str = "Tire une carte ou reste ?", reveal_croupier: bool = False, color: int = 0x8B0000) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=(
            f"Joueur : {bj_afficher(p['joueur'])}\n"
            f"Croupier : {bj_afficher(p['croupier'], cacher=not reveal_croupier)}\n\n"
            f"{message}"
        ),
        color=color
    )

class BlackjackView(discord.ui.View):
    def __init__(self, user_id: int, ch_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.ch_id   = ch_id
        self.message = None

    @discord.ui.button(label="🃏 Tirer", style=discord.ButtonStyle.primary)
    async def tirer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Ce n'est pas ta partie !", ephemeral=True); return
        p = bj_parties.get(self.ch_id)
        if not p:
            await interaction.response.send_message("❌ Partie terminée.", ephemeral=True); return
        p["joueur"].append(p["deck"].pop())
        score = bj_score(p["joueur"])
        if score > 21:
            del bj_parties[self.ch_id]
            for item in self.children: item.disabled = True
            embed = bj_build_embed(
                p,
                title="🃏 Blackjack — Perdu !",
                message="💥 **Bust ! Tu dépasses 21.**",
                reveal_croupier=True,
                color=0xED4245
            )
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            embed = bj_build_embed(p)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🛑 Rester", style=discord.ButtonStyle.success)
    async def rester(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Ce n'est pas ta partie !", ephemeral=True); return
        p = bj_parties.get(self.ch_id)
        if not p:
            await interaction.response.send_message("❌ Partie terminée.", ephemeral=True); return
        while bj_score(p["croupier"]) < 17:
            p["croupier"].append(p["deck"].pop())
        js = bj_score(p["joueur"]); cs = bj_score(p["croupier"])
        del bj_parties[self.ch_id]
        for item in self.children: item.disabled = True
        if cs > 21 or js > cs:
            titre, msg, color = "🃏 Blackjack — Gagné !", "🏆 **Tu gagnes !**", 0x57F287
        elif js == cs:
            titre, msg, color = "🃏 Blackjack — Égalité !", "🤝 **Égalité !**", 0xFFA500
        else:
            titre, msg, color = "🃏 Blackjack — Perdu !", "💀 **Le croupier gagne.**", 0xED4245
        embed = bj_build_embed(p, title=titre, message=msg, reveal_croupier=True, color=color)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        p = bj_parties.pop(self.ch_id, None)
        if not p or not self.message:
            return
        for item in self.children:
            item.disabled = True
        embed = bj_build_embed(
            p,
            title="🃏 Blackjack — Expiré",
            message="⌛ La partie a expiré faute d'action.",
            reveal_croupier=True,
            color=0x95A5A6
        )
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

@game_group.command(name="blackjack", description="🃏 Lance une partie de Blackjack contre le croupier")
async def slash_blackjack(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    if ch_id in bj_parties:
        await interaction.response.send_message("❌ Une partie de Blackjack est déjà en cours dans ce salon.", ephemeral=True)
        return
    deck = bj_deck()
    joueur   = [deck.pop(), deck.pop()]
    croupier = [deck.pop(), deck.pop()]
    bj_parties[ch_id] = {"joueur": joueur, "croupier": croupier, "deck": deck, "owner_id": interaction.user.id}
    p = bj_parties[ch_id]
    js = bj_score(joueur)
    cs = bj_score(croupier)
    if js == 21 or cs == 21:
        if js == 21 and cs == 21:
            titre, msg, color = "🃏 Blackjack — Égalité !", "🤝 Double blackjack.", 0xFFA500
        elif js == 21:
            titre, msg, color = "🃏 Blackjack — Blackjack !", "🏆 Blackjack naturel, tu gagnes immédiatement !", 0x57F287
        else:
            titre, msg, color = "🃏 Blackjack — Perdu !", "💀 Le croupier a un blackjack naturel.", 0xED4245
        bj_parties.pop(ch_id, None)
        await interaction.response.send_message(embed=bj_build_embed(p, title=titre, message=msg, reveal_croupier=True, color=color))
        return
    view = BlackjackView(interaction.user.id, ch_id)
    await interaction.response.send_message(embed=bj_build_embed(p), view=view)
    view.message = await interaction.original_response()

@game_group.command(name="blackjack_stop", description="🃏 Arrête la partie de Blackjack en cours")
async def slash_blackjack_stop(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    partie = bj_parties.get(ch_id)
    if not partie:
        await interaction.response.send_message("❌ Aucune partie de Blackjack en cours.", ephemeral=True)
        return
    if interaction.user.id != partie["owner_id"] and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Seul le joueur ayant lancé la partie peut l'arrêter.", ephemeral=True)
        return
    bj_parties.pop(ch_id, None)
    await interaction.response.send_message("🛑 Partie de Blackjack arrêtée.")


# ── UNO ─────────────────────────────────────────────────────────
UNO_COULEURS  = ["🔴","🔵","🟢","🟡"]
UNO_VALEURS   = ["0","1","2","3","4","5","6","7","8","9","Skip","Reverse","+2"]
UNO_SPECIAUX  = ["🌈 Joker","🌈 +4"]

def uno_deck():
    cartes = [f"{c} {v}" for c in UNO_COULEURS for v in UNO_VALEURS] + UNO_SPECIAUX * 2
    import random as _ur; _ur.shuffle(cartes)
    return cartes

def uno_couleur(carte: str) -> str:
    for c in UNO_COULEURS:
        if carte.startswith(c): return c
    return "🌈"

def uno_valeur(carte: str) -> str:
    return carte.split(" ", 1)[-1] if " " in carte else carte

def uno_compatible(carte: str, dessus: str) -> bool:
    if uno_couleur(carte) == "🌈": return True
    return uno_couleur(carte) == uno_couleur(dessus) or uno_valeur(carte) == uno_valeur(dessus)

uno_parties: dict[int, dict] = {}

def uno_format_main(main: list[str]) -> str:
    if not main:
        return "Aucune carte."
    return "\n".join(f"`{i+1}.` {carte}" for i, carte in enumerate(main))

def uno_build_embed(partie: dict, note: str = None, title: str = "🎴 UNO — La Taverne", color: int = 0xED4245) -> discord.Embed:
    tour_id = partie["joueurs"][partie["tour"]]
    sens = "↻" if partie["sens"] == 1 else "↺"
    compteurs = "\n".join(
        f"{'👉 ' if idx == partie['tour'] else ''}<@{uid}> : **{len(partie['mains'][uid])}** carte(s)"
        for idx, uid in enumerate(partie["joueurs"])
    )
    description = (
        f"**Carte du dessus :** {partie['dessus']}\n"
        f"**Tour de :** <@{tour_id}>\n"
        f"**Sens :** {sens}\n"
        f"**Pioche restante :** {len(partie['deck'])} carte(s)\n\n"
        f"**Mains :**\n{compteurs}"
    )
    if note:
        description += f"\n\n{note}"
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="Utilise les boutons pour voir ta main, jouer une carte ou piocher.")
    return embed

def uno_main_embed(partie: dict, user_id: int) -> discord.Embed:
    main = partie["mains"][user_id]
    jouables = [str(i + 1) for i, carte in enumerate(main) if uno_compatible(carte, partie["dessus"])]
    embed = discord.Embed(
        title="🎴 Ta main UNO",
        description=uno_format_main(main),
        color=0xF1C40F
    )
    embed.add_field(name="Carte du dessus", value=partie["dessus"], inline=True)
    embed.add_field(name="Cartes jouables", value=", ".join(jouables) if jouables else "Aucune", inline=True)
    return embed

def uno_choose_color(main: list[str]) -> str:
    counts = {color: 0 for color in UNO_COULEURS}
    for carte in main:
        couleur = uno_couleur(carte)
        if couleur in counts:
            counts[couleur] += 1
    max_count = max(counts.values()) if counts else 0
    meilleures = [color for color, count in counts.items() if count == max_count]
    return random.choice(meilleures) if meilleures else random.choice(UNO_COULEURS)

def uno_draw_cards(partie: dict, user_id: int, count: int) -> int:
    piochees = 0
    while partie["deck"] and piochees < count:
        partie["mains"][user_id].append(partie["deck"].pop())
        piochees += 1
    return piochees

def uno_advance_turn(partie: dict, steps: int = 1) -> None:
    nb = len(partie["joueurs"])
    partie["tour"] = (partie["tour"] + (partie["sens"] * steps)) % nb

async def uno_refresh_message(ch_id: int, note: str = None, final_embed: discord.Embed = None) -> None:
    partie = uno_parties.get(ch_id)
    if not partie:
        return
    channel = bot.get_channel(ch_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(ch_id)
        except discord.HTTPException:
            return
    message_id = partie.get("message_id")
    if not message_id:
        return
    try:
        message = await channel.fetch_message(message_id)
    except discord.HTTPException:
        return
    if final_embed:
        await message.edit(embed=final_embed, view=None)
        return
    view = UnoView(ch_id)
    view.message = message
    await message.edit(embed=uno_build_embed(partie, note=note), view=view)

def uno_play_card(partie: dict, user_id: int, card_index: int) -> tuple[str, bool, str]:
    main = partie["mains"][user_id]
    card = main.pop(card_index)
    valeur = uno_valeur(card)
    if uno_couleur(card) == "🌈":
        couleur = uno_choose_color(main)
        partie["dessus"] = f"{couleur} {valeur}"
        note = f"<@{user_id}> joue **{card}**.\n🎨 La couleur choisie devient {couleur}."
    else:
        partie["dessus"] = card
        note = f"<@{user_id}> joue **{card}**."
    if not main:
        return note + "\n🏆 Plus aucune carte en main.", True, card
    if len(main) == 1:
        note += "\n⚠️ UNO ! Plus qu'une carte."

    if valeur == "Reverse":
        if len(partie["joueurs"]) == 2:
            uno_advance_turn(partie, 2)
            note += "\n🔄 Reverse en duel: le tour adverse est sauté."
        else:
            partie["sens"] *= -1
            uno_advance_turn(partie, 1)
            note += "\n🔄 Le sens du tour change."
    elif valeur == "Skip":
        uno_advance_turn(partie, 2)
        note += "\n⏭️ Le prochain joueur passe son tour."
    elif valeur == "+2":
        cible_idx = (partie["tour"] + partie["sens"]) % len(partie["joueurs"])
        cible_id = partie["joueurs"][cible_idx]
        nb = uno_draw_cards(partie, cible_id, 2)
        uno_advance_turn(partie, 2)
        note += f"\n📥 <@{cible_id}> pioche {nb} carte(s) et passe son tour."
    elif valeur == "+4":
        cible_idx = (partie["tour"] + partie["sens"]) % len(partie["joueurs"])
        cible_id = partie["joueurs"][cible_idx]
        nb = uno_draw_cards(partie, cible_id, 4)
        uno_advance_turn(partie, 2)
        note += f"\n📥 <@{cible_id}> pioche {nb} carte(s) et passe son tour."
    else:
        uno_advance_turn(partie, 1)
    return note, False, card

class UnoPlaySelect(discord.ui.Select):
    def __init__(self, ch_id: int, user_id: int):
        partie = uno_parties[ch_id]
        options = []
        for index, carte in enumerate(partie["mains"][user_id]):
            if uno_compatible(carte, partie["dessus"]):
                options.append(
                    discord.SelectOption(
                        label=f"{index + 1}. {carte}"[:100],
                        value=str(index),
                        description="Carte jouable"
                    )
                )
        super().__init__(
            placeholder="Choisis une carte jouable",
            min_values=1,
            max_values=1,
            options=options[:25]
        )
        self.ch_id = ch_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        partie = uno_parties.get(self.ch_id)
        if not partie:
            await interaction.response.edit_message(content="❌ La partie est terminée.", embed=None, view=None)
            return
        if interaction.user.id != self.user_id or interaction.user.id != partie["joueurs"][partie["tour"]]:
            await interaction.response.send_message("❌ Ce n'est plus ton tour.", ephemeral=True)
            return
        main = partie["mains"][self.user_id]
        card_index = int(self.values[0])
        if card_index >= len(main):
            await interaction.response.send_message("❌ Cette carte n'est plus disponible.", ephemeral=True)
            return
        carte = main[card_index]
        if not uno_compatible(carte, partie["dessus"]):
            await interaction.response.send_message("❌ Cette carte n'est plus jouable.", ephemeral=True)
            return
        note, fini, played_card = uno_play_card(partie, self.user_id, card_index)
        await interaction.response.edit_message(content=f"✅ Tu as joué **{played_card}**.", embed=None, view=None)
        if fini:
            final_embed = discord.Embed(
                title="🎴 UNO — Victoire !",
                description=f"🏆 {interaction.user.mention} remporte la partie.\n\n{note}",
                color=0x57F287
            )
            await uno_refresh_message(self.ch_id, final_embed=final_embed)
            uno_parties.pop(self.ch_id, None)
            return
        await uno_refresh_message(self.ch_id, note=note)

class UnoPlayView(discord.ui.View):
    def __init__(self, ch_id: int, user_id: int):
        super().__init__(timeout=60)
        self.add_item(UnoPlaySelect(ch_id, user_id))

class UnoView(discord.ui.View):
    def __init__(self, ch_id: int):
        super().__init__(timeout=180)
        self.ch_id = ch_id
        self.message = None

    @discord.ui.button(label="👀 Voir ma main", style=discord.ButtonStyle.secondary)
    async def voir_main(self, interaction: discord.Interaction, button: discord.ui.Button):
        partie = uno_parties.get(self.ch_id)
        if not partie or interaction.user.id not in partie["joueurs"]:
            await interaction.response.send_message("❌ Tu ne participes pas à cette partie.", ephemeral=True)
            return
        await interaction.response.send_message(embed=uno_main_embed(partie, interaction.user.id), ephemeral=True)

    @discord.ui.button(label="🃏 Jouer une carte", style=discord.ButtonStyle.primary)
    async def jouer(self, interaction: discord.Interaction, button: discord.ui.Button):
        partie = uno_parties.get(self.ch_id)
        if not partie or interaction.user.id != partie["joueurs"][partie["tour"]]:
            await interaction.response.send_message("❌ Ce n'est pas ton tour.", ephemeral=True)
            return
        main = partie["mains"][interaction.user.id]
        if not any(uno_compatible(carte, partie["dessus"]) for carte in main):
            await interaction.response.send_message("❌ Aucune carte jouable. Pioche avec le bouton prévu.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=uno_main_embed(partie, interaction.user.id),
            view=UnoPlayView(self.ch_id, interaction.user.id),
            ephemeral=True
        )

    @discord.ui.button(label="📥 Piocher", style=discord.ButtonStyle.secondary)
    async def piocher(self, interaction: discord.Interaction, button: discord.ui.Button):
        partie = uno_parties.get(self.ch_id)
        if not partie or interaction.user.id != partie["joueurs"][partie["tour"]]:
            await interaction.response.send_message("❌ Ce n'est pas ton tour.", ephemeral=True)
            return
        if not partie["deck"]:
            await interaction.response.send_message("❌ La pioche est vide.", ephemeral=True)
            return
        carte = partie["deck"].pop()
        partie["mains"][interaction.user.id].append(carte)
        uno_advance_turn(partie, 1)
        new_view = UnoView(self.ch_id)
        new_view.message = interaction.message
        note = f"{interaction.user.mention} pioche 1 carte et passe son tour."
        await interaction.response.edit_message(embed=uno_build_embed(partie, note=note), view=new_view)
        await interaction.followup.send(f"📥 Tu as pioché **{carte}**.", ephemeral=True)

    async def on_timeout(self):
        partie = uno_parties.pop(self.ch_id, None)
        if not partie or not self.message:
            return
        try:
            await self.message.edit(
                embed=uno_build_embed(
                    partie,
                    note="⌛ La partie a expiré faute d'activité.",
                    title="🎴 UNO — Expiré",
                    color=0x95A5A6
                ),
                view=None
            )
        except discord.HTTPException:
            pass

@game_group.command(name="uno", description="🎴 Lance une partie de UNO (2-4 joueurs)")
@app_commands.describe(j2="Joueur 2", j3="Joueur 3 (optionnel)", j4="Joueur 4 (optionnel)")
async def slash_uno(interaction: discord.Interaction, j2: discord.Member, j3: discord.Member = None, j4: discord.Member = None):
    ch_id = interaction.channel_id
    if ch_id in uno_parties:
        await interaction.response.send_message("❌ Une partie de UNO est déjà en cours dans ce salon.", ephemeral=True)
        return
    joueurs_membres = [interaction.user, j2]
    for joueur in (j3, j4):
        if joueur and joueur.id not in [m.id for m in joueurs_membres]:
            joueurs_membres.append(joueur)
    if any(joueur.bot for joueur in joueurs_membres):
        await interaction.response.send_message("❌ Les bots ne peuvent pas participer au UNO.", ephemeral=True)
        return
    joueurs = [m.id for m in joueurs_membres]
    deck  = uno_deck()
    mains = {uid: [deck.pop() for _ in range(7)] for uid in joueurs}
    dessus = deck.pop()
    while uno_couleur(dessus) == "🌈":
        deck.insert(0, dessus); dessus = deck.pop()
    uno_parties[ch_id] = {
        "joueurs": joueurs,
        "mains": mains,
        "deck": deck,
        "dessus": dessus,
        "tour": 0,
        "sens": 1,
        "owner_id": interaction.user.id,
        "message_id": None,
    }
    p = uno_parties[ch_id]
    view  = UnoView(ch_id)
    embed = uno_build_embed(
        p,
        note=f"**Joueurs :** {', '.join(m.mention for m in joueurs_membres)}\nLe premier joueur peut commencer."
    )
    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()
    p["message_id"] = message.id
    view.message = message

@game_group.command(name="uno_stop", description="🎴 Arrête la partie de UNO en cours")
async def slash_uno_stop(interaction: discord.Interaction):
    ch_id = interaction.channel_id
    partie = uno_parties.get(ch_id)
    if not partie:
        await interaction.response.send_message("❌ Aucune partie de UNO en cours.", ephemeral=True)
        return
    if interaction.user.id not in partie["joueurs"] and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Seuls les participants peuvent arrêter cette partie.", ephemeral=True)
        return
    uno_parties.pop(ch_id, None)
    await interaction.response.send_message("🛑 Partie de UNO arrêtée.")

tree.add_command(game_group)

# ════════════════════════════════════════════════════════════════
#  📊  [17] COMPTEURS DE MEMBRES
# ════════════════════════════════════════════════════════════════

async def update_counters(guild: discord.Guild):
    """Met à jour les 3 salons compteurs."""
    members = [m for m in guild.members if not m.bot]
    bots    = [m for m in guild.members if m.bot]
    created = guild.created_at.strftime("%d/%m/%Y")

    pairs = [
        (COUNTER_MEMBERS_ID, f"🐴 • members: {len(members)}"),
        (COUNTER_BOTS_ID,    f"🌵 | • bots: {len(bots)}"),
        (COUNTER_CREATED_ID, f"🍃 • created: {created}"),
    ]
    for ch_id, name in pairs:
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch and ch.name != name:
                try:
                    await ch.edit(name=name)
                except discord.Forbidden:
                    pass


@tasks.loop(minutes=10)
async def counter_loop():
    """Rafraîchit les compteurs toutes les 10 minutes."""
    for guild in bot.guilds:
        await update_counters(guild)


# ── Commandes de configuration des compteurs ─────────────────

@tree.command(name="setcounters", description="[Admin] Configure les salons compteurs de membres")
@app_commands.describe(
    membres="Salon vocal pour le nombre de membres",
    bots="Salon vocal pour le nombre de bots",
    creation="Salon vocal pour la date de création"
)
@app_commands.checks.has_permissions(administrator=True)
async def slash_setcounters(
    interaction: discord.Interaction,
    membres:   discord.VoiceChannel,
    bots:      discord.VoiceChannel,
    creation:  discord.VoiceChannel
):
    global COUNTER_MEMBERS_ID, COUNTER_BOTS_ID, COUNTER_CREATED_ID
    COUNTER_MEMBERS_ID = membres.id
    COUNTER_BOTS_ID    = bots.id
    COUNTER_CREATED_ID = creation.id
    save_data()

    await update_counters(interaction.guild)

    embed = discord.Embed(
        title="✅ Compteurs configurés !",
        description="Les salons seront mis à jour automatiquement toutes les 10 minutes.",
        color=0x57F287
    )
    embed.add_field(name="👥 Membres", value=membres.mention)
    embed.add_field(name="🤖 Bots",    value=bots.mention)
    embed.add_field(name="📅 Création",value=creation.mention)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ════════════════════════════════════════════════════════════════
#  📈  [18] STATISTIQUES SERVEUR — /serverstats
# ════════════════════════════════════════════════════════════════

@tree.command(name="serverstats", description="📊 Affiche les statistiques complètes du serveur")
async def slash_serverstats(interaction: discord.Interaction):
    guild = interaction.guild
    await interaction.response.defer()

    # Membres
    total    = guild.member_count
    humans   = sum(1 for m in guild.members if not m.bot)
    bots     = sum(1 for m in guild.members if m.bot)
    online   = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)

    # Salons
    text_ch  = len(guild.text_channels)
    voice_ch = len(guild.voice_channels)
    cats     = len(guild.categories)
    threads  = len(guild.threads)

    # Rôles & emojis
    roles    = len(guild.roles) - 1  # -1 pour @everyone
    emojis   = len(guild.emojis)

    # Serveur
    created  = guild.created_at.strftime("%d %B %Y")
    owner    = guild.owner.mention if guild.owner else "?"
    boost_lvl = guild.premium_tier
    boosts   = guild.premium_subscription_count

    # Top membres XP
    top_xp = sorted(xp_data.items(), key=lambda x: x[1].get("xp",0) + x[1].get("level",0)*1000, reverse=True)[:3]

    embed = discord.Embed(
        title=f"📊 Statistiques — {guild.name}",
        color=0x8B0000,
        timestamp=datetime.utcnow()
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="👥 Membres",
        value=f"```\nTotal   : {total}\nHumains : {humans}\nBots    : {bots}\nEn ligne: {online}\n```",
        inline=True
    )
    embed.add_field(
        name="💬 Salons",
        value=f"```\nTexte   : {text_ch}\nVocal   : {voice_ch}\nCatég.  : {cats}\nThreads : {threads}\n```",
        inline=True
    )
    embed.add_field(
        name="✨ Divers",
        value=f"```\nRôles   : {roles}\nEmojis  : {emojis}\nBoosts  : {boosts} (niv.{boost_lvl})\n```",
        inline=True
    )
    embed.add_field(
        name="🏰 Serveur",
        value=f"**Créé le :** {created}\n**Proprio :** {owner}\n**ID :** `{guild.id}`",
        inline=False
    )

    if top_xp:
        medals = ["🥇", "🥈", "🥉"]
        top_txt = ""
        for i, (uid, d) in enumerate(top_xp):
            member = guild.get_member(uid)
            name   = member.display_name if member else f"ID:{uid}"
            top_txt += f"{medals[i]} **{name}** — Niv. {d.get('level',0)}\n"
        embed.add_field(name="🏆 Top XP du serveur", value=top_txt, inline=False)

    embed.set_footer(text=f"Demandé par {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    await interaction.followup.send(embed=embed)


# ════════════════════════════════════════════════════════════════
#  🎭  [10] REACTION ROLES
# ════════════════════════════════════════════════════════════════

# Stockage : { message_id: { emoji: role_id } }

@tree.command(name="reactionrole", description="[Admin] Crée un message avec des réactions pour obtenir des rôles")
@app_commands.describe(
    salon="Salon où envoyer le message",
    titre="Titre du message",
    description="Description du message"
)
@app_commands.checks.has_permissions(administrator=True)
async def slash_reactionrole(interaction: discord.Interaction, salon: discord.TextChannel, titre: str, description: str):
    embed = discord.Embed(title=titre, description=description, color=0x8B0000, timestamp=datetime.utcnow())
    embed.set_footer(text="Réagis pour obtenir ton rôle ✨")
    msg = await salon.send(embed=embed)
    reaction_roles[msg.id] = {}
    save_data()
    await interaction.response.send_message(
        f"✅ Message créé dans {salon.mention} ! (ID: `{msg.id}`)\n"
        f"Utilise `/ajouterreaction` pour lier des emojis à des rôles.", ephemeral=True
    )


@tree.command(name="ajouterreaction", description="[Admin] Ajoute un emoji → rôle sur un message de reaction role")
@app_commands.describe(message_id="ID du message", emoji="L'emoji (ex: 🎮)", role="Le rôle à donner")
@app_commands.checks.has_permissions(administrator=True)
async def slash_ajouterreaction(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    try:
        msg_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
        return
    msg = None
    for ch in interaction.guild.text_channels:
        try:
            msg = await ch.fetch_message(msg_id)
            break
        except Exception:
            continue
    if not msg:
        await interaction.response.send_message("❌ Message introuvable.", ephemeral=True)
        return
    if msg_id not in reaction_roles:
        reaction_roles[msg_id] = {}
    reaction_roles[msg_id][emoji] = role.id
    try:
        await msg.add_reaction(emoji)
    except Exception:
        await interaction.response.send_message("⚠️ Rôle lié mais emoji invalide ?", ephemeral=True)
        return
    save_data()
    await interaction.response.send_message(f"✅ {emoji} → {role.mention} ajouté !", ephemeral=True)


@tree.command(name="retirerreaction", description="[Admin] Retire un emoji d'un message de reaction role")
@app_commands.describe(message_id="ID du message", emoji="L'emoji à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def slash_retirerreaction(interaction: discord.Interaction, message_id: str, emoji: str):
    try:
        msg_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
        return
    if msg_id in reaction_roles and emoji in reaction_roles[msg_id]:
        del reaction_roles[msg_id][emoji]
        if not reaction_roles[msg_id]:
            del reaction_roles[msg_id]
        save_data()
        await interaction.response.send_message(f"✅ {emoji} retiré.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Emoji introuvable.", ephemeral=True)


@tree.command(name="voirreactions", description="[Admin] Affiche les reaction roles d'un message")
@app_commands.describe(message_id="ID du message")
@app_commands.checks.has_permissions(administrator=True)
async def slash_voirreactions(interaction: discord.Interaction, message_id: str):
    try:
        msg_id = int(message_id)
    except ValueError:
        await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
        return
    data = reaction_roles.get(msg_id)
    if not data:
        await interaction.response.send_message("❌ Aucun reaction role sur ce message.", ephemeral=True)
        return
    lines = [f"{em} → {interaction.guild.get_role(rid).mention if interaction.guild.get_role(rid) else rid}" for em, rid in data.items()]
    embed = discord.Embed(title=f"🎭 Reaction Roles — {msg_id}", description="\n".join(lines), color=0x8B0000)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    data = reaction_roles.get(payload.message_id)
    if not data:
        return
    role_id = data.get(str(payload.emoji))
    if not role_id:
        return
    guild  = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    role   = guild.get_role(role_id)
    if member and role:
        try:
            await member.add_roles(role, reason="Reaction Role")
        except Exception:
            pass


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    data = reaction_roles.get(payload.message_id)
    if not data:
        return
    role_id = data.get(str(payload.emoji))
    if not role_id:
        return
    guild  = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    role   = guild.get_role(role_id)
    if member and role:
        try:
            await member.remove_roles(role, reason="Reaction Role retiré")
        except Exception:
            pass



# ════════════════════════════════════════════════════════════════
#  🤫  CONFESSION ANONYME
# ════════════════════════════════════════════════════════════════

@tree.command(name="confession", description="Envoie une confession anonyme dans le salon dédié")
@app_commands.describe(texte="Ta confession (personne ne saura que c'est toi)")
async def slash_confession(interaction: discord.Interaction, texte: str):
    global confession_counter, CONFESSION_CHANNEL_ID

    if not CONFESSION_CHANNEL_ID:
        await interaction.response.send_message(
            "❌ Aucun salon de confession configuré. Demande à un admin d'utiliser `/setconfession`.",
            ephemeral=True
        )
        return

    ch = interaction.guild.get_channel(CONFESSION_CHANNEL_ID)
    if not ch:
        await interaction.response.send_message(
            "❌ Salon de confession introuvable. Refais `/setconfession`.",
            ephemeral=True
        )
        return

    if len(texte.strip()) < 5:
        await interaction.response.send_message("❌ Ta confession est trop courte !", ephemeral=True)
        return

    # Répondre IMMÉDIATEMENT à Discord (obligatoire sous 3s)
    await interaction.response.send_message(
        "✅ Ta confession a été envoyée anonymement ! Personne ne saura que c'est toi. 🤫",
        ephemeral=True
    )

    # Envoyer la confession dans le salon dédié
    confession_counter += 1
    embed = discord.Embed(
        title=f"🤫 Confession anonyme #{confession_counter}",
        description=texte.strip(),
        color=0x2C2F33,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text="Confession anonyme • La Taverne")
    await ch.send(embed=embed)
    save_data()


@tree.command(name="setconfession", description="[Admin] Définit le salon où les confessions sont envoyées")
@app_commands.describe(salon="Salon de destination des confessions")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setconfession(interaction: discord.Interaction, salon: discord.TextChannel):
    global CONFESSION_CHANNEL_ID
    CONFESSION_CHANNEL_ID = salon.id
    save_data()
    await interaction.response.send_message(
        f"✅ Les confessions seront envoyées dans {salon.mention}.", ephemeral=True
    )


@tree.command(name="setboost", description="[Admin] Définit le salon où apparaissent les messages de boost")
@app_commands.describe(salon="Salon de destination des boosts")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setboost(interaction: discord.Interaction, salon: discord.TextChannel):
    global BOOST_CHANNEL_ID
    BOOST_CHANNEL_ID = salon.id
    save_data()
    await interaction.response.send_message(
        f"✅ Les messages de boost seront envoyés dans {salon.mention}. 💜", ephemeral=True
    )



# ════════════════════════════════════════════════════════════════
#  ❌  [19] GESTION DES ERREURS
# ════════════════════════════════════════════════════════════════
@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Log toutes les commandes slash utilisées."""
    if interaction.type != discord.InteractionType.application_command:
        return
    cmd_name = interaction.data.get("name", "?") if interaction.data else "?"
    options  = interaction.data.get("options", []) if interaction.data else []
    opts_str = " ".join(f"{o['name']}={o.get('value','?')}" for o in options) if options else ""
    embed = discord.Embed(
        title="⌨️ Commande utilisée",
        color=0x5865F2,
        timestamp=datetime.utcnow()
    )
    embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="🔧 Commande", value=f"`/{cmd_name}`", inline=True)
    embed.add_field(name="📌 Salon",    value=interaction.channel.mention if interaction.channel else "?", inline=True)
    embed.add_field(name="👤 Par",      value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
    if opts_str:
        embed.add_field(name="📋 Options", value=f"`{opts_str[:512]}`", inline=False)
    embed.set_footer(text=f"User ID : {interaction.user.id}")
    await send_log(interaction.guild, embed)



# ════════════════════════════════════════════════════════════════
#  🎭  SELF ROLES — Couleurs & Notifications
# ════════════════════════════════════════════════════════════════

import os as _os_sr

def _sr_banner_path():
    for p in [
        _os_sr.path.join(_os_sr.path.dirname(_os_sr.path.abspath(__file__)), "selfroles_banner.png"),
        _os_sr.path.join(_os_sr.getcwd(), "selfroles_banner.png"),
    ]:
        if _os_sr.path.exists(p):
            return p
    return None


# ── Panel 1 : Couleurs ──────────────────────────────────────────
class CouleurRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _toggle(self, interaction: discord.Interaction, role_name: str, emoji: str):
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(
                f"❌ Rôle **{role_name}** introuvable. Crée-le d'abord sur Discord.",
                ephemeral=True
            )
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"{emoji} Rôle **{role_name}** retiré !", ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"{emoji} Rôle **{role_name}** obtenu !", ephemeral=True
            )

    @discord.ui.button(label="🔴 Rouge",   style=discord.ButtonStyle.danger,   custom_id="role_rouge",  row=0)
    async def role_rouge(self, i, b): await self._toggle(i, "Rouge", "🔴")

    @discord.ui.button(label="🟠 Orange",  style=discord.ButtonStyle.danger,   custom_id="role_orange", row=0)
    async def role_orange(self, i, b): await self._toggle(i, "Orange", "🟠")

    @discord.ui.button(label="🟡 Jaune",   style=discord.ButtonStyle.secondary,custom_id="role_jaune",  row=0)
    async def role_jaune(self, i, b): await self._toggle(i, "Jaune", "🟡")

    @discord.ui.button(label="🟢 Vert",    style=discord.ButtonStyle.success,  custom_id="role_vert",   row=1)
    async def role_vert(self, i, b): await self._toggle(i, "Vert", "🟢")

    @discord.ui.button(label="🔵 Bleu",    style=discord.ButtonStyle.primary,  custom_id="role_bleu",   row=1)
    async def role_bleu(self, i, b): await self._toggle(i, "Bleu", "🔵")

    @discord.ui.button(label="🟣 Violet",  style=discord.ButtonStyle.primary,  custom_id="role_violet", row=1)
    async def role_violet(self, i, b): await self._toggle(i, "Violet", "🟣")

    @discord.ui.button(label="🩷 Rose",    style=discord.ButtonStyle.secondary,custom_id="role_rose",   row=2)
    async def role_rose(self, i, b): await self._toggle(i, "Rose", "🩷")


# ── Panel 2 : Notifications ─────────────────────────────────────
class NotifRolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _toggle(self, interaction: discord.Interaction, role_name: str, emoji: str):
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(
                f"❌ Rôle **{role_name}** introuvable. Crée-le d'abord sur Discord.",
                ephemeral=True
            )
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"{emoji} Rôle **{role_name}** retiré !", ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"{emoji} Rôle **{role_name}** obtenu !", ephemeral=True
            )

    @discord.ui.button(label="🔔 Ping Animation", style=discord.ButtonStyle.primary,  custom_id="role_ping_anim", row=0)
    async def role_ping_anim(self, i, b): await self._toggle(i, "Ping Animation", "🔔")

    @discord.ui.button(label="🎬 Animation",       style=discord.ButtonStyle.success,  custom_id="role_animation", row=0)
    async def role_animation(self, i, b): await self._toggle(i, "Animation", "🎬")


# ── Commandes ───────────────────────────────────────────────────
@tree.command(name="rolecouleurpanel", description="[Admin] Envoie le panel de rôles couleurs")
@app_commands.checks.has_permissions(administrator=True)
async def slash_rolecouleurpanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    banner = _sr_banner_path()
    embed = discord.Embed(
        title="🎨 Choisis ta couleur",
        description=(
            "Clique sur un bouton pour obtenir ou retirer un rôle de couleur.\n\n"
            "🔴 **Rouge** • 🟠 **Orange** • 🟡 **Jaune**\n"
            "🟢 **Vert** • 🔵 **Bleu** • 🟣 **Violet** • 🩷 **Rose**\n\n"
            "*Clique à nouveau pour retirer le rôle.*"
        ),
        color=0x8B0000
    )
    embed.set_footer(text="Un seul rôle couleur à la fois recommandé • La Taverne")
    if banner:
        file = discord.File(banner, filename="selfroles_banner.png")
        embed.set_image(url="attachment://selfroles_banner.png")
        await interaction.channel.send(embed=embed, file=file, view=CouleurRolesView())
    else:
        await interaction.channel.send(embed=embed, view=CouleurRolesView())
    await interaction.followup.send("✅ Panel couleurs envoyé !", ephemeral=True)


@tree.command(name="rolenotifpanel", description="[Admin] Envoie le panel de rôles notifications")
@app_commands.checks.has_permissions(administrator=True)
async def slash_rolenotifpanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    banner = _sr_banner_path()
    embed = discord.Embed(
        title="🔔 Choisis tes notifications",
        description=(
            "Clique sur un bouton pour activer ou désactiver tes notifications.\n\n"
            "🔔 **Ping Animation** — Reçois un ping lors des nouvelles animations\n"
            "🎬 **Animation** — Accède aux salons d'animation\n\n"
            "*Clique à nouveau pour retirer le rôle.*"
        ),
        color=0x2C2F33
    )
    embed.set_footer(text="Gère tes notifications • La Taverne")
    if banner:
        file = discord.File(banner, filename="selfroles_banner.png")
        embed.set_image(url="attachment://selfroles_banner.png")
        await interaction.channel.send(embed=embed, file=file, view=NotifRolesView())
    else:
        await interaction.channel.send(embed=embed, view=NotifRolesView())
    await interaction.followup.send("✅ Panel notifications envoyé !", ephemeral=True)


# ════════════════════════════════════════════════════════════════
#  🏆  PANEL TROPHÉES
# ════════════════════════════════════════════════════════════════

@tree.command(name="tropheepanel", description="[Admin] Envoie le panel du système de trophées")
@app_commands.checks.has_permissions(administrator=True)
async def slash_tropheepanel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    import os as _os_t

    # Image bannière
    banner_path = _os_t.path.join(_os_t.path.dirname(_os_t.path.abspath(__file__)), "trophee_banner.png")
    if not _os_t.path.exists(banner_path):
        banner_path = _os_t.path.join(_os_t.getcwd(), "trophee_banner.png")

    # ── Embed principal avec l'image ──
    embed_main = discord.Embed(
        title="🏆 SYSTÈME DE TROPHÉES",
        description=(
            "Prouve ta valeur à La Taverne en décrochant des trophées "
            "dans toutes les catégories. Chaque exploit laisse une marque éternelle ! ⚔️"
        ),
        color=0xC9A84C,
        timestamp=datetime.utcnow()
    )
    embed_main.set_footer(text="La Taverne • Système de Trophées")

    # ── Embeds par catégorie ──
    embed_engagement = discord.Embed(color=0xC9A84C)
    embed_engagement.add_field(
        name="⏳ Engagement",
        value=(
            "🏆 **Fidèle** — 7 jours sur le serveur\n"
            "🏆 **Habitué** — 30 jours\n"
            "🏆 **Résident** — 90 jours\n"
            "🏆 **Vétéran** — 1 an"
        ),
        inline=True
    )
    embed_engagement.add_field(
        name="🎉 Events",
        value=(
            "🏆 **Participant** — Participer à un event\n"
            "🏆 **Champion** — Gagner un event\n"
            "🏆 **Chanceux** — Gagner un tirage\n"
            "🏆 **Ambianceur** — 10 events"
        ),
        inline=True
    )

    embed_vocal = discord.Embed(color=0xC9A84C)
    embed_vocal.add_field(
        name="🔊 Vocal",
        value=(
            "🏆 **Connecté** — 1 heure en vocal\n"
            "🏆 **Présent** — 10 heures\n"
            "🏆 **Animateur** — 25 heures\n"
            "🏆 **Radio** — 100 heures"
        ),
        inline=True
    )
    embed_vocal.add_field(
        name="😄 Fun",
        value=(
            "🏆 **Speedrun** — 50 messages en 1h\n"
            "🏆 **Salé** — Perdre 5 events\n"
            "🏆 **Bot humain** — Actif 14 jours d\'affilée"
        ),
        inline=True
    )

    embed_contrib = discord.Embed(color=0xC9A84C)
    embed_contrib.add_field(
        name="💡 Contribution",
        value=(
            "🏆 **Idéateur** — Idée acceptée\n"
            "🏆 **Helper** — Aider 20 personnes\n"
            "🏆 **Mentor** — Aider un nouveau"
        ),
        inline=True
    )
    embed_contrib.add_field(
        name="📈 Progression",
        value=(
            "🏆 **Collectionneur** — 10 trophées\n"
            "🏆 **Légende** — 25 trophées"
        ),
        inline=True
    )

    # Envoyer les embeds
    if _os_t.path.exists(banner_path):
        file = discord.File(banner_path, filename="trophee_banner.png")
        embed_main.set_image(url="attachment://trophee_banner.png")
        await interaction.channel.send(embed=embed_main, file=file)
    else:
        await interaction.channel.send(embed=embed_main)

    await interaction.channel.send(embed=embed_engagement)
    await interaction.channel.send(embed=embed_vocal)
    await interaction.channel.send(embed=embed_contrib)

    await interaction.followup.send("✅ Panel trophées envoyé !", ephemeral=True)

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    message = "❌ Permission insuffisante." if isinstance(error, app_commands.MissingPermissions) else f"❌ Erreur : {error}"
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    if not isinstance(error, app_commands.MissingPermissions):
        raise error




# ════════════════════════════════════════════════════════════════
#  🔮  AKINATOR (Devinettes sans API externe)
# ════════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════════
#  🚀  [20] LANCEMENT
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
#  📚  COMICS MARVEL & DC (ComicVine API)
# ════════════════════════════════════════════════════════════════

COMICVINE_API_KEY = os.getenv("COMICVINE_API_KEY", "")
COMICVINE_BASE    = "https://comicvine.gamespot.com/api"
COMICVINE_HEADERS = {"User-Agent": "SiennaBot/1.0 Discord Bot"}
CV_PUBLISHERS = {
    31: {"name": "Marvel", "emoji": "🔴", "color": 0xEC1D24, "slug": "marvel"},
    10: {"name": "DC Comics", "emoji": "🔵", "color": 0x0075C8, "slug": "dc"},
}
cv_issue_detail_cache: dict[int, dict] = {}
cv_volume_publisher_cache: dict[int, dict] = {}
cv_character_pool_cache: dict[int, dict] = {}

def _publisher_meta(publisher_id: int) -> dict:
    return CV_PUBLISHERS.get(publisher_id, {"name": "Comics", "emoji": "📚", "color": 0x8B0000, "slug": "all"})

def _cv_resource_url(resource: str, resource_id: int) -> str:
    prefixes = {"issue": "4000", "volume": "4050"}
    prefix = prefixes.get(resource, "")
    return f"{COMICVINE_BASE}/{resource}/{prefix}-{resource_id}/" if prefix else f"{COMICVINE_BASE}/{resource}/{resource_id}/"

def _cv_extract_image(image_obj: dict | None) -> str:
    image_obj = image_obj or {}
    return (
        image_obj.get("original_url")
        or image_obj.get("super_url")
        or image_obj.get("medium_url")
        or image_obj.get("screen_large_url")
        or image_obj.get("small_url")
        or ""
    )

def _cv_clean_text(raw: str, max_len: int = 320) -> str:
    import html as _html
    import re as _re

    text = _html.unescape(raw or "")
    text = _re.sub(r"<br\s*/?>", "\n", text, flags=_re.I)
    text = _re.sub(r"</p\s*>", "\n", text, flags=_re.I)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = _re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text

def _cv_month_bounds(target: datetime | None = None) -> tuple[str, str, str]:
    import calendar as _cal

    target = target or datetime.utcnow()
    last_day = _cal.monthrange(target.year, target.month)[1]
    start = f"{target.year}-{target.month:02d}-01"
    end = f"{target.year}-{target.month:02d}-{last_day:02d}"
    label = target.strftime("%B %Y")
    return start, end, label

def _cv_normalize_issue(raw: dict) -> dict:
    vol = raw.get("volume") or {}
    return {
        "id": raw.get("id", 0),
        "title": f"{vol.get('name', '?')} #{raw.get('issue_number', '?')}",
        "name": raw.get("name") or "",
        "date": (raw.get("cover_date") or "")[:10],
        "store": (raw.get("store_date") or "")[:10],
        "image": _cv_extract_image(raw.get("image")),
        "url": raw.get("site_detail_url", ""),
        "api_detail_url": raw.get("api_detail_url", ""),
        "desc": _cv_clean_text(raw.get("description") or raw.get("deck") or "", 320),
        "pub": "",
        "writers": "",
        "artists": "",
        "chars": "",
        "volume": vol,
    }

async def _cv_request(endpoint: str, params: dict) -> dict:
    params = dict(params)
    params["api_key"] = COMICVINE_API_KEY
    params["format"] = "json"
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{COMICVINE_BASE}/{endpoint}",
            params=params,
            headers=COMICVINE_HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status != 200:
                return {}
            return await r.json()

async def _cv_request_url(url: str, params: dict) -> dict:
    params = dict(params)
    params["api_key"] = COMICVINE_API_KEY
    params["format"] = "json"
    async with aiohttp.ClientSession() as s:
        async with s.get(
            url,
            params=params,
            headers=COMICVINE_HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            if r.status != 200:
                return {}
            return await r.json()

async def _cv_get_volume_publisher(volume: dict) -> dict:
    volume = volume or {}
    volume_id = int(volume.get("id") or 0)
    if not volume_id:
        return {}
    if volume_id in cv_volume_publisher_cache:
        return cv_volume_publisher_cache[volume_id]

    publisher = volume.get("publisher") or {}
    if isinstance(publisher, dict) and publisher.get("id"):
        cv_volume_publisher_cache[volume_id] = publisher
        return publisher

    detail_url = volume.get("api_detail_url") or _cv_resource_url("volume", volume_id)
    data = await _cv_request_url(detail_url, {"field_list": "publisher"})
    result = data.get("results") or {}
    publisher = result.get("publisher") or {}
    publisher = publisher if isinstance(publisher, dict) else {}
    cv_volume_publisher_cache[volume_id] = publisher
    return publisher

async def _cv_issue_matches_publisher(issue: dict, publisher_id: int) -> bool:
    pub = await _cv_get_volume_publisher(issue.get("volume") or {})
    return int(pub.get("id") or 0) == publisher_id

async def _cv_enrich_issue(issue: dict) -> dict:
    issue_id = int(issue.get("id") or 0)
    if issue_id in cv_issue_detail_cache:
        enriched = dict(issue)
        enriched.update(cv_issue_detail_cache[issue_id])
        return enriched

    detail_url = issue.get("api_detail_url") or _cv_resource_url("issue", issue_id)
    data = await _cv_request_url(
        detail_url,
        {
            "field_list": ",".join(
                [
                    "id",
                    "name",
                    "issue_number",
                    "cover_date",
                    "store_date",
                    "image",
                    "site_detail_url",
                    "volume",
                    "description",
                    "deck",
                    "person_credits",
                    "character_credits",
                ]
            )
        },
    )
    raw = data.get("results") or {}
    if not raw:
        return issue

    vol = raw.get("volume") or issue.get("volume") or {}
    pub = await _cv_get_volume_publisher(vol)
    persons = raw.get("person_credits") or []
    characters = raw.get("character_credits") or []

    detail = {
        "title": f"{vol.get('name', '?')} #{raw.get('issue_number', '?')}",
        "name": raw.get("name") or issue.get("name") or "",
        "date": (raw.get("cover_date") or issue.get("date") or "")[:10],
        "store": (raw.get("store_date") or issue.get("store") or "")[:10],
        "image": _cv_extract_image(raw.get("image")) or issue.get("image", ""),
        "url": raw.get("site_detail_url") or issue.get("url", ""),
        "api_detail_url": detail_url,
        "desc": _cv_clean_text(raw.get("description") or raw.get("deck") or issue.get("desc") or "", 420),
        "pub": pub.get("name", ""),
        "writers": ", ".join(
            p.get("name", "")
            for p in persons
            if "writer" in (p.get("role", "") or "").lower()
        )[:150],
        "artists": ", ".join(
            p.get("name", "")
            for p in persons
            if any(
                role in (p.get("role", "") or "").lower()
                for role in ["artist", "penciler", "penciller", "inker", "cover"]
            )
        )[:150],
        "chars": ", ".join(c.get("name", "") for c in characters[:6]),
        "volume": vol,
    }
    cv_issue_detail_cache[issue_id] = detail
    enriched = dict(issue)
    enriched.update(detail)
    return enriched

async def _fetch_cv_this_month(publisher_id: int, limit: int = 10) -> list[dict]:
    start, end, _ = _cv_month_bounds()
    seen_ids: set[int] = set()
    candidates: list[dict] = []

    for date_field in ("store_date", "cover_date"):
        offset = 0
        while len(candidates) < limit * 3 and offset <= 200:
            params = {
                "sort": f"{date_field}:desc",
                "limit": 100,
                "offset": offset,
                "filter": f"{date_field}:{start} 00:00:00|{end} 23:59:59",
                "field_list": "id,name,issue_number,cover_date,store_date,image,site_detail_url,api_detail_url,volume",
            }
            data = await _cv_request("issues", params)
            batch = data.get("results") or []
            if not batch:
                break
            for raw in batch:
                issue = _cv_normalize_issue(raw)
                issue_id = int(issue.get("id") or 0)
                if not issue_id or issue_id in seen_ids:
                    continue
                if not await _cv_issue_matches_publisher(issue, publisher_id):
                    continue
                seen_ids.add(issue_id)
                candidates.append(issue)
                if len(candidates) >= limit * 3:
                    break
            if len(batch) < 100:
                break
            offset += 100
            await asyncio.sleep(0.25)

    candidates.sort(key=lambda item: (item.get("store") or item.get("date") or ""), reverse=True)
    results = []
    for issue in candidates[:limit]:
        results.append(await _cv_enrich_issue(issue))
        await asyncio.sleep(0.15)
    return results

async def _fetch_cv_search(query: str, publisher_id: int = 0, limit: int = 15) -> list[dict]:
    params = {
        "query": query,
        "resources": "issue",
        "limit": min(limit * 4, 40),
        "field_list": "id,name,issue_number,cover_date,store_date,image,site_detail_url,api_detail_url,volume,description,deck",
    }
    data = await _cv_request("search", params)
    results = []
    for raw in data.get("results", []):
        issue = _cv_normalize_issue(raw)
        if publisher_id and not await _cv_issue_matches_publisher(issue, publisher_id):
            continue
        results.append(await _cv_enrich_issue(issue))
        if len(results) >= limit:
            break
        await asyncio.sleep(0.1)
    results.sort(key=lambda item: (item.get("store") or item.get("date") or ""), reverse=True)
    return results[:limit]

def _cv_embed(comic: dict, title: str, color: int, page: int, total: int) -> discord.Embed:
    headline = comic["title"]
    if comic.get("name"):
        headline += f" — {comic['name']}"

    embed = discord.Embed(
        title=headline[:256],
        url=comic.get("url") or None,
        description=comic.get("desc") or "Aucune description disponible.",
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.set_author(name=f"{title} • {page}/{total}")
    meta_bits = []
    if comic.get("pub"):
        meta_bits.append(comic["pub"])
    if comic.get("date"):
        meta_bits.append(f"Cover {comic['date']}")
    if comic.get("store"):
        meta_bits.append(f"Sortie {comic['store']}")
    if meta_bits:
        embed.add_field(name="📚 Infos", value=" • ".join(meta_bits)[:1024], inline=False)
    if comic.get("writers"):
        embed.add_field(name="✍️ Scénario", value=comic["writers"][:1024], inline=True)
    if comic.get("artists"):
        embed.add_field(name="🎨 Art / Cover", value=comic["artists"][:1024], inline=True)
    if comic.get("chars"):
        embed.add_field(name="🦸 Personnages", value=comic["chars"][:1024], inline=False)
    if comic.get("image"):
        embed.set_image(url=comic["image"])
    embed.set_footer(text="ComicVine API • comicvine.gamespot.com")
    return embed

class CVPageView(discord.ui.View):
    def __init__(self, comics: list[dict], title: str, color: int):
        super().__init__(timeout=180)
        self.comics = comics
        self.title = title
        self.color = color
        self.page = 1
        self.total = max(1, len(comics))
        self._sync_btns()

    def _sync_btns(self):
        self.prev.disabled = self.page <= 1
        self.next.disabled = self.page >= self.total

    def _embed(self):
        comic = self.comics[self.page - 1]
        return _cv_embed(comic, self.title, self.color, self.page, self.total)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, btn):
        self.page -= 1
        self._sync_btns()
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, btn):
        self.page += 1
        self._sync_btns()
        await interaction.response.edit_message(embed=self._embed(), view=self)

def _no_api_embed() -> discord.Embed:
    return discord.Embed(
        title="❌ Clé API ComicVine manquante",
        description=(
            "**Comment obtenir ta clé gratuite :**\n\n"
            "1. Va sur **comicvine.gamespot.com/api**\n"
            "2. Connecte-toi / crée un compte\n"
            "3. Ta clé apparaît sur la page\n\n"
            "**Sur Railway :** ajoute la variable :\n"
            "```\nCOMICVINE_API_KEY=ta_clé_ici\n```"
        ),
        color=0xED4245,
    )

def _utc_day_key() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def _utc_week_key() -> str:
    iso = datetime.utcnow().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def _quest_templates(scope: str) -> list[dict]:
    return DAILY_QUEST_TEMPLATES if scope == "daily" else WEEKLY_QUEST_TEMPLATES

def _quest_period_key(scope: str) -> str:
    return _utc_day_key() if scope == "daily" else _utc_week_key()

def _build_quest_entry(template: dict) -> dict:
    return {
        "id": template["id"],
        "label": template["label"],
        "type": template["type"],
        "target": template["target"],
        "progress": 0,
        "reward": template["reward"],
        "claimed": False,
        "scope": template["scope"],
    }

def _get_economy_profile(user_id: int) -> dict:
    profile = economy_profiles.setdefault(
        user_id,
        {
            "coins": 0,
            "quests": {},
        },
    )
    profile.setdefault("coins", 0)
    profile.setdefault("quests", {})
    _ensure_quest_scope(profile, "daily")
    _ensure_quest_scope(profile, "weekly")
    return profile

def _ensure_quest_scope(profile: dict, scope: str):
    quests = profile.setdefault("quests", {})
    period = _quest_period_key(scope)
    current = quests.get(scope)
    if not current or current.get("period") != period:
        quests[scope] = {
            "period": period,
            "items": [_build_quest_entry(template) for template in _quest_templates(scope)],
        }
        mark_data_dirty()
    else:
        current.setdefault("items", [_build_quest_entry(template) for template in _quest_templates(scope)])

def _track_quest_progress(user_id: int, quest_type: str, amount: int):
    if amount <= 0:
        return
    profile = _get_economy_profile(user_id)
    updated = False
    for scope in ("daily", "weekly"):
        _ensure_quest_scope(profile, scope)
        items = profile["quests"][scope]["items"]
        for quest in items:
            if quest.get("type") != quest_type:
                continue
            before = int(quest.get("progress", 0))
            target = int(quest.get("target", 0))
            quest["progress"] = min(target, before + amount)
            if quest["progress"] != before:
                updated = True
    if updated:
        mark_data_dirty()

def _format_quest_progress(quest: dict) -> str:
    progress = int(quest.get("progress", 0))
    target = int(quest.get("target", 0))
    if quest.get("type") == "voice_seconds":
        progress_txt = f"{progress // 60}m"
        target_txt = f"{target // 60}m"
    else:
        progress_txt = str(progress)
        target_txt = str(target)
    status = "✅" if quest.get("claimed") else ("🎁" if progress >= target else "🕒")
    return f"{status} **{quest.get('label', 'Quête')}**\n{progress_txt}/{target_txt} • {quest.get('reward', 0)} coins"

def _claim_quests(user_id: int, scope: str = "all") -> tuple[int, int]:
    profile = _get_economy_profile(user_id)
    total_reward = 0
    claimed_count = 0
    scopes = ("daily", "weekly") if scope == "all" else (scope,)
    for current_scope in scopes:
        _ensure_quest_scope(profile, current_scope)
        for quest in profile["quests"][current_scope]["items"]:
            if quest.get("claimed"):
                continue
            if int(quest.get("progress", 0)) < int(quest.get("target", 0)):
                continue
            quest["claimed"] = True
            total_reward += int(quest.get("reward", 0))
            claimed_count += 1
    if total_reward:
        profile["coins"] = int(profile.get("coins", 0)) + total_reward
        save_data()
    return claimed_count, total_reward

GACHA_RARITY_META = {
    "Commun": {"emoji": "⚪", "color": 0xBDC3C7},
    "Rare": {"emoji": "🔵", "color": 0x3498DB},
    "Epique": {"emoji": "🟣", "color": 0x9B59B6},
    "Legendaire": {"emoji": "🟡", "color": 0xF1C40F},
    "Mythique": {"emoji": "🔥", "color": 0xE67E22},
}
GACHA_RARITY_ORDER = ["Mythique", "Legendaire", "Epique", "Rare", "Commun"]

async def _send_comic_release_batch(channel: discord.abc.Messageable, comics: list[dict], publisher_id: int, heading: str):
    meta = _publisher_meta(publisher_id)
    intro = discord.Embed(
        title=f"{meta['emoji']} {heading}",
        description=f"**{len(comics)} sorties** récupérées avec cover et détails enrichis.",
        color=meta["color"],
        timestamp=datetime.utcnow(),
    )
    intro.set_footer(text="ComicVine API • sorties du mois")
    await channel.send(embed=intro)
    for index, comic in enumerate(comics, start=1):
        await channel.send(embed=_cv_embed(comic, heading, meta["color"], index, len(comics)))
        await asyncio.sleep(0.5)

def _gacha_get_profile(user_id: int) -> dict:
    profile = gacha_profiles.setdefault(
        user_id,
        {
            "pulls": 0,
            "pull_windows": {},
            "pity": {},
            "items": {},
        },
    )
    profile.setdefault("pulls", 0)
    profile.setdefault("pull_windows", {})
    profile.setdefault("pity", {})
    profile.setdefault("items", {})
    return profile

def _gacha_rarity_for_index(index: int, total: int) -> str:
    ratio = index / max(total - 1, 1)
    if ratio <= 0.02:
        return "Mythique"
    if ratio <= 0.10:
        return "Legendaire"
    if ratio <= 0.28:
        return "Epique"
    if ratio <= 0.55:
        return "Rare"
    return "Commun"

async def _cv_fetch_character_pool(publisher_id: int, max_items: int = 180) -> list[dict]:
    cached = cv_character_pool_cache.get(publisher_id)
    now_ts = datetime.utcnow().timestamp()
    if cached and now_ts - cached.get("ts", 0) < 6 * 3600:
        return cached.get("items", [])

    items: list[dict] = []
    seen_ids: set[int] = set()
    for offset in range(0, max_items, 100):
        params = {
            "sort": "count_of_issue_appearances:desc",
            "limit": 100,
            "offset": offset,
            "filter": f"publisher:{publisher_id}",
            "field_list": "id,name,real_name,image,deck,site_detail_url,count_of_issue_appearances,publisher",
        }
        data = await _cv_request("characters", params)
        batch = data.get("results") or []
        if not batch:
            break
        for raw in batch:
            cid = int(raw.get("id") or 0)
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            items.append(
                {
                    "id": cid,
                    "name": raw.get("name") or "Inconnu",
                    "real_name": raw.get("real_name") or "",
                    "image": _cv_extract_image(raw.get("image")),
                    "url": raw.get("site_detail_url") or "",
                    "desc": _cv_clean_text(raw.get("deck") or "", 220),
                    "appearances": int(raw.get("count_of_issue_appearances") or 0),
                    "publisher_id": publisher_id,
                    "publisher": _publisher_meta(publisher_id)["name"],
                }
            )
        if len(batch) < 100:
            break
        await asyncio.sleep(0.25)

    for index, item in enumerate(items):
        item["rarity"] = _gacha_rarity_for_index(index, len(items))

    cv_character_pool_cache[publisher_id] = {"ts": now_ts, "items": items}
    return items

def _gacha_roll_rarity(available_rarities: list[str], pity: int) -> str:
    weights = {
        "Commun": 50,
        "Rare": 27,
        "Epique": 14,
        "Legendaire": 7,
        "Mythique": 2,
    }
    if pity >= GACHA_PITY_THRESHOLD:
        weights["Commun"] = 0
        weights["Rare"] = 0
        weights["Epique"] = 55
        weights["Legendaire"] = 35
        weights["Mythique"] = 10

    population = [rarity for rarity in GACHA_RARITY_ORDER if rarity in available_rarities]
    selected = random.choices(population, weights=[weights[rarity] for rarity in population], k=1)[0]
    return selected

def _gacha_get_window(profile: dict, universe_slug: str) -> dict:
    windows = profile.setdefault("pull_windows", {})
    window = windows.setdefault(universe_slug, {"start": 0.0, "count": 0})
    start_ts = float(window.get("start", 0) or 0)
    now_ts = datetime.utcnow().timestamp()
    if not start_ts or now_ts - start_ts >= GACHA_WINDOW_SECONDS:
        window["start"] = now_ts
        window["count"] = 0
    return window

def _gacha_window_status(profile: dict, universe_slug: str) -> tuple[int, int]:
    window = _gacha_get_window(profile, universe_slug)
    count = int(window.get("count", 0) or 0)
    remaining = max(0, GACHA_PULLS_PER_HOUR - count)
    seconds_left = max(0, int(GACHA_WINDOW_SECONDS - (datetime.utcnow().timestamp() - float(window.get("start", 0) or 0))))
    return remaining, seconds_left

def _gacha_register_pull(profile: dict, universe_slug: str) -> tuple[int, int]:
    window = _gacha_get_window(profile, universe_slug)
    window["count"] = int(window.get("count", 0) or 0) + 1
    remaining = max(0, GACHA_PULLS_PER_HOUR - int(window["count"]))
    seconds_left = max(0, int(GACHA_WINDOW_SECONDS - (datetime.utcnow().timestamp() - float(window.get("start", 0) or 0))))
    return remaining, seconds_left

def _gacha_reset_user_counters(user_id: int, universes: list[str] | None = None):
    profile = _gacha_get_profile(user_id)
    windows = profile.setdefault("pull_windows", {})
    now_ts = datetime.utcnow().timestamp()
    targets = universes or ["marvel", "dc"]
    for universe_slug in targets:
        windows[universe_slug] = {"start": now_ts, "count": 0}
    save_data()

def _gacha_item_sort_key(item: dict):
    rarity_index = GACHA_RARITY_ORDER.index(item.get("rarity", "Commun")) if item.get("rarity", "Commun") in GACHA_RARITY_ORDER else len(GACHA_RARITY_ORDER)
    return (rarity_index, -int(item.get("count", 1)), item.get("name", ""))

@tree.command(name="quests", description="🎯 Affiche tes quêtes quotidiennes et hebdomadaires")
async def slash_quests(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    profile = _get_economy_profile(target.id)

    embed = discord.Embed(
        title="🎯 Quêtes du serveur",
        description=f"Progression de {target.mention}",
        color=0xF39C12,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="🪙 Solde", value=f"{int(profile.get('coins', 0))} coins", inline=True)

    daily_lines = [_format_quest_progress(quest) for quest in profile["quests"]["daily"]["items"]]
    weekly_lines = [_format_quest_progress(quest) for quest in profile["quests"]["weekly"]["items"]]
    embed.add_field(name="☀️ Quotidiennes", value="\n\n".join(daily_lines)[:1024], inline=False)
    embed.add_field(name="📅 Hebdomadaires", value="\n\n".join(weekly_lines)[:1024], inline=False)
    embed.set_footer(text="Utilise /claimquests pour récupérer tes récompenses")
    await interaction.response.send_message(embed=embed, ephemeral=(target == interaction.user))

@tree.command(name="claimquests", description="🎁 Récupère les récompenses de tes quêtes terminées")
@app_commands.choices(portee=[
    app_commands.Choice(name="Toutes", value="all"),
    app_commands.Choice(name="Quotidiennes", value="daily"),
    app_commands.Choice(name="Hebdomadaires", value="weekly"),
])
async def slash_claim_quests(interaction: discord.Interaction, portee: str = "all"):
    claimed_count, total_reward = _claim_quests(interaction.user.id, portee)
    if not claimed_count:
        await interaction.response.send_message("📭 Aucune quête terminée à récupérer pour le moment.", ephemeral=True)
        return

    profile = _get_economy_profile(interaction.user.id)
    embed = discord.Embed(
        title="🎁 Récompenses récupérées",
        description=f"Tu as validé **{claimed_count} quête(s)**.",
        color=0x57F287,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="🪙 Gains", value=f"{total_reward} coins", inline=True)
    embed.add_field(name="💼 Nouveau solde", value=f"{int(profile.get('coins', 0))} coins", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="balance", description="🪙 Affiche le solde de coins d'un membre")
async def slash_balance(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    profile = _get_economy_profile(target.id)
    embed = discord.Embed(
        title="🪙 Solde",
        description=f"{target.mention} possède **{int(profile.get('coins', 0))} coins**.",
        color=0xF1C40F,
        timestamp=datetime.utcnow(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=(target == interaction.user))

@tree.command(name="shop", description="🛒 Affiche la boutique liée au gacha")
async def slash_shop(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 Boutique du gacha",
        description="Achète des boosts avec tes coins.",
        color=0x8E44AD,
        timestamp=datetime.utcnow(),
    )
    for item_id, item in SHOP_ITEMS.items():
        embed.add_field(
            name=f"{item['label']} — {item['price']} coins",
            value=f"`{item_id}`\n{item['description']}",
            inline=False,
        )
    embed.set_footer(text="Utilise /buy pour acheter un objet")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="buy", description="🛍️ Achète un objet dans la boutique")
@app_commands.choices(item=[
    app_commands.Choice(name="Reset Marvel", value="marvel_reset"),
    app_commands.Choice(name="Reset DC", value="dc_reset"),
    app_commands.Choice(name="Reset total", value="all_reset"),
    app_commands.Choice(name="Boost pity Marvel", value="marvel_pity"),
    app_commands.Choice(name="Boost pity DC", value="dc_pity"),
])
async def slash_buy(interaction: discord.Interaction, item: str):
    if item not in SHOP_ITEMS:
        await interaction.response.send_message("❌ Objet introuvable dans la boutique.", ephemeral=True)
        return

    econ_profile = _get_economy_profile(interaction.user.id)
    shop_item = SHOP_ITEMS[item]
    price = int(shop_item["price"])
    if int(econ_profile.get("coins", 0)) < price:
        await interaction.response.send_message(
            f"❌ Il te faut **{price} coins** pour acheter `{shop_item['label']}`.",
            ephemeral=True,
        )
        return

    econ_profile["coins"] = int(econ_profile.get("coins", 0)) - price
    gacha_profile = _gacha_get_profile(interaction.user.id)
    pity_map = gacha_profile.setdefault("pity", {})

    if item == "marvel_reset":
        _gacha_reset_user_counters(interaction.user.id, ["marvel"])
    elif item == "dc_reset":
        _gacha_reset_user_counters(interaction.user.id, ["dc"])
    elif item == "all_reset":
        _gacha_reset_user_counters(interaction.user.id, ["marvel", "dc"])
    elif item == "marvel_pity":
        pity_map["marvel"] = min(GACHA_PITY_THRESHOLD, int(pity_map.get("marvel", 0) or 0) + 3)
        save_data()
    elif item == "dc_pity":
        pity_map["dc"] = min(GACHA_PITY_THRESHOLD, int(pity_map.get("dc", 0) or 0) + 3)
        save_data()

    if item.endswith("_reset"):
        save_data()

    embed = discord.Embed(
        title="🛍️ Achat validé",
        description=f"Tu as acheté **{shop_item['label']}**.",
        color=0x57F287,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="💸 Dépensé", value=f"{price} coins", inline=True)
    embed.add_field(name="🪙 Solde restant", value=f"{int(econ_profile.get('coins', 0))} coins", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="gachapull", description="🎴 Invoque un personnage Marvel ou DC")
@app_commands.choices(univers=[
    app_commands.Choice(name="Marvel", value="marvel"),
    app_commands.Choice(name="DC Comics", value="dc"),
])
async def slash_gacha_pull(interaction: discord.Interaction, univers: str):
    await interaction.response.defer()
    if not COMICVINE_API_KEY:
        await interaction.followup.send(embed=_no_api_embed())
        return

    publisher_id = 31 if univers == "marvel" else 10
    meta = _publisher_meta(publisher_id)
    profile = _gacha_get_profile(interaction.user.id)
    pulls_left, seconds_left = _gacha_window_status(profile, univers)
    if pulls_left <= 0:
        minutes, seconds = divmod(seconds_left, 60)
        await interaction.followup.send(
            f"⏳ Tu as déjà utilisé tes **{GACHA_PULLS_PER_HOUR} pulls** {meta['name']} pour cette heure.\n"
            f"Prochaine recharge dans **{minutes}m {seconds:02d}s**.",
            ephemeral=True,
        )
        return

    pool = await _cv_fetch_character_pool(publisher_id)
    if not pool:
        await interaction.followup.send(f"❌ Impossible de charger le pool gacha {meta['name']} pour le moment.")
        return

    pity_map = profile.setdefault("pity", {})
    pity_before = int(pity_map.get(univers, 0) or 0)
    buckets: dict[str, list[dict]] = {}
    for item in pool:
        buckets.setdefault(item["rarity"], []).append(item)
    target_rarity = _gacha_roll_rarity(list(buckets.keys()), pity_before)
    pulled = random.choice(buckets[target_rarity])

    items = profile.setdefault("items", {})
    key = f"{publisher_id}:{pulled['id']}"
    stored = items.get(key)
    duplicate_count = 1
    if stored:
        stored["count"] = int(stored.get("count", 1)) + 1
        duplicate_count = stored["count"]
    else:
        stored = {
            "id": pulled["id"],
            "name": pulled["name"],
            "real_name": pulled.get("real_name", ""),
            "image": pulled.get("image", ""),
            "url": pulled.get("url", ""),
            "desc": pulled.get("desc", ""),
            "appearances": pulled.get("appearances", 0),
            "publisher_id": publisher_id,
            "publisher": pulled.get("publisher", meta["name"]),
            "rarity": pulled["rarity"],
            "count": 1,
        }
        items[key] = stored

    profile["pulls"] = int(profile.get("pulls", 0)) + 1
    pity_map[univers] = 0 if pulled["rarity"] in ("Legendaire", "Mythique") else pity_before + 1
    pulls_left_after, seconds_left_after = _gacha_register_pull(profile, univers)
    _track_quest_progress(interaction.user.id, "gacha_pulls", 1)
    save_data()

    rarity_meta = GACHA_RARITY_META[pulled["rarity"]]
    embed = discord.Embed(
        title=f"{rarity_meta['emoji']} Pull {meta['name']} — {pulled['rarity']}",
        description=pulled.get("desc") or "Aucune description disponible pour ce personnage.",
        color=rarity_meta["color"],
        timestamp=datetime.utcnow(),
        url=pulled.get("url") or None,
    )
    name_line = pulled["name"]
    if pulled.get("real_name"):
        name_line += f" ({pulled['real_name']})"
    embed.add_field(name="🧬 Personnage", value=name_line[:1024], inline=False)
    embed.add_field(name="📚 Univers", value=meta["name"], inline=True)
    embed.add_field(name="📖 Apparitions", value=str(pulled.get("appearances", 0)), inline=True)
    embed.add_field(name="🗂️ Exemplaires", value=str(duplicate_count), inline=True)
    embed.add_field(name="🎯 Pity", value=f"{pity_map[univers]}/{GACHA_PITY_THRESHOLD}", inline=True)
    embed.add_field(name="🎟️ Pulls restants", value=f"{pulls_left_after}/{GACHA_PULLS_PER_HOUR}", inline=True)
    if pulled.get("image"):
        embed.set_image(url=pulled["image"])
    if pulls_left_after == 0:
        minutes, seconds = divmod(seconds_left_after, 60)
        footer = f"Gacha {meta['name']} • quota atteint, reset dans {minutes}m {seconds:02d}s"
    else:
        footer = f"Gacha {meta['name']} • jusqu'à {GACHA_PULLS_PER_HOUR} pulls par heure"
    embed.set_footer(text=footer)
    await interaction.followup.send(embed=embed)

@tree.command(name="gachacollection", description="📚 Affiche la collection gacha Marvel/DC")
@app_commands.choices(univers=[
    app_commands.Choice(name="Tout", value="all"),
    app_commands.Choice(name="Marvel", value="marvel"),
    app_commands.Choice(name="DC Comics", value="dc"),
])
async def slash_gacha_collection(
    interaction: discord.Interaction,
    univers: str = "all",
    membre: discord.Member = None,
):
    target = membre or interaction.user
    profile = gacha_profiles.get(target.id)
    if not profile or not profile.get("items"):
        await interaction.response.send_message(f"📭 {target.mention} n'a encore aucune carte gacha.", ephemeral=True)
        return

    publisher_filter = 0
    if univers == "marvel":
        publisher_filter = 31
    elif univers == "dc":
        publisher_filter = 10

    items = list(profile.get("items", {}).values())
    if publisher_filter:
        items = [item for item in items if int(item.get("publisher_id", 0)) == publisher_filter]
    if not items:
        await interaction.response.send_message("📭 Aucune carte dans cette collection pour cet univers.", ephemeral=True)
        return

    items.sort(key=_gacha_item_sort_key)
    counts_by_rarity = {rarity: 0 for rarity in GACHA_RARITY_ORDER}
    total_copies = 0
    for item in items:
        counts_by_rarity[item.get("rarity", "Commun")] += int(item.get("count", 1))
        total_copies += int(item.get("count", 1))

    title = "🎴 Collection Gacha"
    if publisher_filter:
        title += f" — {_publisher_meta(publisher_filter)['name']}"
    embed = discord.Embed(
        title=title,
        description=f"Collection de {target.mention}",
        color=0x8B0000,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="🧾 Cartes uniques", value=str(len(items)), inline=True)
    embed.add_field(name="📦 Copies totales", value=str(total_copies), inline=True)
    embed.add_field(name="🎰 Pulls", value=str(profile.get("pulls", 0)), inline=True)
    marvel_left, _ = _gacha_window_status(profile, "marvel")
    dc_left, _ = _gacha_window_status(profile, "dc")
    embed.add_field(name="🎟️ Marvel", value=f"{marvel_left}/{GACHA_PULLS_PER_HOUR}", inline=True)
    embed.add_field(name="🎟️ DC", value=f"{dc_left}/{GACHA_PULLS_PER_HOUR}", inline=True)

    rarity_summary = []
    for rarity in GACHA_RARITY_ORDER:
        count = counts_by_rarity.get(rarity, 0)
        if count:
            rarity_summary.append(f"{GACHA_RARITY_META[rarity]['emoji']} {rarity}: {count}")
    embed.add_field(name="✨ Raretés", value="\n".join(rarity_summary)[:1024], inline=False)

    lines = []
    for item in items[:10]:
        rarity = item.get("rarity", "Commun")
        emoji = GACHA_RARITY_META.get(rarity, GACHA_RARITY_META["Commun"])["emoji"]
        lines.append(
            f"{emoji} **{item.get('name', 'Inconnu')}** x{int(item.get('count', 1))}"
            f" • {item.get('publisher', 'Comics')}"
        )
    embed.add_field(name="🗃️ Top collection", value="\n".join(lines)[:1024], inline=False)
    if len(items) > 10:
        embed.set_footer(text=f"{len(items) - 10} carte(s) supplémentaire(s) non affichée(s)")
    await interaction.response.send_message(embed=embed)


@tree.command(name="marvelcomics", description="📚 Dernières sorties Marvel du mois (ComicVine)")
@app_commands.describe(recherche="Recherche un comic Marvel spécifique (optionnel)")
async def slash_marvel_comics(interaction: discord.Interaction, recherche: str = ""):
    await interaction.response.defer()
    if not COMICVINE_API_KEY:
        await interaction.followup.send(embed=_no_api_embed()); return

    _, _, month_label = _cv_month_bounds()
    meta = _publisher_meta(31)

    if recherche:
        comics = await _fetch_cv_search(recherche, publisher_id=31)
        titre  = f"{meta['emoji']} {meta['name']} — Recherche : {recherche}"
    else:
        comics = await _fetch_cv_this_month(publisher_id=31, limit=20)
        titre  = f"{meta['emoji']} Sorties du mois {meta['name']} — {month_label}"

    if not comics:
        await interaction.followup.send("❌ Aucun résultat. Réessaie dans quelques instants."); return

    view  = CVPageView(comics, titre, 0xEC1D24)
    await interaction.followup.send(embed=view._embed(), view=view)


@tree.command(name="dccomics", description="📚 Dernières sorties DC Comics du mois (ComicVine)")
@app_commands.describe(recherche="Recherche un comic DC spécifique (optionnel)")
async def slash_dc_comics(interaction: discord.Interaction, recherche: str = ""):
    await interaction.response.defer()
    if not COMICVINE_API_KEY:
        await interaction.followup.send(embed=_no_api_embed()); return

    _, _, month_label = _cv_month_bounds()
    meta = _publisher_meta(10)

    if recherche:
        comics = await _fetch_cv_search(recherche, publisher_id=10)
        titre  = f"{meta['emoji']} {meta['name']} — Recherche : {recherche}"
    else:
        comics = await _fetch_cv_this_month(publisher_id=10, limit=20)
        titre  = f"{meta['emoji']} Sorties du mois {meta['name']} — {month_label}"

    if not comics:
        await interaction.followup.send("❌ Aucun résultat DC trouvé."); return

    view  = CVPageView(comics, titre, 0x0075C8)
    await interaction.followup.send(embed=view._embed(), view=view)


@tree.command(name="comicsinfo", description="📚 Recherche n'importe quel comic (Marvel, DC, Image...)")
@app_commands.describe(recherche="Titre du comic à rechercher")
async def slash_comics_info(interaction: discord.Interaction, recherche: str):
    await interaction.response.defer()
    if not COMICVINE_API_KEY:
        await interaction.followup.send(embed=_no_api_embed()); return

    comics = await _fetch_cv_search(recherche, limit=12)
    if not comics:
        await interaction.followup.send(f"❌ Aucun résultat pour `{recherche}`."); return

    view  = CVPageView(comics, f"🔍 Recherche : {recherche}", 0x8B0000)
    await interaction.followup.send(embed=view._embed(), view=view)


# ════════════════════════════════════════════════════════════════
#  📡  SALONS COMICS AUTO (Marvel & DC)
# ════════════════════════════════════════════════════════════════

MARVEL_CHANNEL_ID: int = 0   # salon auto Marvel
DC_CHANNEL_ID:     int = 0   # salon auto DC
COMICS_INTERVAL    = 24      # heures entre chaque post
comics_last_posted: dict[str, str] = {}  # {publisher: dernière date postée}


@tasks.loop(hours=COMICS_INTERVAL)
async def comics_auto_loop():
    """Envoie automatiquement les nouvelles sorties dans les salons configurés."""
    if not COMICVINE_API_KEY:
        return

    _, _, month_label = _cv_month_bounds()

    for publisher, channel_id, pub_id in [
        ("Marvel", MARVEL_CHANNEL_ID, 31),
        ("DC",     DC_CHANNEL_ID,     10),
    ]:
        if not channel_id:
            continue
        for guild in bot.guilds:
            ch = guild.get_channel(channel_id)
            if not ch:
                continue
            try:
                comics = await _fetch_cv_this_month(publisher_id=pub_id, limit=8)
                if not comics:
                    continue

                # Vérifier s'il y a du nouveau depuis le dernier post
                top_date = comics[0].get("store") or comics[0].get("date", "")
                last     = comics_last_posted.get(publisher, "")
                if top_date and top_date == last:
                    continue  # rien de nouveau

                comics_last_posted[publisher] = top_date
                mark_data_dirty()
                await _send_comic_release_batch(ch, comics[:6], pub_id, f"Sorties du mois {publisher} — {month_label}")
            except Exception as e:
                print(f"⚠️ Erreur comics auto {publisher} : {e}")


@comics_auto_loop.before_loop
async def before_comics():
    await bot.wait_until_ready()


@tree.command(name="setmarvelchannel", description="[Admin] Configure le salon des sorties Marvel automatiques")
@app_commands.describe(salon="Salon où envoyer les nouvelles sorties Marvel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setmarvelchannel(interaction: discord.Interaction, salon: discord.TextChannel):
    global MARVEL_CHANNEL_ID
    MARVEL_CHANNEL_ID = salon.id
    save_data()

    if not comics_auto_loop.is_running():
        comics_auto_loop.start()

    # Envoie immédiatement les dernières sorties
    await interaction.response.defer(ephemeral=True)
    if COMICVINE_API_KEY:
        comics = await _fetch_cv_this_month(publisher_id=31, limit=6)
        if comics:
            _, _, month_label = _cv_month_bounds()
            await _send_comic_release_batch(salon, comics, 31, f"Sorties du mois Marvel — {month_label}")

    await interaction.followup.send(
        f"✅ Salon Marvel configuré : {salon.mention}\n"
        f"Les nouvelles sorties seront postées toutes les **{COMICS_INTERVAL}h**.",
        ephemeral=True
    )


@tree.command(name="setdcchannel", description="[Admin] Configure le salon des sorties DC automatiques")
@app_commands.describe(salon="Salon où envoyer les nouvelles sorties DC")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setdcchannel(interaction: discord.Interaction, salon: discord.TextChannel):
    global DC_CHANNEL_ID
    DC_CHANNEL_ID = salon.id
    save_data()

    if not comics_auto_loop.is_running():
        comics_auto_loop.start()

    await interaction.response.defer(ephemeral=True)
    if COMICVINE_API_KEY:
        comics = await _fetch_cv_this_month(publisher_id=10, limit=6)
        if comics:
            _, _, month_label = _cv_month_bounds()
            await _send_comic_release_batch(salon, comics, 10, f"Sorties du mois DC Comics — {month_label}")

    await interaction.followup.send(
        f"✅ Salon DC configuré : {salon.mention}\n"
        f"Les nouvelles sorties seront postées toutes les **{COMICS_INTERVAL}h**.",
        ephemeral=True
    )


@tree.command(name="stopcomics", description="[Admin] Désactive les posts automatiques de comics")
@app_commands.choices(publisher=[
    app_commands.Choice(name="Marvel", value="marvel"),
    app_commands.Choice(name="DC",     value="dc"),
    app_commands.Choice(name="Les deux", value="both"),
])
@app_commands.checks.has_permissions(administrator=True)
async def slash_stopcomics(interaction: discord.Interaction, publisher: str = "both"):
    global MARVEL_CHANNEL_ID, DC_CHANNEL_ID
    msg = []
    if publisher in ("marvel", "both"):
        MARVEL_CHANNEL_ID = 0
        msg.append("🔴 Marvel désactivé")
    if publisher in ("dc", "both"):
        DC_CHANNEL_ID = 0
        msg.append("🔵 DC désactivé")
    if not MARVEL_CHANNEL_ID and not DC_CHANNEL_ID:
        if comics_auto_loop.is_running():
            comics_auto_loop.cancel()
    save_data()
    await interaction.response.send_message("\n".join(msg), ephemeral=True)

# ════════════════════════════════════════════════════════════════
#  😀  VOLER UN EMOJI
# ════════════════════════════════════════════════════════════════

@tree.command(name="voleremoji", description="[Admin] Copie un emoji d'un autre serveur et l'ajoute ici")
@app_commands.describe(
    emoji="L'emoji à voler (colle-le directement : <:nom:id> ou <a:nom:id>)",
    nom="Nouveau nom pour l'emoji (optionnel, sinon garde le nom original)"
)
@app_commands.checks.has_permissions(manage_emojis=True)
async def slash_voler_emoji(interaction: discord.Interaction, emoji: str, nom: str = ""):
    await interaction.response.defer(ephemeral=True)

    import re as _re

    # Parser l'emoji : <:nom:id> ou <a:nom:id>
    match = _re.match(r'<(a?):(\w+):(\d+)>', emoji.strip())
    if not match:
        await interaction.followup.send(
            "❌ Format invalide ! Colle un vrai emoji custom : `<:nom:id>` ou `<a:nom:id>`\n"
            "*(Les emojis de base comme 😀 ne peuvent pas être volés)*",
            ephemeral=True
        )
        return

    animated   = match.group(1) == "a"
    emoji_name = nom.strip() or match.group(2)
    emoji_id   = match.group(3)
    ext        = "gif" if animated else "png"
    url        = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128&quality=lossless"

    # Vérifier la limite d'emojis du serveur
    guild      = interaction.guild
    max_emojis = guild.emoji_limit
    current    = len([e for e in guild.emojis if e.animated == animated])
    kind       = "animés" if animated else "statiques"

    if current >= max_emojis:
        await interaction.followup.send(
            f"❌ Limite d'emojis {kind} atteinte ({current}/{max_emojis}).\n"
            "Supprime un emoji existant avant d'en ajouter un nouveau.",
            ephemeral=True
        )
        return

    # Télécharger l'image de l'emoji
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    await interaction.followup.send(
                        f"❌ Impossible de télécharger l'emoji (code {resp.status}).\n"
                        "L'emoji existe peut-être plus ou l'ID est invalide.",
                        ephemeral=True
                    )
                    return
                image_data = await resp.read()
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur téléchargement : `{e}`", ephemeral=True)
        return

    # Nettoyer le nom (Discord n'accepte que lettres, chiffres, underscore)
    import re as _re2
    emoji_name = _re2.sub(r'[^\w]', '_', emoji_name)[:32]
    if not emoji_name:
        emoji_name = "emoji_vole"

    # Ajouter l'emoji au serveur
    try:
        new_emoji = await guild.create_custom_emoji(
            name=emoji_name,
            image=image_data,
            reason=f"Emoji volé par {interaction.user} via /volerEmoji"
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ Je n'ai pas la permission de gérer les emojis.\n"
            "Donne-moi la permission **Gérer les emojis** dans les paramètres du serveur.",
            ephemeral=True
        )
        return
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Erreur Discord : `{e}`", ephemeral=True)
        return

    # Succès !
    embed = discord.Embed(
        title="✅ Emoji volé avec succès !",
        description=(
            f"L'emoji {new_emoji} a été ajouté au serveur !\n\n"
            f"**Nom :** `:{new_emoji.name}:`\n"
            f"**Type :** {'Animé 🎬' if animated else 'Statique 🖼️'}\n"
            f"**Emojis {kind} :** {current + 1}/{max_emojis}"
        ),
        color=0x57F287,
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=url)
    embed.set_footer(text=f"Volé par {interaction.user.display_name}")
    await interaction.followup.send(embed=embed, ephemeral=True)

    # Log
    log_embed = discord.Embed(title="😀 Emoji ajouté", color=0x57F287, timestamp=datetime.utcnow())
    log_embed.add_field(name="Emoji",   value=f"{new_emoji} `:{new_emoji.name}:`", inline=True)
    log_embed.add_field(name="Par",     value=f"{interaction.user.mention}",        inline=True)
    log_embed.add_field(name="Type",    value="Animé" if animated else "Statique",  inline=True)
    await send_log(guild, log_embed)




# ════════════════════════════════════════════════════════════════
#  🚀  [20] LANCEMENT
# ════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    bot.run(TOKEN)
