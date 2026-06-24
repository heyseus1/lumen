from __future__ import annotations

"""
The agent's non-human identity.

On demand, the agent authenticates to Auth0 as itself (client-credentials grant),
receives a least-privilege access token, and the app validates that token offline
against the tenant JWKS — the same discipline as the human login path. The scopes
Auth0 granted become the agent's authority for every tool call.

So the grant lives in the IdP: granted and revoked in Auth0, not in local config.
The token is cached until shortly before expiry and re-minted on refresh (the
Auth0-recommended M2M pattern; lower the API's token lifetime to make it more
ephemeral).

Note on architecture: the Hue bridge is not the resource server here — it has no
concept of Auth0. The app is the policy-enforcement point. It holds the agent's
IdP-issued credential, proves it (signature/iss/aud/exp), and enforces the scopes
that credential carries. Fails closed: if the grant can't be proven, the agent
gets no capability.

Falls back to AGENT_SCOPES (config) only when no M2M credential is configured, so
the app still runs fully offline.
"""

import threading
import time

import httpx
import jwt
from jwt import PyJWKClient

from hue_async.core.config import get_settings


class AgentIdentity:
    def __init__(self, settings) -> None:
        self.s = settings
        self._token: str | None = None
        self._exp: float = 0.0
        self._scopes: set[str] = set()
        self._lock = threading.Lock()
        self._jwks = (
            PyJWKClient(f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json", cache_keys=True)
            if settings.AUTH0_DOMAIN else None
        )

    @property
    def configured(self) -> bool:
        return bool(self.s.AGENT_CLIENT_ID and self.s.AGENT_CLIENT_SECRET
                    and self.s.AGENT_API_AUDIENCE and self._jwks)

    def scopes(self) -> set[str]:
        """The agent's current authority: scopes from the live validated token,
        or the config fallback when no M2M credential is set. Fails closed."""
        if not self.configured:
            return set(self.s.AGENT_SCOPES.split())
        try:
            self._ensure_token()
        except Exception:
            # Couldn't prove a fresh grant. Keep a still-valid cached one; else deny.
            if not (self._token and time.time() < self._exp):
                return set()
        return set(self._scopes)

    def token(self) -> str | None:
        if not self.configured:
            return None
        self._ensure_token()
        return self._token

    def _ensure_token(self, skew: float = 60.0) -> None:
        if self._token and time.time() < self._exp - skew:
            return
        with self._lock:
            if self._token and time.time() < self._exp - skew:
                return
            self._fetch_and_validate()

    def _fetch_and_validate(self) -> None:
        r = httpx.post(
            f"https://{self.s.AUTH0_DOMAIN}/oauth/token",
            json={
                "client_id": self.s.AGENT_CLIENT_ID,
                "client_secret": self.s.AGENT_CLIENT_SECRET,
                "audience": self.s.AGENT_API_AUDIENCE,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        token = data["access_token"]

        signing_key = self._jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.s.AGENT_API_AUDIENCE,
            issuer=f"https://{self.s.AUTH0_DOMAIN}/",
            options={"require": ["exp", "iat", "iss", "aud"]},
        )

        scopes = set(str(claims.get("scope", "")).split())
        scopes.update(claims.get("permissions", []) or [])

        self._token = token
        self._scopes = scopes
        self._exp = float(claims.get("exp", time.time() + data.get("expires_in", 0)))


_identity: AgentIdentity | None = None
_identity_lock = threading.Lock()


def get_agent_identity() -> AgentIdentity:
    global _identity
    if _identity is None:
        with _identity_lock:
            if _identity is None:
                _identity = AgentIdentity(get_settings())
    return _identity
