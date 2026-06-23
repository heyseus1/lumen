from __future__ import annotations

"""Shared FastAPI dependencies."""

from fastapi import HTTPException, Request, status

from hue_async.core.config import get_settings


def get_current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        # Browsers get redirected to login; XHR/chat calls get a clean 401.
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": "/login"},
            )
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def get_room_service():
    """Return the real Hue-backed service, or a fake one for offline demos."""
    settings = get_settings()

    if settings.MOCK_HUE:
        from hue_async.agent.fake_service import FakeRoomService
        return FakeRoomService()

    from hue_async.clients.hue_client import HueClient
    from hue_async.services.room_service import RoomService

    if not settings.HUE_USERNAME:
        raise RuntimeError("HUE_USERNAME is missing in .env (or set MOCK_HUE=true)")

    client = HueClient(settings.HUE_BRIDGE_IP, settings.HUE_USERNAME)
    return RoomService(client)
