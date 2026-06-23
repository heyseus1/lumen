from __future__ import annotations

"""
The agent's tools. Each tool declares the scope it requires. The runner only
exposes tools the agent is *granted*, and the dispatcher re-checks the scope at
execution time — defense in depth, so the model can never exceed its grant even
if it hallucinates a call.

Tool -> required scope:
  list_rooms          lights:read
  set_power           lights:write
  set_brightness      lights:write
  activate_scene      scenes:write
  delete_scene        bridge:admin   (deliberately withheld by default)
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


def _find_room(service, name: str):
    name = (name or "").strip().lower()
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


def _list_rooms(service, args):
    out = []
    for room in service.list_rooms():
        is_on, bri = service.get_grouped_light_state(room.grouped_light_id)
        out.append({"room": room.name, "on": is_on, "brightness": round(bri)})
    return {"ok": True, "detail": out}


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
    level = max(0.0, min(100.0, float(args.get("level", 50))))
    service.set_room_brightness(room.grouped_light_id, level)
    return {"ok": True, "detail": f"{room.name} set to {round(level)}%",
            "action": {"type": "brightness", "room": room.name, "level": level}}


def _activate_scene(service, args):
    room = _find_room(service, args.get("room", ""))
    if not room:
        return {"ok": False, "detail": f"no room matching '{args.get('room')}'"}
    scene = _find_scene(service, room, args.get("scene", ""))
    if not scene:
        return {"ok": False, "detail": f"no scene matching '{args.get('scene')}' in {room.name}"}
    service.activate_scene(scene.scene_id)
    return {"ok": True, "detail": f"activated '{scene.name}' in {room.name}",
            "action": {"type": "scene", "room": room.name, "scene": scene.name}}


def _delete_scene(service, args):
    # Real implementation would DELETE the scene resource. Left as a stub because
    # it sits behind bridge:admin and is the "agent can't do this" demo.
    return {"ok": True, "detail": f"deleted scene '{args.get('scene')}'"}


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
            name="set_power",
            description="Turn a room's lights on or off.",
            input_schema={
                "type": "object",
                "properties": {
                    "room": {"type": "string", "description": "Room name, e.g. 'studio'"},
                    "on": {"type": "boolean"},
                },
                "required": ["room", "on"],
            },
            required_scope="lights:write",
            handler=_set_power,
        ),
        Tool(
            name="set_brightness",
            description="Set a room's brightness to a percentage (0-100).",
            input_schema={
                "type": "object",
                "properties": {
                    "room": {"type": "string"},
                    "level": {"type": "number", "description": "0 to 100"},
                },
                "required": ["room", "level"],
            },
            required_scope="lights:write",
            handler=_set_brightness,
        ),
        Tool(
            name="activate_scene",
            description="Activate a named scene in a room (e.g. 'Deep House').",
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
        Tool(
            name="delete_scene",
            description="Permanently delete a scene from the bridge.",
            input_schema={
                "type": "object",
                "properties": {
                    "room": {"type": "string"},
                    "scene": {"type": "string"},
                },
                "required": ["room", "scene"],
            },
            required_scope="bridge:admin",
            handler=_delete_scene,
        ),
    ]


def granted_tools(granted_scopes: set[str]) -> list[Tool]:
    return [t for t in all_tools() if t.required_scope in granted_scopes]
