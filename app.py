from __future__ import annotations

"""
Hue Control Portal — now with Auth0 login and a scope-constrained chat agent.

Routes:
  /            dashboard (room cards + chat)   [requires login]
  /login,/callback,/logout  -> Auth0 OIDC (web/auth.py)
  /api/chat, /api/rooms/*   -> agent + actions (web/chat.py)
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from hue_async.core.config import get_settings
from hue_async.web import auth as auth_module
from hue_async.web import chat as chat_module
from hue_async.web.deps import get_current_user, get_room_service

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

settings = get_settings()

app = FastAPI(title="Hue Control Portal")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.WEB_SESSION_SECRET,
    same_site="lax",
    https_only=False,  # local-only for now
)

app.include_router(auth_module.router)
app.include_router(chat_module.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "mock_hue": settings.MOCK_HUE, "mock_llm": settings.MOCK_LLM}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    room_states = []
    for room in service.list_rooms():
        is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
        room_states.append({"room": room, "is_on": is_on, "brightness": round(bri)})

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "room_states": room_states,
            "agent_scopes": sorted(set(settings.AGENT_SCOPES.split())),
        },
    )
