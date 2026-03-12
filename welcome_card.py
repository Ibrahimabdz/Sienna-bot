"""
welcome_card.py — GIF animé bienvenue/au revoir style Taverne
"""
from PIL import Image, ImageDraw, ImageFont
import io, os, aiohttp, asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GIF_PATH = os.path.join(BASE_DIR, "welcome_bg.gif")

import os as _os
def _find_font(names):
    dirs = [
        r"C:\Windows\Fonts",
        _os.path.join(_os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts"),
        "/usr/share/fonts/truetype/google-fonts",
        "/usr/share/fonts/truetype/dejavu",
    ]
    for name in names:
        for d in dirs:
            path = _os.path.join(d, name)
            if _os.path.exists(path):
                return path
    return None

POPPINS_BOLD = _find_font(["Poppins-Bold.ttf",   "arialbd.ttf"]) or ""
POPPINS_MED  = _find_font(["Poppins-Medium.ttf",  "arial.ttf"])   or ""
LORA_ITALIC  = _find_font(["Lora-Italic-Variable.ttf", "georgiai.ttf"]) or ""
FALLBACK     = _find_font(["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"]) or ""

TARGET_W, TARGET_H = 960, 540
FLAG_CENTER_X = 195
FLAG_CENTER_Y = 285
AVATAR_SIZE   = 155
TEXT_X        = 390
FRAME_STEP    = 2

def F(path, size):
    from PIL import ImageFont
    for p in [path, POPPINS_BOLD, FALLBACK]:
        if p:
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

async def fetch_avatar_round(url: str, size: int = 155):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                if r.status != 200: return None
                data = await r.read()
        img  = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        out  = Image.new("RGBA", (size, size), (0,0,0,0))
        out.paste(img, mask=mask)
        return out
    except Exception:
        return None

def make_fallback_avatar(letter: str, size: int = 155):
    av = Image.new("RGBA", (size, size), (0,0,0,0))
    d  = ImageDraw.Draw(av)
    d.ellipse([0,0,size,size], fill=(100, 70, 190, 255))
    d.text((size//2, size//2), letter.upper(), font=F(POPPINS_BOLD, size//2), fill=(255,255,255,255), anchor="mm")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0,0,size,size], fill=255)
    out = Image.new("RGBA", (size, size), (0,0,0,0))
    out.paste(av, mask=mask)
    return out

def overlay_frame(frame: Image.Image, avatar: Image.Image, name: str, is_welcome: bool) -> Image.Image:
    W, H = frame.size
    img  = frame.convert("RGBA")
    draw = ImageDraw.Draw(img)

    AV = AVATAR_SIZE
    AX = FLAG_CENTER_X - AV // 2
    AY = FLAG_CENTER_Y - AV // 2

    shadow = Image.new("RGBA", (AV+20, AV+20), (0,0,0,0))
    ImageDraw.Draw(shadow).ellipse([4,4,AV+16,AV+16], fill=(0,0,0,90))
    img.paste(shadow, (AX-10, AY-10), shadow)

    av = avatar.resize((AV, AV), Image.LANCZOS)
    img.paste(av, (AX, AY), av)

    ring = Image.new("RGBA", (AV+12, AV+12), (0,0,0,0))
    rd   = ImageDraw.Draw(ring)
    rd.ellipse([0,0,AV+11,AV+11], outline=(255,210,80,240), width=4)
    rd.ellipse([4,4,AV+7,AV+7],   outline=(200,150,40,120), width=1)
    img.paste(ring, (AX-6, AY-6), ring)

    TX = TEXT_X

    def st(pos, text, font, fill, offset=2):
        draw.text((pos[0]+offset, pos[1]+offset), text, font=font, fill=(0,0,0,170))
        draw.text(pos, text, font=font, fill=fill)

    if is_welcome:
        TY = 145
        st((TX, TY-35), "★  ★  ★  ★  ★",           F(POPPINS_MED, 18), (255,210,80,200))
        st((TX, TY),    "⚔  BIENVENUE !",             F(POPPINS_BOLD,46), (255,220,60,255))
        st((TX, TY+62), f"dans la Taverne, {name} !", F(POPPINS_BOLD,28), (255,255,255,255))
        draw.line([(TX, TY+106),(TX+460, TY+106)], fill=(255,200,60,150), width=2)
        st((TX, TY+118), "✅  Accepte les règles du serveur", F(POPPINS_MED,19), (200,255,200,240))
        st((TX, TY+146), "🎭  Choisis tes rôles",             F(POPPINS_MED,19), (200,200,255,240))
        st((TX, TY+178), "✨  Que ton aventure commence...",   F(LORA_ITALIC,17), (255,190,60,220))
    else:
        TY = 160
        st((TX, TY-35), "🕯  🕯  🕯  🕯  🕯",                F(POPPINS_MED,18), (200,180,255,200))
        st((TX, TY),    "AU REVOIR...",                        F(POPPINS_BOLD,46), (200,180,255,255))
        st((TX, TY+62), f"{name} quitte la taverne",           F(POPPINS_BOLD,28), (255,255,255,255))
        draw.line([(TX, TY+106),(TX+460, TY+106)], fill=(200,160,255,150), width=2)
        st((TX, TY+118), "est reparti vers d'autres horizons.", F(POPPINS_MED,18), (200,200,220,240))
        st((TX, TY+152), "✨  On espère vous revoir bientôt...", F(LORA_ITALIC,17), (200,160,255,220))
        st((TX, TY+178), "     peut-être.",                      F(LORA_ITALIC,17), (200,160,255,220))

    return img

def build_gif(avatar: Image.Image, name: str, is_welcome: bool) -> io.BytesIO:
    gif       = Image.open(GIF_PATH)
    frames    = []
    durations = []
    try:
        for i in range(0, gif.n_frames, FRAME_STEP):
            gif.seek(i)
            frame  = gif.copy().convert("RGBA").resize((TARGET_W, TARGET_H), Image.LANCZOS)
            result = overlay_frame(frame, avatar, name, is_welcome)
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

async def make_welcome_gif(member, is_welcome: bool = True) -> io.BytesIO:
    avatar = await fetch_avatar_round(str(member.display_avatar.url), size=155)
    if avatar is None:
        avatar = make_fallback_avatar(member.display_name[0])
    loop = asyncio.get_event_loop()
    buf  = await loop.run_in_executor(None, build_gif, avatar, member.display_name, is_welcome)
    return buf
