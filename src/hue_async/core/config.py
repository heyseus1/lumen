from __future__ import annotations

"""Application settings, loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Web / session ---
    WEB_SESSION_SECRET: str = "change-me"
    WEB_BASE_URL: str = "http://localhost:5000"

    # --- Auth0 OIDC ---
    AUTH0_DOMAIN: str = ""
    AUTH0_CLIENT_ID: str = ""
    AUTH0_CLIENT_SECRET: str = ""

    # --- Agent ---
    ANTHROPIC_API_KEY: str = ""
    AGENT_MODEL: str = "claude-sonnet-4-6"
    # Fallback grant, used only when no M2M credential is configured (offline/mock).
    # When the M2M identity below is set, the live grant comes from the token.
    AGENT_SCOPES: str = "lights:read lights:write scenes:write"

    # --- Agent non-human identity (Auth0 M2M) ---
    AGENT_API_AUDIENCE: str = ""
    AGENT_CLIENT_ID: str = ""
    AGENT_CLIENT_SECRET: str = ""

    # --- Hue (only needed when MOCK_HUE is false) ---
    HUE_BRIDGE_IP: str = ""
    HUE_USERNAME: str = ""
    HUE_CLIENTKEY: str = ""

    # --- Demo toggles ---
    MOCK_HUE: bool = True
    MOCK_LLM: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
