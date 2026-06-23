from __future__ import annotations

"""A drop-in stand-in for RoomService so the dashboard + agent run with no bridge.

Mirrors the methods app.py / the agent call on the real service. Flip MOCK_HUE
to false in .env to use the real HueClient/RoomService instead.
"""

from dataclasses import dataclass


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


class FakeRoomService:
    def __init__(self) -> None:
        self._rooms = {
            "studio": Room("studio", "gl-studio", "Studio"),
            "kitchen": Room("kitchen", "gl-kitchen", "Kitchen"),
            "bedroom": Room("bedroom", "gl-bedroom", "Bedroom"),
        }
        # grouped_light_id -> (is_on, brightness 0..100)
        self._state = {
            "gl-studio": [True, 80.0],
            "gl-kitchen": [False, 50.0],
            "gl-bedroom": [False, 30.0],
        }
        self._scenes = [
            Scene("scene-deep-house", "Deep House", "studio"),
            Scene("scene-focus", "Focus", "studio"),
            Scene("scene-dinner", "Dinner", "kitchen"),
        ]

    def list_rooms(self) -> list[Room]:
        return list(self._rooms.values())

    def get_grouped_light_state(self, grouped_light_id: str):
        s = self._state.get(grouped_light_id, [False, 0.0])
        return s[0], s[1]

    def set_room_power(self, grouped_light_id: str, on: bool) -> None:
        self._state.setdefault(grouped_light_id, [False, 50.0])[0] = on

    def set_room_brightness(self, grouped_light_id: str, brightness: float) -> None:
        s = self._state.setdefault(grouped_light_id, [True, 50.0])
        s[1] = max(0.0, min(100.0, brightness))
        if brightness > 0:
            s[0] = True

    def list_scenes_for_room(self, room_id: str) -> list[Scene]:
        return [s for s in self._scenes if s.room_id == room_id]

    def activate_scene(self, scene_id: str) -> None:
        # No-op for the fake; a real bridge would push the scene.
        return None
