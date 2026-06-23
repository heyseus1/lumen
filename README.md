# Lumen

A Philips Hue control portal with **Auth0 login** and a **chat agent that is
scope-constrained at the identity layer** — it can only do what its grant allows,
no matter what you ask it.

```
browser ──(session, Auth0 OIDC)──▶ Lumen ──▶ Hue bridge
                                     │
                                     └── chat agent (least-privilege NHI)
```

## Why this exists

The interesting part isn't "chat for lights." It's that the agent's authority is
a scope grant (`AGENT_SCOPES`), enforced twice:

1. The model is only shown the tools its grant permits — it can't invoke what it
   can't see.
2. Every tool call is re-checked at execution time, so a hallucinated or coerced
   call to a withheld tool is refused.

Default grant is `lights:read lights:write scenes:write`. `bridge:admin` is
withheld, so `delete_scene` is off-limits. Ask the bot to delete a scene and it
refuses on the same valid session — least privilege for a non-human identity,
made visible.

ID/access tokens from Auth0 are RS256 JWTs validated against the tenant JWKS
(Authlib handles this on login). Offline validation, no per-request call to Auth0.

## Quick start (no bridge, no LLM key)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env          # MOCK_HUE / MOCK_LLM are true by default
# fill AUTH0_DOMAIN / CLIENT_ID / CLIENT_SECRET from your Auth0 app
uvicorn hue_async.web.app:app --reload --port 5000
# open http://localhost:5000
```

Auth0 application (Regular Web Application):
- Allowed Callback URLs: `http://localhost:5000/callback`
- Allowed Logout URLs: `http://localhost:5000`

Try in the chat: `turn on the studio`, `set kitchen to 30%`,
`play the deep house scene in the studio`, `delete the focus scene` (refused).

## Going live

- `MOCK_HUE=false` + set `HUE_BRIDGE_IP` and `HUE_USERNAME` (mint the app key by
  pressing the bridge link button, then
  `curl -k -X POST https://<ip>/api -d '{"devicetype":"lumen#app","generateclientkey":true}'`).
- `MOCK_LLM=false` + set `ANTHROPIC_API_KEY` to use the real agent.

## Layout

```
src/hue_async/
  core/config.py        settings (pydantic-settings)
  clients/hue_client.py thin Hue v2 HTTP client
  services/room_service.py  rooms / scenes / state
  agent/tools.py        tools + required scopes + dispatch
  agent/runner.py       Anthropic tool-use loop + offline mock
  agent/fake_service.py runs with no bridge
  web/auth.py           Auth0 OIDC
  web/chat.py           /api/chat + room actions
  web/app.py            dashboard + wiring
  web/templates/dashboard.html
```

## Roadmap

Give the agent its own Auth0 M2M client and mint it a token scoped to exactly
`AGENT_SCOPES`, then validate that token's scopes on each tool call. The grant
then lives in the IdP (revocable centrally) instead of a config string — the
non-human-identity governance version of this demo.
