# Lumen

A Philips Hue control portal built as an **identity-engineering study**: real
Auth0 OIDC login for the human, an LLM agent with its own non-human identity
bounded by a least-privilege scope grant, and an audit trail that records every
action either of them takes. The lighting is the demo surface; the access model
is the point.

![Lumen demo](docs/demo.gif)

```
                  ┌── OIDC Authorization Code (Authlib) ──┐
   browser ───────┤                                       ├──> Auth0 tenant
      │           └── ID token (RS256) validated vs JWKS ─┘     (OIDC + M2M)
      │  session                                                     ▲
      ▼                                                              │ client-credentials
    Lumen ──(scope-checked dispatch)──> chat agent ──────────────────┘
      │                                    │  (agent's own M2M token)
      └──────────── audit trail ───────────┘──> Hue v2 bridge
```

## Identity model

**Human authentication — OIDC Authorization Code.**
Login is delegated to Auth0 as the OpenID Provider. Lumen is a confidential
Regular Web Application. The returned **ID token is an Auth0-signed RS256 JWT,
validated offline against the tenant's JWKS** — signature, `iss`, `aud`, `exp`
all checked, with no per-request call to Auth0. Authlib performs the validation
rather than hand-rolled crypto.

Access is restricted at the IdP: a **Post-Login Action allowlists the owner's
email**, so an unauthorized human is denied before a token is ever issued. The
app handles that denial with a clean 403 dead-end and **fails closed**.

**Agent authorization — a real non-human identity.**
The chat agent has its **own Auth0 Machine-to-Machine application**. It
authenticates as itself via the client-credentials grant, receives a
least-privilege access token, and the app validates that token offline against
the JWKS — the same discipline as the human path. **The scopes Auth0 grants are
the agent's authority**, sourced from the live token, not from local config. The
grant lives in the IdP: revoke it in Auth0 and the agent loses the capability on
next refresh, with no code change.

Enforcement is two layers, defense in depth:

1. **Capability hiding** — the model is only handed the tools its grant permits.
   It cannot call what it cannot see.
2. **Execution-time check** — every tool call is re-validated against the grant in
   `agent/runner.py::_dispatch`, so a hallucinated or prompt-injected call to a
   withheld tool is refused regardless of what the model emitted.

The tool surface is read-plus-recall only — read state, list scenes, set power and
brightness, recall an **existing** scene. There is deliberately no create or
delete tool, so "the agent never authors or destroys" is true by construction.

```
tool            required scope    effect
list_rooms      lights:read       all rooms: power + brightness
room_status     lights:read       one room's state
list_scenes     lights:read       scenes available in a room
set_power       lights:write      on / off
set_brightness  lights:write      1-100
activate_scene  scenes:write      recall an existing scene
```

> Provisioning the agent's identity is documented step-by-step in
> **[docs/auth0-agent-runbook.md](docs/auth0-agent-runbook.md)** — creating the
> API, scopes, M2M app, and verifying + revoking the grant.

## Audit trail

Every privileged action — human click or agent tool call — flows through one sink
(`core/audit.py`) and is visible live at `/audit`. Each entry records the
principal (`human:<sub>` or `agent`), the action and target, the decision
(allowed / denied), the missing scope on a denial, and a correlation id tying a
chat message to the tool calls it spawned.

The denials are the most valuable rows: least privilege proving itself in writing.

```
human:auth0|… chat.message   allowed                          cid=cdfe05
agent         set_power       allowed   lights:write           cid=cdfe05
human:auth0|… chat.message   allowed                          cid=5e7968
agent         activate_scene  denied    missing scope: scenes:write  cid=5e7968
```

## The three edges

- **Human edge** — unauthorized people are denied at the IdP before a token issues.
- **Machine edge** — the agent is a distinct identity capped by its own scoped token.
- **The record between** — every action, allowed or refused, is audited and visible.

## Why this shape

Autonomous agents are non-human identities that act with real privilege, and the
common failure mode is handing them broad access "to make it work." This is a
small, working argument for the opposite: an agent constrained to least privilege
at the identity layer, where the constraint holds no matter what the prompt asks.
The Hue bridge is just a tangible thing to be over-permissioned *against*. (The
bridge doesn't validate tokens — the app is the policy-enforcement point, holding
the agent's IdP-issued credential and enforcing the scopes it carries.)

## Run it

Mock mode needs no bridge and no LLM key — only an Auth0 app — so the auth flow is
demonstrable on its own.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env        # MOCK_HUE / MOCK_LLM default to true
# generate a real session secret and put it in .env as WEB_SESSION_SECRET
openssl rand -hex 32
uvicorn hue_async.web.app:app --reload --port 5000
# open http://localhost:5000  -> redirected to Auth0 login
```

**Auth0 setup** — create a Regular Web Application:
- Allowed Callback URLs: `http://localhost:5000/callback`, `http://127.0.0.1:5000/callback`
- Allowed Logout URLs: `http://localhost:5000`, `http://127.0.0.1:5000`

Put its Domain / Client ID / Client Secret in `.env`. For the agent's M2M identity,
follow **[docs/auth0-agent-runbook.md](docs/auth0-agent-runbook.md)** and set
`AGENT_API_AUDIENCE` / `AGENT_CLIENT_ID` / `AGENT_CLIENT_SECRET`.

**Going live:**
- `MOCK_HUE=false` + `HUE_BRIDGE_IP` + `HUE_USERNAME` (mint the app key by pressing
  the bridge link button, then
  `curl -k -X POST https://<ip>/api -d '{"devicetype":"lumen#app","generateclientkey":true}'`).
- `MOCK_LLM=false` + `ANTHROPIC_API_KEY` for the LLM agent; otherwise a built-in
  name-aware parser handles commands with no key (scope enforcement is identical
  on both paths).

## What is real vs. roadmap

- **Real:** human OIDC login with offline JWKS validation; IdP-side owner allowlist
  with fail-closed denial; the agent's own M2M identity with client-credentials
  token and JWKS-validated scopes as its live authority; two-layer scope
  enforcement; a tool surface with no authoring capability; an audit trail across
  both principals.
- **Roadmap:** short token TTLs for genuinely ephemeral agent credentials;
  persisting the audit trail (file/DB) for durability and tamper-evidence; binding
  agent actions to the triggering human principal so every action is traceable to
  a person, not just to "agent."

## Layout

```
src/hue_async/
  core/config.py           settings (pydantic-settings)
  core/audit.py            single audit sink (human + agent)
  clients/hue_client.py    thin Hue v2 HTTP client
  services/room_service.py rooms / scenes / state
  agent/identity.py        agent M2M token: fetch, cache, JWKS-validate
  agent/tools.py           tools + required scopes (the capability boundary)
  agent/runner.py          scope dispatch | Anthropic tool loop | offline parser
  agent/fake_service.py    runs with no bridge
  web/auth.py              Auth0 OIDC login, denial handling, logout
  web/chat.py              agent + room/scene actions + audit feed
  web/app.py               dashboard, room pages, /audit
  web/templates/           base | dashboard | room | audit
docs/
  auth0-agent-runbook.md   provisioning the agent's non-human identity
```

## Stack

FastAPI · Authlib (OIDC) · PyJWT (JWKS) · Anthropic (optional) · Hue CLIP v2 ·
pydantic-settings · Jinja2.