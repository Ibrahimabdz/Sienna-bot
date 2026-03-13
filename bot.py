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

def save_data():
    """Sauvegarde xp_data et warns dans data.json"""
    try:
        payload = {
            "xp_data": {str(k): v for k, v in xp_data.items()},
            "warns":   {str(k): v for k, v in warns.items()},
            "reaction_roles": {str(k): v for k, v in reaction_roles.items()},
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde : {e}")

def load_data():
    """Charge xp_data et warns depuis data.json au démarrage"""
    global xp_data, warns, reaction_roles
    if not os.path.exists(DATA_FILE):
        print("ℹ️ Aucun fichier data.json trouvé — démarrage à zéro.")
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        xp_data        = {int(k): v for k, v in payload.get("xp_data", {}).items()}
        warns          = {int(k): v for k, v in payload.get("warns",   {}).items()}
        reaction_roles = {int(k): v for k, v in payload.get("reaction_roles", {}).items()}
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
#  [11] 📣  Auto-bump
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

# ════════════════════════════════════════════════════════════════
#  🤖  [2] INTENTS & BOT
# ════════════════════════════════════════════════════════════════
intents = discord.Intents.all()
bot  = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

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
    save_data()


@bot.event
async def on_ready():
    load_data()
    print(f"✅  Connecté : {bot.user}  (ID: {bot.user.id})")
    try:
        synced = await tree.sync()
        print(f"🔄  {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"Erreur sync : {e}")
    save_loop.start()
    check_free_games.start()
    if not counter_loop.is_running():
        counter_loop.start()
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
        activity=discord.Activity(type=discord.ActivityType.watching, name="la taverne 🍺")
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
    log.set_footer(text=f"ID : {member.id}")
    await send_log(guild, log)

    # Auto-rôles
    for role_id in AUTO_ROLES:
        role = guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-rôle")
            except Exception:
                pass

    # Message de bienvenue
    ch_id = WELCOME_CHANNEL_ID
    if not ch_id:
        return
    ch = guild.get_channel(ch_id)
    if not ch:
        return
    try:
        from welcome_card import make_welcome_gif
        buf  = await make_welcome_gif(member, is_welcome=True)
        file = discord.File(buf, filename="bienvenue.gif")
        embed = discord.Embed(
            description=(
                f"Les portes s'ouvrent pour {member.mention} ! 🍺\n\n"
                "┣ ✅ Accepte les **règles**\n"
                f"┗ 🎭 Choisis tes **rôles** !"
            ),
            color=0x8B0000
        )
        embed.set_image(url="attachment://bienvenue.gif")
        embed.set_footer(text=f"🍻 Aventurier #{guild.member_count}", icon_url=guild.icon.url if guild.icon else None)
        await ch.send(embed=embed, file=file)
    except Exception:
        embed = discord.Embed(
            title="⚔️ Bienvenue à la Taverne !",
            description=f"Heureux de t'accueillir {member.mention} ! 🍺",
            color=0x8B0000
        )
        await ch.send(embed=embed)
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
    elif before.channel and not after.channel:
        # Quitté
        if uid in voice_join_time:
            start = voice_join_time.pop(uid)
            d = get_user_data(uid)
            d["voice_history"].append((start, now))
            cutoff = now - 14 * 86400
            d["voice_history"] = [(s, e) for s, e in d["voice_history"] if e >= cutoff]
    elif before.channel and after.channel:
        # Changement de salon
        if uid in voice_join_time:
            start = voice_join_time[uid]
            d = get_user_data(uid)
            d["voice_history"].append((start, now))
            cutoff = now - 14 * 86400
            d["voice_history"] = [(s, e) for s, e in d["voice_history"] if e >= cutoff]
        voice_join_time[uid] = now
        d = get_user_data(uid)
        d["top_voice"][after.channel.name] = d["top_voice"].get(after.channel.name, 0) + 1

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
    if now - xp_cooldowns.get(uid, 0) >= XP_COOLDOWN:
        xp_cooldowns[uid] = now
        save_data()
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

class TicketCloseButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        uid = next((u for u, c in open_tickets.items() if c == channel.id), None)
        if uid:
            del open_tickets[uid]
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
        await asyncio.sleep(5)
        await channel.delete(reason="Ticket fermé")


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
    await ticket_ch.send(embed=embed, view=TicketCloseButton())
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
#  🎮  [13] MINI-JEUX — /coinflip /dice /rps /slots /guess
# ════════════════════════════════════════════════════════════════
@tree.command(name="coinflip", description="🪙 Lance une pièce")
async def slash_coinflip(interaction: discord.Interaction):
    result = random.choice(["Pile 🪙", "Face 🎭"])
    embed = discord.Embed(title="🪙 Pile ou Face", description=f"Résultat : **{result}**", color=0xFFD700)
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="dice", description="🎲 Lance un dé")
@app_commands.describe(faces="Nombre de faces (défaut : 6)")
async def slash_dice(interaction: discord.Interaction, faces: int = 6):
    if faces < 2:
        await interaction.response.send_message("❌ Minimum 2 faces.", ephemeral=True)
        return
    result = random.randint(1, faces)
    embed = discord.Embed(title=f"🎲 Dé à {faces} faces", description=f"Résultat : **{result}**", color=0x9B59B6)
    embed.set_footer(text=f"Lancé par {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="rps", description="✂️ Pierre-Papier-Ciseaux contre le bot")
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


@tree.command(name="slots", description="🎰 Machine à sous")
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


@tree.command(name="guess", description="🔢 Devine un nombre entre 1 et 100 (5 essais)")
async def slash_guess(interaction: discord.Interaction):
    left = check_game_cooldown(interaction.user.id, "guess", 30)
    if left > 0:
        await interaction.response.send_message(f"⏳ Cooldown ! Réessaie dans **{left:.0f}s**.", ephemeral=True)
        return
    secret = random.randint(1, 100)
    await interaction.response.send_message(
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
    await interaction.response.send_message(f"✅ Salon logs : {channel.mention}", ephemeral=True)

@tree.command(name="setwelcome", description="[Admin] Définit le salon de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    global WELCOME_CHANNEL_ID
    WELCOME_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"✅ Salon bienvenue : {channel.mention}", ephemeral=True)

@tree.command(name="setgoodbye", description="[Admin] Définit le salon d'au revoir")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setgoodbye(interaction: discord.Interaction, channel: discord.TextChannel):
    global GOODBYE_CHANNEL_ID
    GOODBYE_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"✅ Salon au revoir : {channel.mention}", ephemeral=True)

@tree.command(name="setfreegames", description="[Admin] Définit le salon des jeux gratuits")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setfreegames(interaction: discord.Interaction, channel: discord.TextChannel):
    global FREE_GAMES_CHANNEL_ID
    FREE_GAMES_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"✅ Salon jeux gratuits : {channel.mention}", ephemeral=True)

@tree.command(name="setlevelup", description="[Admin] Définit le salon des notifications de level-up")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setlevelup(interaction: discord.Interaction, channel: discord.TextChannel):
    global LEVELUP_CHANNEL_ID
    LEVELUP_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"✅ Salon level-up : {channel.mention}", ephemeral=True)

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
        await interaction.response.send_message(f"✅ {role.mention} ajouté aux auto-rôles !", ephemeral=True)
    elif action == "remove":
        if role.id in AUTO_ROLES:
            AUTO_ROLES.remove(role.id)
        AUTO_ROLE_ID = AUTO_ROLES[0] if AUTO_ROLES else 0
        await interaction.response.send_message(f"✅ {role.mention} retiré des auto-rôles.", ephemeral=True)

@tree.command(name="setticketcategory", description="[Admin] Définit la catégorie des tickets")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setticketcategory(interaction: discord.Interaction, categorie: discord.CategoryChannel):
    global TICKET_CATEGORY_ID
    TICKET_CATEGORY_ID = categorie.id
    await interaction.response.send_message(f"✅ Catégorie tickets : **{categorie.name}**", ephemeral=True)

@tree.command(name="ticketpanel", description="[Admin] Envoie le panel de tickets avec l'image dans ce salon")
@app_commands.checks.has_permissions(administrator=True)
async def slash_ticketpanel(interaction: discord.Interaction):
    import os as _os
    banner_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ticket_banner.png")
    if not os.path.exists(banner_path):
        banner_path = os.path.join(os.getcwd(), "ticket_banner.png")

    embed = discord.Embed(
        title="",
        description=(
            "**Besoin d'aide ? Tu veux nous rejoindre ?**\n\nChoisis la catégorie qui correspond à ta demande\n\net clique sur le bouton ci-dessous. 🛡️\n\n\n🆘 **Problème / Aide** — Un souci sur le serveur ?\n\n🤝 **Partenariat** — Tu veux proposer un partenariat ?\n\n⚔️ **Devenir Staff** — Tu veux rejoindre l'équipe ?"
        ),
        color=0x8B0000
    )
    embed.set_footer(text="Un seul ticket actif par personne • La Taverne")

    if _os.path.exists(banner_path):
        file  = discord.File(banner_path, filename="ticket_banner.png")
        embed.set_image(url="attachment://ticket_banner.png")
        await interaction.channel.send(embed=embed, file=file, view=TicketSelectView())
    else:
        await interaction.channel.send(embed=embed, view=TicketSelectView())

    await interaction.response.send_message("✅ Panel tickets envoyé !", ephemeral=True)

@tree.command(name="setlevelrole", description="[Admin] Associe un rôle à un niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(niveau="Niveau requis", role="Rôle à attribuer")
async def slash_setlevelrole(interaction: discord.Interaction, niveau: int, role: discord.Role):
    LEVEL_ROLES[niveau] = role.id
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


@tree.command(name="ban", description="[Mod] Bannit un membre")
@app_commands.describe(membre="Membre à bannir", raison="Raison du ban")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if membre.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ Je ne peux pas bannir ce membre (rôle trop élevé).", ephemeral=True)
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
    if membre.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ Je ne peux pas expulser ce membre.", ephemeral=True)
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
    if membre.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message("❌ Je ne peux pas muter ce membre.", ephemeral=True)
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
    uid = membre.id
    if uid not in warns:
        warns[uid] = []
    warns[uid].append({
        "raison": raison,
        "mod":    str(interaction.user),
        "date":   datetime.utcnow().strftime("%d/%m/%Y %H:%M")
    })
    count = len(warns[uid])

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
    warns.pop(membre.id, None)
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


@tree.command(name="puissance4", description="🔴🟡 Lance une partie de Puissance 4")
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


@bot.event
async def on_member_join_counter(member: discord.Member):
    await update_counters(member.guild)


@bot.event
async def on_member_remove_counter(member: discord.Member):
    await update_counters(member.guild)


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
reaction_roles: dict[int, dict[str, int]] = {}

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


@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Erreur : {error}", ephemeral=True)
        raise error

# ════════════════════════════════════════════════════════════════
#  🚀  [20] LANCEMENT
# ════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════
#  📣  [11] AUTO-BUMP (toutes les 2h)
# ════════════════════════════════════════════════════════════════

BUMP_CHANNEL_ID: int = 0
BUMP_ROLE_ID:    int = 0
bump_enabled:    bool = False

@tasks.loop(hours=2)
async def auto_bump():
    if not bump_enabled or not BUMP_CHANNEL_ID:
        return
    for guild in bot.guilds:
        ch = guild.get_channel(BUMP_CHANNEL_ID)
        if not ch:
            continue
        try:
            await ch.send("/bump")
            embed = discord.Embed(
                title="📣 Bump effectué !",
                description=(
                    "Le serveur vient d'être **bump** sur Disboard ! 🚀\n\n"
                    "Merci d'aider la Taverne à grandir !\n"
                    "Prochain bump dans **2 heures**. ⏰"
                ),
                color=0x8B0000,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Auto-bump • La Taverne")
            if BUMP_ROLE_ID:
                role = guild.get_role(BUMP_ROLE_ID)
                mention = role.mention if role else ""
                await ch.send(mention, embed=embed)
            else:
                await ch.send(embed=embed)
        except Exception as e:
            print(f"⚠️ Erreur auto-bump : {e}")


@auto_bump.before_loop
async def before_bump():
    await bot.wait_until_ready()


@tree.command(name="setbump", description="[Admin] Configure le salon et active le bump automatique toutes les 2h")
@app_commands.describe(salon="Salon où envoyer /bump", role="Rôle à mentionner (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def slash_setbump(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role = None):
    global BUMP_CHANNEL_ID, BUMP_ROLE_ID, bump_enabled
    BUMP_CHANNEL_ID = salon.id
    BUMP_ROLE_ID    = role.id if role else 0
    bump_enabled    = True
    if not auto_bump.is_running():
        auto_bump.start()
    embed = discord.Embed(
        title="✅ Auto-bump configuré !",
        description=(
            f"📌 Salon : {salon.mention}\n"
            f"🔔 Rôle  : {role.mention if role else 'Aucun'}\n"
            f"⏰ Fréquence : toutes les **2 heures**"
        ),
        color=0x57F287
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="stopbump", description="[Admin] Désactive le bump automatique")
@app_commands.checks.has_permissions(administrator=True)
async def slash_stopbump(interaction: discord.Interaction):
    global bump_enabled
    bump_enabled = False
    if auto_bump.is_running():
        auto_bump.cancel()
    await interaction.response.send_message("✅ Auto-bump désactivé.", ephemeral=True)


@tree.command(name="bumpnow", description="[Admin] Envoie /bump immédiatement et remet le timer à zéro")
@app_commands.checks.has_permissions(administrator=True)
async def slash_bumpnow(interaction: discord.Interaction):
    if not BUMP_CHANNEL_ID:
        await interaction.response.send_message("❌ Configure d'abord avec `/setbump`.", ephemeral=True)
        return
    ch = interaction.guild.get_channel(BUMP_CHANNEL_ID)
    if not ch:
        await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)
        return
    await ch.send("/bump")
    embed = discord.Embed(
        title="📣 Bump manuel envoyé !",
        description=f"/bump envoyé dans {ch.mention}\nProchain auto-bump dans **2 heures**.",
        color=0x57F287
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    if auto_bump.is_running():
        auto_bump.restart()


@tree.command(name="bumpstatus", description="Affiche le statut du bump automatique")
async def slash_bumpstatus(interaction: discord.Interaction):
    if not bump_enabled or not BUMP_CHANNEL_ID:
        embed = discord.Embed(
            title="📣 Auto-bump",
            description="❌ **Désactivé**\nUtilise `/setbump` pour l'activer.",
            color=0xED4245
        )
    else:
        ch        = interaction.guild.get_channel(BUMP_CHANNEL_ID)
        next_bump = auto_bump.next_iteration
        next_ts   = f"<t:{int(next_bump.timestamp())}:R>" if next_bump else "Bientôt"
        embed = discord.Embed(
            title="📣 Auto-bump",
            description=(
                f"✅ **Actif**\n\n"
                f"📌 Salon : {ch.mention if ch else '?'}\n"
                f"⏰ Prochain bump : {next_ts}\n"
                f"🔄 Fréquence : toutes les 2 heures"
            ),
            color=0x57F287
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)
