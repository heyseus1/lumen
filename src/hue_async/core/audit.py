from __future__ import annotations

"""
Audit trail — one sink every privileged action flows through, whether it came
from the human UI or the agent.

Each entry records the principal (who), the action and target (what), the
decision (allowed / denied) and, on denial, the missing scope. The denials are
the point: they are least-privilege proving itself in writing.

Entries go to a console logger (syslog-style) and an in-memory ring buffer that
the /audit page reads. Swap the ring for a file/DB when you want persistence.
"""

import json
import logging
import threading
from collections import deque
from datetime import datetime, timezone

_LOG = logging.getLogger("lumen.audit")
_BUF: deque[dict] = deque(maxlen=500)
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(principal: str, action: str, decision: str, *,
           target: str | None = None, reason: str | None = None,
           scope_basis: str | None = None, cid: str | None = None) -> dict:
    entry = {
        "ts": _now(),
        "principal": principal,     # "human:<sub>" or "agent"
        "action": action,           # set_power, activate_scene, chat.message, ...
        "target": target,
        "decision": decision,       # "allowed" | "denied" | "error"
        "reason": reason,           # e.g. "missing scope: scenes:write"
        "scope_basis": scope_basis, # which scope authorized it
        "cid": cid,                 # correlation id tying a chat msg to its actions
    }
    with _LOCK:
        _BUF.appendleft(entry)
    _LOG.info(json.dumps(entry))
    return entry


def recent(limit: int = 100) -> list[dict]:
    with _LOCK:
        return list(_BUF)[:limit]
