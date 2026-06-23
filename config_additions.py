from __future__ import annotations

"""
NOT a standalone module — these are the fields to ADD to your existing
`Settings` class in src/hue_async/core/config.py (pydantic-settings).
Keep your existing HUE_* / WEB_* fields; just add these.
"""

# class Settings(BaseSettings):
#     ... your existing fields ...

#     # --- Auth0 OIDC ---
#     AUTH0_DOMAIN: str = ""            # e.g. dev-xxxx.us.auth0.com
#     AUTH0_CLIENT_ID: str = ""
#     AUTH0_CLIENT_SECRET: str = ""
#     WEB_BASE_URL: str = "http://localhost:8000"

#     # --- Agent ---
#     ANTHROPIC_API_KEY: str = ""
#     AGENT_MODEL: str = "claude-sonnet-4-6"
#     # Space-delimited grant. This is the agent's ceiling — note bridge:admin is absent.
#     AGENT_SCOPES: str = "lights:read lights:write scenes:write"

#     # --- Demo toggles (run with no bridge / no API key) ---
#     MOCK_HUE: bool = True
#     MOCK_LLM: bool = True
