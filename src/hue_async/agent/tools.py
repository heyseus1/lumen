from __future__ import annotations

"""
The agent's tools — this list IS the agent's capability boundary.

Approved capabilities only:
  list_rooms      lights:read    metrics for all rooms (power + brightness)
  room_status     lights:read    metrics for one room
  list_scenes     lights:read    scenes available in a room (read-only)
  set_power       lights:write   turn a room on/off
  set_brightness  lights:write   set a room's brightness 1-100
  activate_scene  scenes:write   recall an EXISTING scene

There is deliberately no create/delete tool. Scene authoring stays in the Hue
app; the agent can only recall what already exists. "Manage existing, never
author" is enforced structurally — the model cannot call a tool that isn't here.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    required_scope: str
    handler: Callable[[Any, dict], dict]


# --- resolvers ---------------------------------------------------------------
def _find_room(service, name: str):
    name = (name or "").strip().lower()
    if not name:
        return None
    for room in service.list_rooms():
        if name in room.name.lower() or name == room.room_id.lower():
            return room
    return None


def _find_scene(service, room, name: str):
    name = (name or "").strip().lower()
    for scene in service.list_scenes_for_room(room.room_id):
        if name in scene.name.lower():
            return scene
    return None


# --- handlers ----------------------------------------------------------------
def _list_rooms(service, args):
    out = []
    for room in service.list_rooms():
        is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
        out.append({"room": room.name, "on": is_on, "brightness": round(bri)})
    return {"ok": True, "detail": out}


def _room_status(service, args):
    room = _find_room(service, args.get("room", ""))
    if not room:
        return {"ok": False, "detail": f"no room matching '{args.get('room')}'"}
    is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
    return {"ok": True, "detail": {"room": room.name, "on": is_on, "brightness": round(bri)}}


def _list_scenes(service, args):
    room = _find_room(service, args.get("room", ""))
    if not room:
        return {"ok": False, "detail": f"no room matching '{args.get('room')}'"}
    scenes = [s.name for s in service.list_scenes_for_room(room.room_id)]
    return {"ok": True, "detail": {"room": room.name, "scenes": scenes}}


def _set_power(service, args):
    room = _find_room(service, args.get("room", ""))
    if not room:
        return {"ok": False, "detail": f"no room matching '{args.get('room')}'"}
    on = bool(args.get("on"))
    service.set_room_power(room.grouped_light_id, on)
    return {"ok": True, "detail": f"{room.name} turned {'on' if on else 'off'}",
            "action": {"type": "power", "room": room.name, "on": on}}


def _set_brightness(service, args):
    room = _find_room(service, args.get("room", ""))
    if not room:
        return {"ok": False, "detail": f"no room matching '{args.get('room')}'"}
    level = max(1.0, min(100.0, float(args.get("level", 50))))
    service.set_room_brightness(room.grouped_light_id, level)
    return {"ok": True, "detail": f"{room.name} set to {round(level)}%",
            "action": {"type": "brightness", "room": room.name, "level": level}}


def _activate_scene(service, args):
    room = _find_room(service, args.get("room", ""))
    if not room:
        return {"ok": False, "detail": f"no room matching '{args.get('room')}'"}
    scene = _find_scene(service, room, args.get("scene", ""))
    if not scene:
        avail = [s.name for s in service.list_scenes_for_room(room.room_id)]
        return {"ok": False,
                "detail": f"no scene matching '{args.get('scene')}' in {room.name}. available: {avail}"}
    service.activate_scene(scene.scene_id)
    return {"ok": True, "detail": f"activated '{scene.name}' in {room.name}",
            "action": {"type": "scene", "room": room.name, "scene": scene.name}}


# --- registry ----------------------------------------------------------------
def all_tools() -> list[Tool]:
    return [
        Tool(
            name="list_rooms",
            description="List all rooms with their on/off state and brightness.",
            input_schema={"type": "object", "properties": {}},
            required_scope="lights:read",
            handler=_list_rooms,
        ),
        Tool(
            name="room_status",
            description="Get the current power state and brightness of one room.",
            input_schema={
                "type": "object",
                "properties": {"room": {"type": "string"}},
                "required": ["room"],
            },
            required_scope="lights:read",
            handler=_room_status,
        ),
        Tool(
            name="list_scenes",
            description="List the scenes available in a room (read-only).",
            input_schema={
                "type": "object",
                "properties": {"room": {"type": "string"}},
                "required": ["room"],
            },
            required_scope="lights:read",
            handler=_list_scenes,
        ),
        Tool(
            name="set_power",
            description="Turn a room's lights on or off.",
            input_schema={
                "type": "object",
                "properties": {
                    "room": {"type": "string"},
                    "on": {"type": "boolean"},
                },
                "required": ["room", "on"],
            },
            required_scope="lights:write",
            handler=_set_power,
        ),
        Tool(
            name="set_brightness",
            description="Set a room's brightness to a percentage (1-100).",
            input_schema={
                "type": "object",
                "properties": {
                    "room": {"type": "string"},
                    "level": {"type": "number", "description": "1 to 100"},
                },
                "required": ["room", "level"],
            },
            required_scope="lights:write",
            handler=_set_brightness,
        ),
        Tool(
            name="activate_scene",
            description="Activate an existing named scene in a room. Cannot create scenes.",
            input_schema={
                "type": "object",
                "properties": {
                    "room": {"type": "string"},
                    "scene": {"type": "string"},
                },
                "required": ["room", "scene"],
            },
            required_scope="scenes:write",
            handler=_activate_scene,
        ),
    ]


def granted_tools(granted_scopes: set[str]) -> list[Tool]:
    return [t for t in all_tools() if t.required_scope in granted_scopes]