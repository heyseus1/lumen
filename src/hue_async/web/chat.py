from __future__ import annotations

"""Chat endpoint (the agent), JSON room actions for the dashboard, and the
audit feed. Every privileged action — human click or agent tool call — is
recorded through hue_async.core.audit."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from hue_async.agent.identity import get_agent_identity
from hue_async.agent.runner import run_agent
from hue_async.core.audit import recent as audit_recent
from hue_async.core.audit import record as audit
from hue_async.core.config import get_settings
from hue_async.web.deps import get_current_user, get_room_service

router = APIRouter()
settings = get_settings()


def _granted_scopes() -> set[str]:
    # The agent's authority is whatever its Auth0 M2M token grants (validated
    # offline). Falls back to the config string only when no credential is set.
    return get_agent_identity().scopes()


def _who(user: dict) -> str:
    return f"human:{user.get('sub', '?')}"


def _room_states(service) -> list[dict]:
    out = []
    for room in service.list_rooms():
        is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
        out.append({"room_id": room.room_id, "name": room.name,
                    "on": is_on, "brightness": round(bri)})
    return out


@router.get("/api/rooms")
def api_rooms(user: dict = Depends(get_current_user)):
    return {"rooms": _room_states(get_room_service())}


@router.post("/api/rooms/{room_id}/power")
async def api_power(room_id: str, request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    room = next((r for r in service.list_rooms() if r.room_id == room_id), None)
    if not room:
        raise HTTPException(404, "room not found")
    body = await request.json()
    on = bool(body.get("on"))
    service.set_room_power(room.grouped_light_id, on)
    audit(_who(user), "set_power", "allowed", target=room.name, scope_basis="human-session")
    return {"ok": True}


@router.post("/api/rooms/{room_id}/brightness")
async def api_brightness(room_id: str, request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    room = next((r for r in service.list_rooms() if r.room_id == room_id), None)
    if not room:
        raise HTTPException(404, "room not found")
    body = await request.json()
    level = max(0.0, min(100.0, float(body.get("level", 50))))
    service.set_room_brightness(room.grouped_light_id, level)
    audit(_who(user), "set_brightness", "allowed", target=f"{room.name} {round(level)}%",
          scope_basis="human-session")
    return {"ok": True}


@router.get("/api/rooms/{room_id}/scenes")
def api_scenes(room_id: str, user: dict = Depends(get_current_user)):
    service = get_room_service()
    scenes = service.list_scenes_for_room(room_id)
    return {"scenes": [{"id": s.scene_id, "name": s.name} for s in scenes]}


@router.post("/api/rooms/{room_id}/scene")
async def api_activate_scene(room_id: str, request: Request, user: dict = Depends(get_current_user)):
    service = get_room_service()
    room = next((r for r in service.list_rooms() if r.room_id == room_id), None)
    if not room:
        raise HTTPException(404, "room not found")
    body = await request.json()
    scene_id = body.get("scene_id")
    if not scene_id:
        raise HTTPException(400, "scene_id required")
    service.activate_scene(scene_id)
    audit(_who(user), "activate_scene", "allowed", target=room.name, scope_basis="human-session")
    return {"ok": True}


@router.get("/api/audit")
def api_audit(user: dict = Depends(get_current_user)):
    return {"entries": audit_recent(120)}


@router.post("/api/chat")
async def api_chat(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "empty message")
    cid = uuid.uuid4().hex[:6]
    audit(_who(user), "chat.message", "allowed", target=message[:70], cid=cid)
    service = get_room_service()
    granted = _granted_scopes()
    result = run_agent(message, service, granted, settings, cid=cid)
    result["rooms"] = _room_states(service)   # so the UI can refresh after actions
    result["agent_scopes"] = sorted(granted)
    return result
