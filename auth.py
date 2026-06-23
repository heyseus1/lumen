from __future__ import annotations

"""
Auth0 OIDC login (Authorization Code flow).

This replaces the hardcoded username/password form. Authlib handles the OIDC
dance and — importantly — validates the returned ID token against the tenant's
JWKS (signature, iss, aud, exp, nonce) for us. That's the same offline-JWKS
validation lesson from the Warden demo; here we let a maintained library do the
crypto instead of hand-rolling it, which is the right call.

Auth0 application setup (Regular Web Application):
  Allowed Callback URLs:  http://localhost:8000/callback
  Allowed Logout URLs:    http://localhost:8000
"""

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from hue_async.core.config import get_settings

settings = get_settings()

oauth = OAuth()
oauth.register(
    name="auth0",
    client_id=settings.AUTH0_CLIENT_ID,
    client_secret=settings.AUTH0_CLIENT_SECRET,
    server_metadata_url=f"https://{settings.AUTH0_DOMAIN}/.well-known/openid-configuration",
    client_kwargs={"scope": "openid profile email"},
)

router = APIRouter()


@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("callback")
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="callback")
async def callback(request: Request):
    token = await oauth.auth0.authorize_access_token(request)  # validates ID token vs JWKS
    userinfo = token.get("userinfo") or {}
    request.session["user"] = {
        "sub": userinfo.get("sub"),
        "name": userinfo.get("name") or userinfo.get("email") or "user",
        "email": userinfo.get("email"),
    }
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(
        url=(
            f"https://{settings.AUTH0_DOMAIN}/v2/logout"
            f"?client_id={settings.AUTH0_CLIENT_ID}"
            f"&returnTo={settings.WEB_BASE_URL}"
        ),
        status_code=303,
    )
