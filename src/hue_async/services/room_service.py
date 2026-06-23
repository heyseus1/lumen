from __future__ import annotations

"""
RoomService: business logic over the Hue v2 API.

Maps the bridge's resource model (rooms, grouped_light, scenes) to the simple
operations the web layer and the agent call. Brightness is expressed 0-100.
"""

from dataclasses import dataclass

from hue_async.clients.hue_client import HueClient


@dataclass
class Room:
    room_id: str
    grouped_light_id: str
    name: str


@dataclass
class Scene:
    scene_id: str
    name: str
    room_id: str


class RoomService:
    def __init__(self, client: HueClient) -> None:
        self.client = client

    def list_rooms(self) -> list[Room]:
        data = self.client.get("/clip/v2/resource/room").get("data", [])
        rooms: list[Room] = []
        for r in data:
            grouped_light_id = ""
            for svc in r.get("services", []):
                if svc.get("rtype") == "grouped_light":
                    grouped_light_id = svc.get("rid", "")
                    break
            name = r.get("metadata", {}).get("name", r["id"])
            rooms.append(Room(room_id=r["id"], grouped_light_id=grouped_light_id, name=name))
        return rooms

    def get_grouped_light_state(self, grouped_light_id: str) -> tuple[bool, float]:
        if not grouped_light_id:
            return False, 0.0
        data = self.client.get(f"/clip/v2/resource/grouped_light/{grouped_light_id}").get("data", [])
        if not data:
            return False, 0.0
        gl = data[0]
        is_on = gl.get("on", {}).get("on", False)
        brightness = gl.get("dimming", {}).get("brightness", 0.0)
        return is_on, float(brightness)

    def set_room_power(self, grouped_light_id: str, on: bool) -> None:
        self.client.put(f"/clip/v2/resource/grouped_light/{grouped_light_id}", {"on": {"on": on}})

    def set_room_brightness(self, grouped_light_id: str, brightness: float) -> None:
        brightness = max(0.0, min(100.0, float(brightness)))
        self.client.put(
            f"/clip/v2/resource/grouped_light/{grouped_light_id}",
            {"dimming": {"brightness": brightness}},
        )

    def list_scenes_for_room(self, room_id: str) -> list[Scene]:
        data = self.client.get("/clip/v2/resource/scene").get("data", [])
        scenes: list[Scene] = []
        for s in data:
            group = s.get("group", {})
            if group.get("rtype") == "room" and group.get("rid") == room_id:
                scenes.append(
                    Scene(
                        scene_id=s["id"],
                        name=s.get("metadata", {}).get("name", s["id"]),
                        room_id=room_id,
                    )
                )
        return scenes

    def activate_scene(self, scene_id: str) -> None:
        self.client.put(f"/clip/v2/resource/scene/{scene_id}", {"recall": {"action": "active"}})
