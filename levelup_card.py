"""
levelup_card.py — Génère un GIF animé de level-up
avec avatar sur le drapeau + texte à droite.
Place welcome_bg.gif dans le même dossier que bot.py
"""

from PIL import Image, ImageDraw, ImageFont
import io, os, aiohttp, asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GIF_PATH = os.path.join(BASE_DIR, "welcome_bg.gif")

import os as _os

def _find_font(names):
    win_dirs = [
        r"C:\Windows\Fonts",
        _os.path.join(_os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts"),
    ]
    linux_dirs = [
        "/usr/share/fonts/truetype/google-fonts",
        "/usr/share/fonts/truetype/dejavu",
    ]
    for name in names:
        for d in win_dirs + linux_dirs:
            path = _os.path.join(d, name)
            if _os.path.exists(path):
                return path
    return None

POPPINS_BOLD = _find_font(["Poppins-Bold.ttf",   "arialbd.ttf"]) or ""
POPPINS_MED  = _find_font(["Poppins-Medium.ttf",  "arial.ttf"])   or ""
LORA_ITALIC  = _find_font(["Lora-Italic-Variable.ttf", "georgiai.ttf"]) or ""
FALLBACK     = _find_font(["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"]) or ""

def F(path, size):
    from PIL import ImageFont
    for p in [path, POPPINS_BOLD, FALLBACK]:
        if p:
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

TARGET_W, TARGET_H = 960, 540
FLAG_CENTER_X = 195
FLAG_CENTER_Y = 285
AVATAR_SIZE   = 155
TEXT_X        = 390
TEXT_Y        = 130
FRAME_STEP    = 2


async def fetch_avatar_round(url: str, size: int = 155) -> Image.Image | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                data = await r.read()
        img  = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        return out
    except Exception:
        return None


def make_fallback_avatar(letter: str, size: int = 155) -> Image.Image:
    av = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d  = ImageDraw.Draw(av)
    d.ellipse([0, 0, size, size], fill=(80, 160, 120, 255))
    d.text((size//2, size//2), letter.upper(), font=F(POPPINS_BOLD, size//2),
           fill=(255, 255, 255, 255), anchor="mm")
    return av


def overlay_levelup(frame: Image.Image, avatar: Image.Image,
                    name: str, level: int, xp: int, xp_max: int) -> Image.Image:
    W, H = frame.size
    img  = frame.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # ── Avatar centré sur le drapeau ──────────────────────
    AV = AVATAR_SIZE
    AX = FLAG_CENTER_X - AV // 2
    AY = FLAG_CENTER_Y - AV // 2

    # Ombre
    shadow = Image.new("RGBA", (AV+20, AV+20), (0,0,0,0))
    ImageDraw.Draw(shadow).ellipse([4,4,AV+16,AV+16], fill=(0,0,0,90))
    img.paste(shadow, (AX-10, AY-10), shadow)

    # Avatar
    av = avatar.resize((AV, AV), Image.LANCZOS)
    img.paste(av, (AX, AY), av)

    # Anneau doré
    ring = Image.new("RGBA", (AV+12, AV+12), (0,0,0,0))
    rd   = ImageDraw.Draw(ring)
    rd.ellipse([0,0,AV+11,AV+11], outline=(255,210,80,240), width=4)
    rd.ellipse([4,4,AV+7,AV+7],   outline=(200,150,40,120), width=1)
    img.paste(ring, (AX-6, AY-6), ring)

    # Badge niveau (coin bas droite de l'avatar)
    br  = 28
    bx  = AX + AV - br
    by  = AY + AV - br
    draw.ellipse([bx-br, by-br, bx+br, by+br], fill=(255,200,40,255))
    draw.ellipse([bx-br, by-br, bx+br, by+br], outline=(255,255,255,200), width=2)
    draw.text((bx, by), str(level), font=F(POPPINS_BOLD, 22),
              fill=(20,10,40,255), anchor="mm")

    # ── Texte à droite ────────────────────────────────────
    TX, TY = TEXT_X, TEXT_Y

    def st(pos, text, font, fill, offset=2):
        """Texte avec ombre portée pour lisibilité."""
        draw.text((pos[0]+offset, pos[1]+offset), text, font=font, fill=(0,0,0,170))
        draw.text(pos, text, font=font, fill=fill)

    # Étoiles déco
    st((TX, TY-35), "★  ★  ★  ★  ★", F(POPPINS_MED, 18), (255, 210, 80, 200))

    # Titre
    st((TX, TY),    "⬆  LEVEL UP !",
       F(POPPINS_BOLD, 46), (255, 220, 60, 255))

    # Félicitations + nom
    st((TX, TY+62), f"Félicitations, {name} !",
       F(POPPINS_BOLD, 30), (255, 255, 255, 255))

    # Niveau
    st((TX, TY+104), f"Tu atteins le niveau  {level} !",
       F(POPPINS_MED, 24), (200, 180, 255, 255))

    # Séparateur
    draw.line([(TX, TY+142),(TX+460, TY+142)], fill=(255,200,60,150), width=2)

    # Barre XP
    bx1, by1 = TX, TY+158
    bw, bh   = 460, 18
    xp_pct   = min(xp / max(xp_max, 1), 1.0)
    draw.rounded_rectangle([bx1, by1, bx1+bw, by1+bh], radius=9, fill=(20,10,40,200))
    filled = int(bw * xp_pct)
    if filled > 0:
        for i in range(filled):
            t  = i / max(filled, 1)
            draw.line([(bx1+i, by1+1),(bx1+i, by1+bh-1)],
                      fill=(int(80+140*t), int(180+40*t), int(255-80*t), 220))
    draw.rounded_rectangle([bx1, by1, bx1+bw, by1+bh],
                            radius=9, outline=(255,200,60,120), width=1)
    st((bx1, by1+bh+6), f"XP : {xp:,} / {xp_max:,}",
       F(POPPINS_MED, 14), (200, 200, 255, 220))

    # Message bas
    st((TX, TY+210), "✨  Continue comme ça, aventurier !",
       F(LORA_ITALIC, 16), (255, 190, 60, 210))

    return img


def build_levelup_gif(avatar: Image.Image, name: str,
                      level: int, xp: int, xp_max: int) -> io.BytesIO:
    gif       = Image.open(GIF_PATH)
    frames    = []
    durations = []
    try:
        for i in range(0, gif.n_frames, FRAME_STEP):
            gif.seek(i)
            frame  = gif.copy().convert("RGBA").resize((TARGET_W, TARGET_H), Image.LANCZOS)
            result = overlay_levelup(frame, avatar, name, level, xp, xp_max)
            p      = result.quantize(colors=100, method=Image.Quantize.FASTOCTREE)
            frames.append(p)
            durations.append(gif.info.get("duration", 50) * FRAME_STEP)
    except EOFError:
        pass

    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   loop=0, duration=durations, optimize=True)
    buf.seek(0)
    return buf


async def make_levelup_gif(member, level: int, xp: int, xp_max: int) -> io.BytesIO:
    """Fonction principale appelée depuis bot.py"""
    avatar = await fetch_avatar_round(str(member.display_avatar.url), size=155)
    if avatar is None:
        avatar = make_fallback_avatar(member.display_name[0])

    loop = asyncio.get_event_loop()
    buf  = await loop.run_in_executor(
        None, build_levelup_gif, avatar, member.display_name, level, xp, xp_max
    )
    return buf
