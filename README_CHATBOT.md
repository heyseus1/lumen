# Hue Control Portal — Auth0 login + scope-constrained chat agent

This upgrades the existing `technologic/Hue` app. It keeps your `RoomService` and
`HueClient` untouched and adds three things:

1. **Real Auth0 login** (OIDC Authorization Code) in `web/auth.py` — replacing the
   hardcoded username/password form. Authlib validates the ID token against the
   tenant JWKS for you (the offline-JWKS lesson, done by a maintained library).
2. **A chat agent** (`agent/`) that controls the lights from natural language.
3. **A dashboard** (`web/templates/dashboard.html`) with room cards + a chat panel.

## The point: the agent is a least-privilege non-human identity

The agent's authority is its scope grant — `AGENT_SCOPES` — and nothing else.

- The model is only shown the tools its grant permits (`agent/tools.py`,
  `granted_tools`). It can't invoke what it can't see.
- Every call is re-checked at execution time (`runner._dispatch`). A hallucinated
  or coerced call to a withheld tool is refused.

Default grant is `lights:read lights:write scenes:write`. `bridge:admin` is
deliberately absent, so `delete_scene` is off-limits. Ask the bot to delete a
scene and it refuses — same identity, valid session, structurally barred. That
refusal is the demo. Frame the project around *that*, not around "chat for lights."

## Files (drop into src/hue_async/)

```
web/auth.py                 Auth0 OIDC router (fills the empty file)
web/deps.py                 current-user guard + service factory (mock-aware)
web/chat.py                 /api/chat + JSON room actions
web/app.py                  rewired: Auth0 + chat + dashboard
web/templates/dashboard.html
agent/tools.py              tools + required scopes + dispatch
agent/runner.py             Anthropic tool-use loop + offline mock
agent/fake_service.py       runs with no bridge
core/config_additions.py    fields to merge into your Settings
```

## Dependencies to add (pyproject.toml)

```
"authlib>=1.3.0",
"httpx>=0.27.0",
"anthropic>=0.40.0",
"pyjwt[crypto]>=2.8.0",
```

You already have `itsdangerous`, `jinja2`, `python-multipart`, `fastapi`, `uvicorn`.

## Config

Merge the fields from `core/config_additions.py` into your `Settings`. Then in `.env`:

```
WEB_SESSION_SECRET=change-me
AUTH0_DOMAIN=dev-xxxx.us.auth0.com
AUTH0_CLIENT_ID=...
AUTH0_CLIENT_SECRET=...
WEB_BASE_URL=http://localhost:8000

ANTHROPIC_API_KEY=            # leave blank to use the offline mock
AGENT_MODEL=claude-sonnet-4-6
AGENT_SCOPES=lights:read lights:write scenes:write

MOCK_HUE=true                 # true = no bridge needed
MOCK_LLM=true                 # true = rule-based parser, no API key
```

## Run

```bash
pip install -e .   # after adding the deps above
uvicorn hue_async.web.app:app --reload --port 8000
# open http://localhost:8000  -> redirected to Auth0 login
```

With both mocks on, the whole thing works end to end with no bridge and no LLM key.
Try: `turn on the studio`, `set kitchen to 30%`, `play the deep house scene in the
studio`, `delete the focus scene` (refused).

## Auth0 setup

Create a **Regular Web Application**:
- Allowed Callback URLs: `http://localhost:8000/callback`
- Allowed Logout URLs: `http://localhost:8000`

Copy its Domain / Client ID / Client Secret into `.env`. (User login uses OIDC, so
no API/audience is required for v1. Add an API + `AGENT_SCOPES` as real granted
permissions later if you want the agent carrying its own access token.)

## Honest next step

Right now `AGENT_SCOPES` is enforced locally — a config value, not a token claim.
The principled version: give the agent its own M2M client in Auth0, mint it an
access token scoped to exactly those permissions, and have `_dispatch` validate
that token's scopes (the Warden validator). Then the grant lives in your IdP, not
your code, and you can revoke it centrally. That's the upgrade that turns this from
a demo into the NHI-governance story.
