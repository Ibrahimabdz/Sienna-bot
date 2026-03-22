import asyncio
import os
import re
import time
import uuid
from html import unescape

from aiohttp import web
from akinator.async_client import AsyncAkinator, AsyncCloudScraper, THEME_IDS


HOST = os.getenv("AKINATOR_SERVICE_HOST", "0.0.0.0")
PORT = int(os.getenv("AKINATOR_SERVICE_PORT", "8080"))
AUTH_TOKEN = os.getenv("AKINATOR_SERVICE_TOKEN", "")
SESSION_TTL_SECONDS = int(os.getenv("AKINATOR_SERVICE_SESSION_TTL", "1800"))

SESSIONS: dict[str, dict] = {}


def _make_akinator_client(browser_platform: str | None = None) -> AsyncAkinator:
    browser_platform = browser_platform or os.getenv(
        "AKINATOR_BROWSER_PLATFORM",
        "windows" if os.name == "nt" else "linux",
    )
    if browser_platform == "linux":
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        )
    else:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        )
    session = AsyncCloudScraper(
        browser={"browser": "chrome", "platform": browser_platform, "desktop": True}
    )
    scraper = getattr(session, "scraper", None)
    if scraper:
        scraper.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )
    return AsyncAkinator(session=session)


def _reset_akinator_state(aki: AsyncAkinator):
    aki.progression = 0
    aki.step = 0
    aki.akitude = "defi.png"
    aki.finished = False
    aki.win = False
    aki.step_last_proposition = ""
    aki.id_proposition = None
    aki.name_proposition = None
    aki.description_proposition = None
    aki.flag_photo = None
    aki.photo = None


def _extract_akinator_value(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.S)
        if match:
            return unescape(match.group(1)).strip()
    return ""


async def _akinator_post(aki: AsyncAkinator, endpoint: str, data: dict, *, allow_redirects: bool = False):
    response = await aki.session.post(
        f"https://{aki.language}.akinator.com/{endpoint}",
        data=data,
        allow_redirects=allow_redirects,
    )
    response.raise_for_status()
    return response


async def _start_akinator_game(aki: AsyncAkinator, theme: str, *, child_mode: bool = False):
    errors: list[str] = []

    async def _start_native(target: AsyncAkinator, language: str):
        await asyncio.wait_for(
            target.start_game(language=language, child_mode=child_mode, theme=theme),
            timeout=20,
        )
        _reset_akinator_state(target)

    async def _start_legacy(target: AsyncAkinator, language: str):
        target.theme = theme
        target.language = language
        target.child_mode = child_mode
        headers = {
            "Origin": f"https://{language}.akinator.com",
            "Referer": f"https://{language}.akinator.com/",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        scraper = getattr(target.session, "scraper", None)
        if scraper:
            scraper.headers.update(headers)
            await asyncio.to_thread(
                scraper.get,
                f"https://{language}.akinator.com/",
                headers=headers,
                timeout=20,
                allow_redirects=True,
            )
        response = await target.session.post(
            f"https://{language}.akinator.com/game",
            data={"sid": THEME_IDS[theme], "cm": str(child_mode).lower()},
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        text = response.text

        target.session_id = _extract_akinator_value([r"#session'\)\.val\('(.+?)'\)"], text)
        target.signature = _extract_akinator_value([r"#signature'\)\.val\('(.+?)'\)"], text)
        target.identifiant = _extract_akinator_value([r"#identifiant'\)\.val\('(.+?)'\)"], text)
        target.question = _extract_akinator_value(
            [
                r'<p class="question-text" id="question-label">(.+?)</p>',
                r'<div class="bubble-body">\s*<p[^>]*id="question-label"[^>]*>(.+?)</p>',
            ],
            text,
        )
        if not all([target.session_id, target.signature, target.identifiant, target.question]):
            raise RuntimeError("Réponse de démarrage incomplète")
        target.proposition = _extract_akinator_value([r'<p id="p-sub-bubble">(.+?)</p>'], text)
        _reset_akinator_state(target)

    platform_order = [os.getenv("AKINATOR_BROWSER_PLATFORM", "windows" if os.name == "nt" else "linux")]
    alternate_platform = "linux" if platform_order[0] == "windows" else "windows"
    if alternate_platform not in platform_order:
        platform_order.append(alternate_platform)

    for browser_platform in platform_order:
        for language in ("fr", "en"):
            for strategy_name, strategy in (("native", _start_native), ("legacy", _start_legacy)):
                try:
                    fresh_client = _make_akinator_client(browser_platform)
                    aki.session = fresh_client.session
                    await strategy(aki, language)
                    print(f"ℹ️ Akinator service startup OK via {strategy_name} ({browser_platform}/{language})")
                    return
                except Exception as exc:
                    errors.append(f"{strategy_name}:{browser_platform}:{language}:{exc!r}")
                    await asyncio.sleep(0.5)
    raise RuntimeError(" ; ".join(errors) or "Échec du démarrage Akinator")


def _akinator_apply_payload(aki: AsyncAkinator, payload: dict):
    aki.completion = payload.get("completion", getattr(aki, "completion", None))
    if aki.completion == "KO - TIMEOUT":
        raise RuntimeError("La session Akinator a expiré.")

    if "id_proposition" in payload:
        aki.win = True
        aki.finished = False
        aki.id_proposition = payload.get("id_proposition")
        aki.name_proposition = payload.get("name_proposition", "Inconnu")
        aki.description_proposition = payload.get("description_proposition", "")
        aki.pseudo = payload.get("pseudo")
        aki.flag_photo = payload.get("flag_photo")
        aki.photo = payload.get("photo")
        if "step" in payload:
            aki.step = int(float(payload["step"]))
        if "progression" in payload:
            aki.progression = float(payload["progression"])
        return

    aki.win = False
    aki.finished = False
    aki.id_proposition = None
    aki.name_proposition = None
    aki.description_proposition = None
    aki.flag_photo = None
    aki.photo = None
    if "step" in payload:
        aki.step = int(float(payload["step"]))
    if "progression" in payload:
        aki.progression = float(payload["progression"])
    if "question" in payload:
        aki.question = payload["question"]
    if "akitude" in payload:
        aki.akitude = payload["akitude"]


async def _akinator_answer(aki: AsyncAkinator, answer: str):
    if aki.win:
        if answer == "yes":
            await _akinator_post(
                aki,
                "choice",
                {
                    "step": aki.step,
                    "sid": THEME_IDS[aki.theme],
                    "session": aki.session_id,
                    "signature": aki.signature,
                    "identifiant": aki.identifiant,
                    "pid": aki.id_proposition,
                    "charac_name": aki.name_proposition,
                    "charac_description": aki.description_proposition,
                    "pflag_photo": aki.flag_photo or "",
                },
                allow_redirects=True,
            )
            aki.finished = True
            aki.win = True
            aki.progression = 100
            return
        if answer == "no":
            await _akinator_back(aki)
            return
        raise ValueError("Après une proposition, réponds seulement par oui ou non.")

    answer_map = {
        "yes": 0,
        "no": 1,
        "idk": 2,
        "probably": 3,
        "probably_not": 4,
    }
    if answer not in answer_map:
        raise ValueError("Réponse Akinator invalide.")

    response = await _akinator_post(
        aki,
        "answer",
        {
            "step": aki.step,
            "progression": aki.progression,
            "sid": THEME_IDS[aki.theme],
            "cm": str(aki.child_mode).lower(),
            "answer": answer_map[answer],
            "step_last_proposition": getattr(aki, "step_last_proposition", ""),
            "session": aki.session_id,
            "signature": aki.signature,
        },
    )
    _akinator_apply_payload(aki, response.json())


async def _akinator_back(aki: AsyncAkinator):
    if int(getattr(aki, "step", 0) or 0) <= 0:
        raise ValueError("Tu es déjà à la première question.")
    aki.win = False
    response = await _akinator_post(
        aki,
        "cancel_answer",
        {
            "step": aki.step,
            "progression": aki.progression,
            "sid": THEME_IDS[aki.theme],
            "cm": str(aki.child_mode).lower(),
            "session": aki.session_id,
            "signature": aki.signature,
        },
    )
    _akinator_apply_payload(aki, response.json())


def _serialize_aki(session_id: str, aki: AsyncAkinator) -> dict:
    return {
        "session_id": session_id,
        "state": {
            "theme": getattr(aki, "theme", "c"),
            "question": getattr(aki, "question", ""),
            "progression": float(getattr(aki, "progression", 0) or 0),
            "step": int(getattr(aki, "step", 0) or 0),
            "akitude": getattr(aki, "akitude", "defi.png"),
            "win": bool(getattr(aki, "win", False)),
            "finished": bool(getattr(aki, "finished", False)),
            "child_mode": bool(getattr(aki, "child_mode", False)),
            "name_proposition": getattr(aki, "name_proposition", None),
            "description_proposition": getattr(aki, "description_proposition", None),
            "flag_photo": getattr(aki, "flag_photo", None),
            "photo": getattr(aki, "photo", None),
        },
    }


async def _close_aki(aki: AsyncAkinator):
    close_method = getattr(getattr(aki, "session", None), "close", None)
    if not close_method:
        return
    maybe_coro = close_method()
    if asyncio.iscoroutine(maybe_coro):
        await maybe_coro


async def _purge_stale_sessions():
    now = time.time()
    stale_ids = [
        session_id
        for session_id, session in SESSIONS.items()
        if now - float(session.get("updated_at", 0)) >= SESSION_TTL_SECONDS
    ]
    for session_id in stale_ids:
        session = SESSIONS.pop(session_id, None)
        if session:
            try:
                await _close_aki(session["aki"])
            except Exception:
                pass


async def _require_auth(request: web.Request):
    await _purge_stale_sessions()
    if not AUTH_TOKEN:
        return
    header = request.headers.get("Authorization", "")
    if header != f"Bearer {AUTH_TOKEN}":
        raise web.HTTPUnauthorized(text="Unauthorized")


async def health(request: web.Request):
    return web.json_response({"ok": True, "sessions": len(SESSIONS)})


async def start(request: web.Request):
    await _require_auth(request)
    payload = await request.json()
    theme = payload.get("theme", "c")
    child_mode = bool(payload.get("child_mode", False))

    aki = _make_akinator_client()
    await _start_akinator_game(aki, theme, child_mode=child_mode)
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {"aki": aki, "updated_at": time.time()}
    return web.json_response(_serialize_aki(session_id, aki))


def _get_session_or_404(session_id: str) -> dict:
    session = SESSIONS.get(session_id)
    if not session:
        raise web.HTTPNotFound(text="Unknown session")
    session["updated_at"] = time.time()
    return session


async def answer(request: web.Request):
    await _require_auth(request)
    payload = await request.json()
    session_id = str(payload.get("session_id") or "").strip()
    answer_value = str(payload.get("answer") or "").strip()
    session = _get_session_or_404(session_id)
    await _akinator_answer(session["aki"], answer_value)
    return web.json_response(_serialize_aki(session_id, session["aki"]))


async def back(request: web.Request):
    await _require_auth(request)
    payload = await request.json()
    session_id = str(payload.get("session_id") or "").strip()
    session = _get_session_or_404(session_id)
    await _akinator_back(session["aki"])
    return web.json_response(_serialize_aki(session_id, session["aki"]))


async def close(request: web.Request):
    await _require_auth(request)
    payload = await request.json()
    session_id = str(payload.get("session_id") or "").strip()
    session = SESSIONS.pop(session_id, None)
    if session:
        await _close_aki(session["aki"])
    return web.json_response({"ok": True})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/start", start)
    app.router.add_post("/answer", answer)
    app.router.add_post("/back", back)
    app.router.add_post("/close", close)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=HOST, port=PORT)
