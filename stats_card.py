"""
stats_card.py — Génère une image de stats style Taverne Fantastique
Dépendances : Pillow, aiohttp
Place ce fichier dans le même dossier que bot.py
"""

from PIL import Image, ImageDraw, ImageFont
import io, os, aiohttp, asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BG_PATH  = os.path.join(BASE_DIR, "taverne_bg.png")

def _find_font(*names):
    dirs = [
        r"C:\Windows\Fonts",
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts"),
        "/usr/share/fonts/truetype/google-fonts",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
    ]
    for name in names:
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None

POPPINS_BOLD = _find_font("Poppins-Bold.ttf",    "arialbd.ttf",  "LiberationSans-Bold.ttf")
POPPINS_REG  = _find_font("Poppins-Regular.ttf", "arial.ttf",    "LiberationSans-Regular.ttf")
POPPINS_MED  = _find_font("Poppins-Medium.ttf",  "arial.ttf")
LORA         = _find_font("Lora-Variable.ttf",   "georgia.ttf")
LORA_ITALIC  = _find_font("Lora-Italic-Variable.ttf", "georgiai.ttf")
FALLBACK     = _find_font("arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")

W, H = 960, 520
GOLD        = (255, 210,  80, 255)
GOLD_DARK   = (200, 150,  40, 255)
AMBER       = (255, 180,  40, 255)
PURPLE      = (160, 100, 255, 255)
PURPLE_SOFT = ( 90,  50, 160, 200)
TEAL        = ( 80, 220, 200, 255)
WHITE       = (255, 255, 255, 255)
PANEL_BG    = ( 12,   6,  25, 195)
PANEL_BG2   = ( 20,  10,  40, 175)
BORDER      = (160, 110,  60, 180)
BAR_BG      = ( 30,  15,  55, 210)
GREEN_XP    = ( 80, 220, 130, 255)
PAD = 22

def F(path, size):
    for p in [path, POPPINS_BOLD, FALLBACK]:
        if p:
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

def rrect(draw, xy, r, fill=None, outline=None, width=2):
    if fill:    draw.rounded_rectangle(xy, radius=r, fill=fill)
    if outline: draw.rounded_rectangle(xy, radius=r, outline=outline, width=width)

def panel(draw, xy, r=14, fill=PANEL_BG, border=BORDER, bw=2):
    rrect(draw, xy, r, fill=fill)
    rrect(draw, xy, r, outline=border, width=bw)

def gold_line(draw, x1, y, x2, alpha=120):
    draw.line([(x1, y), (x2, y)], fill=(*GOLD_DARK[:3], alpha), width=1)

def txt(draw, pos, text, font, fill=WHITE, anchor="la"):
    draw.text(pos, str(text), font=font, fill=fill, anchor=anchor)

def draw_sparkline(draw, data_pts, x1, y1, xw, yh, color, combined_max):
    if not data_pts or combined_max == 0: return
    pts = []
    n = len(data_pts)
    for i, v in enumerate(data_pts):
        px = x1 + int(i / (n-1) * xw) if n > 1 else x1 + xw // 2
        py = y1 + yh - int((v / combined_max) * yh * 0.9) - 4
        pts.append((px, py))
    for j in range(len(pts)-1):
        draw.line([pts[j], pts[j+1]], fill=(*color[:3], 220), width=2)
    for px, py in pts:
        draw.ellipse([px-3, py-3, px+3, py+3], fill=(*color[:3], 255))

async def fetch_avatar(avatar_url: str, size: int = 72):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(avatar_url) as r:
                if r.status != 200: return None
                data = await r.read()
        img  = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        return out
    except: return None

def generate_stats_card(data: dict, avatar_img=None) -> io.BytesIO:
    """Synchrone — appelée dans run_in_executor."""
    if os.path.exists(BG_PATH):
        bg = Image.open(BG_PATH).convert("RGBA").resize((W, H), Image.LANCZOS)
    else:
        bg = Image.new("RGBA", (W, H), (15, 8, 30, 255))

    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dv  = ImageDraw.Draw(vig)
    for i in range(120):
        alpha = int(220 * (i / 120) ** 1.6)
        dv.rectangle([i, i, W-i, H-i], outline=(0, 0, 0, alpha))
    bg     = Image.alpha_composite(bg, vig)
    canvas = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (5, 2, 18, 155)))
    d      = ImageDraw.Draw(canvas)

    f_name   = F(POPPINS_BOLD, 38);  f_tag    = F(POPPINS_REG,  20)
    f_small  = F(POPPINS_REG,  13);  f_rank_l = F(POPPINS_MED,  13)
    f_italic = F(LORA_ITALIC,  15)

    # ── HEADER ──────────────────────────────────────────────
    HH = 100
    panel(d, [PAD, PAD, W-PAD, HH+PAD], r=16, fill=(8,3,20,210), border=(*GOLD_DARK[:3],160), bw=2)
    AX, AY, AR = PAD+54, PAD+54, 36
    if avatar_img:
        av = avatar_img.resize((AR*2, AR*2), Image.LANCZOS)
        canvas.paste(av, (AX-AR, AY-AR), av)
    else:
        d.ellipse([AX-AR, AY-AR, AX+AR, AY+AR], fill=(*data.get("avatar_color",(100,80,180)),255))
        txt(d, (AX, AY), data["name"][0].upper(), F(POPPINS_BOLD, 32), fill=WHITE, anchor="mm")
    d.ellipse([AX-AR-3, AY-AR-3, AX+AR+3, AY+AR+3], outline=(*GOLD[:3],200), width=2)
    NX = AX+AR+18
    txt(d, (NX, PAD+14), data["name"], f_name, fill=WHITE)
    nw = int(d.textlength(data["name"], font=f_name))
    txt(d, (NX+nw+8, PAD+22), data["tag"], f_tag, fill=(*PURPLE[:3],200))
    txt(d, (NX, PAD+56), f"⚔  {data['server']}", f_small, fill=(*GOLD[:3],190))
    DX = W-PAD-10
    panel(d, [DX-185, PAD+8,  DX-10, PAD+46], r=8, fill=(20,10,45,200), border=(*PURPLE[:3],120), bw=1)
    panel(d, [DX-185, PAD+54, DX-10, PAD+92], r=8, fill=(20,10,45,200), border=(*PURPLE[:3],120), bw=1)
    txt(d, (DX-100, PAD+14), "Créé le",      f_rank_l, fill=(*GOLD[:3],200), anchor="mm")
    txt(d, (DX-100, PAD+32), data["created"], f_small,  fill=WHITE, anchor="mm")
    txt(d, (DX-100, PAD+60), "A rejoint",     f_rank_l, fill=(*TEAL[:3],200), anchor="mm")
    txt(d, (DX-100, PAD+78), data["joined"],  f_small,  fill=WHITE, anchor="mm")

    # ── BARRE XP ─────────────────────────────────────────────
    BY = HH+PAD+10
    panel(d, [PAD, BY, W-PAD, BY+52], r=12, fill=(10,4,22,205), border=(*GOLD_DARK[:3],130), bw=1)
    xp_pct = min(data["xp"] / max(data["xp_max"], 1), 1.0)
    BW = W-PAD*2-200;  BX = PAD+14;  BYY = BY+28
    txt(d, (BX, BY+10), f"NIVEAU  {data['level']}", F(POPPINS_BOLD,15), fill=GOLD)
    txt(d, (BX+135, BY+10), f"Rang messages : #{data['rank_msg']}  ·  Rang vocal : #{data['rank_voice']}", f_small, fill=(*PURPLE[:3],220))
    d.rounded_rectangle([BX, BYY, BX+BW, BYY+12], radius=6, fill=BAR_BG)
    bw2 = int(BW * xp_pct)
    for i in range(bw2):
        t = i / max(bw2, 1)
        d.line([(BX+i, BYY), (BX+i, BYY+12)], fill=(int(80+120*t), int(180+40*t), int(130-30*t), 230))
    d.rounded_rectangle([BX, BYY, BX+BW, BYY+12], radius=6, outline=(*TEAL[:3],80), width=1)
    txt(d, (BX+BW+10, BYY+6), f"{data['xp']:,} / {data['xp_max']:,} XP", f_small, fill=(*GREEN_XP[:3],220), anchor="lm")

    # ── PANNEAUX STATS ───────────────────────────────────────
    SY = BY+62;  SH = 120;  CW = (W-PAD*2-20)//3

    def spanel(sx, sy, w, h, title, icon, rows):
        panel(d, [sx,sy,sx+w,sy+h], r=12, fill=PANEL_BG2, border=(*BORDER[:3],140), bw=1)
        d.rounded_rectangle([sx,sy,sx+w,sy+30], radius=12, fill=(*PURPLE_SOFT[:3],160))
        d.rounded_rectangle([sx,sy+18,sx+w,sy+30], radius=0, fill=(*PURPLE_SOFT[:3],160))
        txt(d, (sx+w//2, sy+15), f"{icon}  {title}", F(POPPINS_BOLD,13), fill=GOLD, anchor="mm")
        gold_line(d, sx+10, sy+30, sx+w-10, alpha=100)
        for i,(label,val,color) in enumerate(rows):
            ry = sy+42+i*25
            d.rounded_rectangle([sx+8,ry-1,sx+38,ry+17], radius=5, fill=(*AMBER[:3],50))
            txt(d, (sx+23,ry+8), label, F(POPPINS_BOLD,11), fill=(*AMBER[:3],230), anchor="mm")
            txt(d, (sx+w-10,ry+8), val, F(POPPINS_BOLD,16), fill=color, anchor="rm")

    spanel(PAD, SY, CW, SH, "Messages", "#",
        [("1j",str(data["msgs_1d"]),WHITE), ("7j",str(data["msgs_7d"]),(*TEAL[:3],255)), ("14j",f"{data['msgs_14d']:,}",GOLD)])
    spanel(PAD+CW+10, SY, CW, SH, "Activité Vocale", "🔊",
        [("1j",f"{data['voice_1d']}h",WHITE), ("7j",f"{data['voice_7d']}h",(*TEAL[:3],255)), ("14j",f"{data['voice_14d']}h",GOLD)])

    TX3 = PAD+CW*2+20
    panel(d, [TX3,SY,W-PAD,SY+SH], r=12, fill=PANEL_BG2, border=(*BORDER[:3],140), bw=1)
    d.rounded_rectangle([TX3,SY,W-PAD,SY+30], radius=12, fill=(*PURPLE_SOFT[:3],160))
    d.rounded_rectangle([TX3,SY+18,W-PAD,SY+30], radius=0, fill=(*PURPLE_SOFT[:3],160))
    txt(d, (TX3+(CW//2),SY+15), "📊  Top Salons", F(POPPINS_BOLD,13), fill=GOLD, anchor="mm")
    gold_line(d, TX3+10, SY+30, W-PAD-10, alpha=100)
    tx = TX3+14
    txt(d,(tx,SY+44),"💬",F(POPPINS_REG,14),fill=GOLD); txt(d,(tx+26,SY+44),data["top_channel"],F(POPPINS_BOLD,13),fill=WHITE)
    txt(d,(tx,SY+70),"🎙",F(POPPINS_REG,14),fill=TEAL); txt(d,(tx+26,SY+70),data["top_voice"],F(POPPINS_MED,13),fill=(*TEAL[:3],220))
    txt(d,(tx,SY+96),"✨",F(POPPINS_REG,14),fill=PURPLE); txt(d,(tx+26,SY+96),f"{data['msgs_14d']:,} msgs en 14j",F(POPPINS_MED,12),fill=(*PURPLE[:3],220))

    # ── SPARKLINES ───────────────────────────────────────────
    CHY = SY+SH+12;  CHH = H-CHY-PAD-10
    panel(d, [PAD,CHY,W-PAD,CHY+CHH], r=12, fill=(8,3,18,210), border=(*GOLD_DARK[:3],130), bw=1)
    txt(d, (PAD+16,CHY+10), "📈  Activité — 14 derniers jours", F(POPPINS_BOLD,14), fill=GOLD)
    LX = W-PAD-220
    d.ellipse([LX,CHY+14,LX+10,CHY+24], fill=(*GREEN_XP[:3],255)); txt(d,(LX+16,CHY+10),"Messages",f_small,fill=(*GREEN_XP[:3],220))
    d.ellipse([LX+110,CHY+14,LX+120,CHY+24], fill=(*PURPLE[:3],255)); txt(d,(LX+126,CHY+10),"Vocal (h)",f_small,fill=(*PURPLE[:3],220))
    gold_line(d, PAD+10, CHY+34, W-PAD-10, alpha=80)
    CX1,CX2 = PAD+18, W-PAD-18;  CY1,CY2 = CHY+40, CHY+CHH-16
    cw_c = CX2-CX1;  ch_c = CY2-CY1
    chart_m = data.get("chart_msgs",[0]*14);  chart_v = data.get("chart_voice",[0]*14)
    chart_vs = [v*3 for v in chart_v]
    cmax = max(max(chart_m,default=1), max(chart_vs,default=1), 1)
    draw_sparkline(d, chart_m,  CX1, CY1, cw_c, ch_c, GREEN_XP, cmax)
    draw_sparkline(d, chart_vs, CX1, CY1, cw_c, ch_c, PURPLE,   cmax)
    for i, lbl in enumerate(["J-14","","","","","","J-7","","","","","","","Auj"]):
        if lbl:
            px = CX1+int(i/13*cw_c)
            txt(d, (px,CY2+2), lbl, F(POPPINS_REG,10), fill=(*WHITE[:3],120), anchor="mt")
    txt(d, (W-PAD-8,H-12), "⚔ La Taverne Bot", F(LORA_ITALIC,12), fill=(*GOLD[:3],130), anchor="rb")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def make_stats_card(member, xp_data: dict) -> io.BytesIO:
    """
    Point d'entrée appelé par bot.py.
    - Télécharge l'avatar en async
    - Génère l'image dans run_in_executor (thread séparé)
      → évite le timeout Discord de 3 secondes
    """
    avatar_img = await fetch_avatar(str(member.display_avatar.url))
    joined  = member.joined_at.strftime("%d %b %Y") if member.joined_at else "?"
    created = member.created_at.strftime("%d %b %Y")
    level   = xp_data.get("level", 0)
    xp_max  = int(80 * (level + 1) ** 1.5)   # même formule que xp_needed()

    data = {
        "name":         member.display_name,
        "tag":          f"#{member.discriminator}" if member.discriminator != "0" else "",
        "server":       member.guild.name,
        "level":        level,
        "xp":           xp_data.get("xp", 0),
        "xp_max":       xp_max,
        "rank_msg":     xp_data.get("rank_msg",   "?"),
        "rank_voice":   xp_data.get("rank_voice", "?"),
        "total_members":member.guild.member_count,
        "msgs_1d":      xp_data.get("msgs_1d",  0),
        "msgs_7d":      xp_data.get("msgs_7d",  0),
        "msgs_14d":     xp_data.get("msgs_14d", 0),
        "voice_1d":     round(xp_data.get("voice_1d",  0), 1),
        "voice_7d":     round(xp_data.get("voice_7d",  0), 1),
        "voice_14d":    round(xp_data.get("voice_14d", 0), 1),
        "top_channel":  xp_data.get("top_channel", "—"),
        "top_voice":    xp_data.get("top_voice",   "—"),
        "joined":       joined,
        "created":      created,
        "chart_msgs":   xp_data.get("chart_msgs",  [0]*14),
        "chart_voice":  xp_data.get("chart_voice", [0]*14),
        "avatar_color": (100, 80, 200),
    }

    # ⚠️ CRUCIAL : thread séparé = event loop libre = pas de timeout Discord
    loop = asyncio.get_event_loop()
    buf  = await loop.run_in_executor(None, generate_stats_card, data, avatar_img)
    return buf
