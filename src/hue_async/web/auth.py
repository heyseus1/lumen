from __future__ import annotations

"""
Auth0 OIDC login (Authorization Code flow).

The human authenticates via Auth0 as the OpenID Provider. Authlib runs the OIDC
dance and validates the returned ID token against the tenant's JWKS (signature,
iss, aud, exp, nonce) — the offline-JWKS discipline, handled by a maintained
library rather than hand-rolled crypto.

Access is gated at the IdP by a Post-Login Action (an email allowlist). When it
denies a user, Auth0 redirects back to /callback with ?error=access_denied
instead of a code; we render a clean 403 dead-end rather than crashing.

Auth0 application setup (Regular Web Application):
  Allowed Callback URLs:  http://localhost:5000/callback, http://127.0.0.1:5000/callback
  Allowed Logout URLs:    http://localhost:5000, http://127.0.0.1:5000
"""

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, RedirectResponse

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


_DENIED_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Lumen</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600&family=Inter&display=swap" rel="stylesheet">
<style>
  body{{margin:0;background:#0d0d10;color:#ECEAE4;font-family:'Inter',system-ui,sans-serif}}
  .box{{max-width:420px;margin:18vh auto;text-align:center;padding:0 20px}}
  .lamp{{width:13px;height:13px;border-radius:50%;background:#F4B45A;
        box-shadow:0 0 14px 2px rgba(244,180,90,.8);margin:0 auto 20px}}
  h1{{font-family:'Space Grotesk',system-ui;font-weight:600;font-size:22px;margin:0 0 8px}}
  p{{color:#8c8a83;line-height:1.5}}
</style></head>
<body><div class="box">
  <div class="lamp"></div>
  <h1>Lumen</h1>
  <p>{desc}</p>
</div></body></html>"""


@router.get("/login")
async def login(request: Request):
    redirect_uri = request.url_for("callback")
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="callback")
async def callback(request: Request):
    # A Post-Login Action denial comes back here as ?error=access_denied (no code).
    error = request.query_params.get("error")
    if error:
        desc = request.query_params.get("error_description", "Access denied.")
        return HTMLResponse(_DENIED_PAGE.format(desc=desc), status_code=403)

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