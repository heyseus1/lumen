from __future__ import annotations

"""
Hue Control Portal (Lumen) — Auth0 login + a scope-constrained chat agent.

Routes:
  /                 dashboard (lit room grid + chat)        [requires login]
  /rooms/{id}       per-room detail (power, brightness, scenes)
  /login,/callback,/logout  -> Auth0 OIDC (web/auth.py)
  /api/*            room actions + chat (web/chat.py)
"""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
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

app = FastAPI(title="Lumen")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.WEB_SESSION_SECRET,
    same_site="lax",
    https_only=False,  # local-only for now
)

app.include_router(auth_module.router)
app.include_router(chat_module.router)


def _scenes(service, room_id):
    return [{"id": s.scene_id, "name": s.name} for s in service.list_scenes_for_room(room_id)]


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "mock_hue": settings.MOCK_HUE, "mock_llm": settings.MOCK_LLM}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    rooms = service.list_rooms()
    room_states = []
    for room in rooms:
        is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
        room_states.append({
            "id": room.room_id, "name": room.name,
            "on": is_on, "brightness": round(bri),
            "scenes": _scenes(service, room.room_id),
        })
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user_name": user.get("name", "you"),
            "room_count": len(rooms),
            "room_states": room_states,
            "agent_scopes": sorted(set(settings.AGENT_SCOPES.split())),
        },
    )


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    return templates.TemplateResponse(
        request,
        "audit.html",
        {
            "user_name": user.get("name", "you"),
            "room_count": len(service.list_rooms()),
        },
    )


@app.get("/rooms/{room_id}", response_class=HTMLResponse)
def room_detail(room_id: str, request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    rooms = service.list_rooms()
    room = next((r for r in rooms if r.room_id == room_id), None)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
    return templates.TemplateResponse(
        request,
        "room.html",
        {
            "user_name": user.get("name", "you"),
            "room_count": len(rooms),
            "room": {"id": room.room_id, "name": room.name},
            "is_on": is_on,
            "brightness": round(bri),
            "scenes": _scenes(service, room.room_id),
        },
    )
