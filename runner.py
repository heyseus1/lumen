from __future__ import annotations

"""
The agent runner.

Security spine (this is the part that matters):
  1. The model is only shown the tools the agent is *granted* — it cannot invoke
     what it cannot see.
  2. Every tool call is re-checked against the grant at execution time, so even a
     hallucinated or coerced call to a withheld tool is refused.

So the agent's authority is its scope grant, full stop — independent of what the
logged-in human can do, and independent of what the prompt asks for. That is the
"AI agent as a least-privilege non-human identity" demo.
"""

import re

from hue_async.agent.tools import Tool, all_tools, granted_tools

SYSTEM = (
    "You are a home-lighting assistant that controls Philips Hue lights by "
    "calling tools. Only use the tools provided. Keep replies short. If asked to "
    "do something you have no tool for, say you are not authorized for that "
    "action and name what you can do."
)


def _dispatch(tool: Tool, service, granted: set[str], args: dict) -> dict:
    if tool.required_scope not in granted:
        return {"ok": False, "detail": f"DENIED: agent lacks scope '{tool.required_scope}'"}
    return tool.handler(service, args)


def run_agent(message: str, service, granted: set[str], settings) -> dict:
    if settings.MOCK_LLM or not settings.ANTHROPIC_API_KEY:
        return _mock_run(message, service, granted)
    return _anthropic_run(message, service, granted, settings)


# ---------------------------------------------------------------------------
# Real LLM path (Anthropic tool use)
# ---------------------------------------------------------------------------
def _anthropic_run(message: str, service, granted: set[str], settings) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    tools = granted_tools(granted)
    by_name = {t.name: t for t in tools}
    api_tools = [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]

    messages = [{"role": "user", "content": message}]
    actions: list[dict] = []

    for _ in range(5):  # cap the tool loop
        resp = client.messages.create(
            model=settings.AGENT_MODEL,
            max_tokens=1024,
            system=SYSTEM,
            tools=api_tools,
            messages=messages,
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"reply": text.strip(), "actions": actions}

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            tool = by_name.get(block.name) or next((t for t in all_tools() if t.name == block.name), None)
            outcome = _dispatch(tool, service, granted, dict(block.input)) if tool else {
                "ok": False, "detail": f"unknown tool {block.name}"}
            if outcome.get("action"):
                actions.append(outcome["action"])
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(outcome.get("detail")),
                "is_error": not outcome.get("ok", False),
            })
        messages.append({"role": "user", "content": results})

    return {"reply": "Stopped after too many steps.", "actions": actions}


# ---------------------------------------------------------------------------
# Offline mock path (no API key needed)
# ---------------------------------------------------------------------------
def _mock_run(message: str, service, granted: set[str]) -> dict:
    m = message.lower().strip()
    tools = {t.name: t for t in all_tools()}
    actions: list[dict] = []

    def run(name: str, args: dict) -> str:
        out = _dispatch(tools[name], service, granted, args)
        if out.get("action"):
            actions.append(out["action"])
        return str(out.get("detail"))

    # status / list
    if any(w in m for w in ("status", "what's on", "list", "which lights")):
        return {"reply": str(run("list_rooms", {})), "actions": actions}

    # scene: "activate <scene> in <room>" / "set the deep house scene"
    sc = re.search(r"(?:activate|set|play|start)\s+(?:the\s+)?(.+?)\s+(?:scene|vibe)", m)
    if sc:
        room = re.search(r"in (?:the )?(\w+)", m)
        reply = run("activate_scene", {"room": room.group(1) if room else "studio",
                                        "scene": sc.group(1)})
        return {"reply": reply, "actions": actions}

    # brightness: "set studio to 40%" / "dim the kitchen to 20"
    br = re.search(r"(?:set|dim|brighten)\s+(?:the\s+)?(\w+).*?(\d{1,3})\s*%?", m)
    if br:
        reply = run("set_brightness", {"room": br.group(1), "level": int(br.group(2))})
        return {"reply": reply, "actions": actions}

    # power: "turn on/off the studio"
    pw = re.search(r"turn\s+(on|off)\s+(?:the\s+)?(\w+)", m)
    if pw:
        reply = run("set_power", {"room": pw.group(2), "on": pw.group(1) == "on"})
        return {"reply": reply, "actions": actions}

    # delete (withheld -> demonstrates refusal)
    if "delete" in m and "scene" in m:
        reply = run("delete_scene", {"room": "studio", "scene": "x"})
        return {"reply": reply, "actions": actions}

    return {"reply": "Try: 'turn on the studio', 'set kitchen to 30%', "
                     "'play the deep house scene', or 'status'.", "actions": actions}
