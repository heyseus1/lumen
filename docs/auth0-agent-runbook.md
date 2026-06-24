# Runbook — Giving the Agent Its Own Auth0 Identity

This provisions the chat agent as a **non-human identity (NHI)**: its own
Machine-to-Machine application in Auth0, issued a short-lived access token via the
client-credentials grant, scoped to exactly the permissions it needs. After this,
the agent's authority lives in the IdP — granted, audited, and revoked in Auth0 —
instead of a config string in the app.

It is a deliberately separate identity from the human web login. The human signs
in with OIDC; the agent authenticates as itself. Two principals, two credentials.

> Auth0 dashboard labels shift occasionally. Steps are described by function;
> if a menu name differs, look for the equivalent.

---

## What you'll create

| Object | Purpose |
|---|---|
| **API** (resource server) | The thing the agent is authorized *against*. Its identifier is the token `audience`. |
| **Permissions** on that API | `lights:read`, `lights:write`, `scenes:write` — the agent's possible capabilities. |
| **Machine-to-Machine application** | The agent's identity. Holds the client credential. |
| **Grant** linking the M2M app → API | The least-privilege scopes the agent actually gets. |

`bridge:admin` is intentionally never created or granted. The agent cannot be
given a capability that doesn't exist.

---

## Prerequisites

- The existing human web-login app already works (the Regular Web Application).
- You can reach the Auth0 Dashboard for your tenant
  (`dev-20hu8r2wgzbkc0sf.us.auth0.com`).

---

## Step 1 — Create the protected API

1. Dashboard → **Applications → APIs → Create API**.
2. **Name:** `Lumen Agent API`
3. **Identifier:** `https://lumen/agent`
   This is a logical URL, not a real endpoint — it becomes the token's `aud`.
   Once set it cannot be changed, so keep it stable.
4. **Signing Algorithm:** `RS256` (default — this is what lets you validate the
   token offline against JWKS).
5. Create.

## Step 2 — Define the agent's permissions

1. Open the new API → **Permissions** tab.
2. Add each scope with a short description:
   - `lights:read` — read room power and brightness
   - `lights:write` — set power and brightness
   - `scenes:write` — recall existing scenes
3. Do **not** add an admin/delete permission. The absence is the control.

## Step 3 — Put the permissions into the token

1. Same API → **Settings** tab → **RBAC Settings**.
2. Enable **Enable RBAC**.
3. Enable **Add Permissions in the Access Token**.
4. Save. (This makes granted scopes appear in the issued token so the app can
   enforce them.)

## Step 4 — Create the agent's identity (M2M app)

1. Dashboard → **Applications → Applications → Create Application**.
2. **Name:** `Lumen Agent`
3. **Type:** **Machine to Machine Applications**.
4. When prompted to authorize an API, select **`Lumen Agent API`**.
5. On the permissions list, check **only** `lights:read`, `lights:write`,
   `scenes:write`. Authorize.

If you weren't prompted, open the app → **APIs** tab → toggle on `Lumen Agent API`
→ expand it → select the three scopes → **Update**.

## Step 5 — Collect the credential

1. Open **Lumen Agent** → **Settings**.
2. Copy **Client ID** and **Client Secret**.
3. These are the agent's credential. Treat the secret like a password — it goes in
   `.env` (git-ignored), never in code or a commit.

## Step 6 — Wire it into `.env`

```bash
# --- Agent non-human identity (Auth0 M2M) ---
AGENT_API_AUDIENCE=https://lumen/agent
AGENT_CLIENT_ID=<Lumen Agent client id>
AGENT_CLIENT_SECRET=<Lumen Agent client secret>

# AGENT_SCOPES stays as the offline/mock fallback; once the M2M token is wired,
# the live grant comes from the token, not this string.
AGENT_SCOPES=lights:read lights:write scenes:write
```

---

## Step 7 — Verify the credential works

Mint a token directly, the same way the app will:

```bash
curl -s --request POST \
  --url https://dev-20hu8r2wgzbkc0sf.us.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "client_id":"<AGENT_CLIENT_ID>",
    "client_secret":"<AGENT_CLIENT_SECRET>",
    "audience":"https://lumen/agent",
    "grant_type":"client_credentials"
  }'
```

You should get back JSON with an `access_token`. Decode its payload (locally — do
not paste a real token into a website):

```bash
TOKEN="<paste access_token>"
python3 -c "import sys,json,base64; p=sys.argv[1].split('.')[1]; p+='='*(-len(p)%4); print(json.dumps(json.loads(base64.urlsafe_b64decode(p)),indent=2))" "$TOKEN"
```

Confirm in the decoded payload:
- `aud` is `https://lumen/agent`
- `iss` is `https://dev-20hu8r2wgzbkc0sf.us.auth0.com/`
- `scope` contains `lights:read lights:write scenes:write`
- (with RBAC on) a `permissions` array lists the same three
- `exp` is present — the token is short-lived

If `scope` is empty, Step 5's grant didn't take — re-check the app's APIs tab.

## Step 8 — Prove the governance payoff (the part that sells it)

1. Open **Lumen Agent → APIs → Lumen Agent API**, un-check `scenes:write`, Update.
2. Re-run the Step 7 curl. The new token's `scope` no longer contains
   `scenes:write`.
3. The agent can no longer activate scenes — and you changed nothing in the code.
   The capability was revoked centrally, in the IdP.
4. Re-check the box to restore it.

That round trip — grant and revoke a non-human identity's capability from the
directory, with the app enforcing whatever the token says — is the whole thesis.
Worth a screenshot for the writeup.

---

## Reference: the four facts the app needs

| `.env` key | Where it comes from |
|---|---|
| `AGENT_API_AUDIENCE` | API identifier (Step 1) |
| `AGENT_CLIENT_ID` | Lumen Agent app (Step 5) |
| `AGENT_CLIENT_SECRET` | Lumen Agent app (Step 5) |
| issuer / JWKS | derived from `AUTH0_DOMAIN`, already set |

## Security notes

- The client secret is a credential. `.env` is git-ignored; if it ever lands in a
  commit, rotate it in the app's Settings rather than trying to scrub history.
- Least privilege is enforced by what you *granted* in Step 4, not by the app
  asking nicely. Grant the minimum; widen only when a capability needs it.
- The agent's identity is independent of the human's. Revoking the human's access
  doesn't touch the agent, and vice-versa — which is exactly why each gets audited
  and rotated on its own schedule.
