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
    """A name-aware intent parser. Instead of guessing English phrasings, it
    matches the message against the bridge's actual room and scene names — so a
    real scene name appearing anywhere in the sentence is treated as intent,
    regardless of word order or verb. Replies are plain sentences."""
    m = " " + message.lower().strip() + " "
    tools = {t.name: t for t in all_tools()}
    actions: list[dict] = []

    def run(name: str, args: dict) -> dict:
        out = _dispatch(tools[name], service, granted, args)
        if out.get("action"):
            actions.append(out["action"])
        return out

    def say(text: str) -> dict:
        return {"reply": text, "actions": actions}

    rooms = service.list_rooms()
    room = next((r for r in rooms if r.name.lower() in m or r.room_id.lower() in m), None)

    has_num = re.search(r"(\d{1,3})", m)
    is_question = message.strip().endswith("?") or bool(re.match(r"\s*(is|are|what|which|how|does|do)\b", m))
    scene_word = "scene" in m

    # 1) list scenes
    if scene_word and any(w in m for w in ("list", "what", "which", "available", "show", "have", "got")):
        if not room:
            return say("Which room? e.g. 'list bedroom scenes'.")
        out = run("list_scenes", {"room": room.name})
        if not out["ok"]:
            return say(out["detail"])
        names = out["detail"]["scenes"]
        if not names:
            return say(f"{room.name} has no scenes.")
        return say(f"{room.name} has {len(names)} scenes: {', '.join(names)}.")

    # 2) brightness — a number, or a dim/brighten verb
    dim = bool(re.search(r"\bdim\b", m))
    brighten = bool(re.search(r"\bbrighten\b|\bbrighter\b", m))
    if has_num or dim or brighten:
        if not room:
            return say("Which room? e.g. 'set bedroom to 40%'.")
        level = int(has_num.group(1)) if has_num else (30 if dim else 100)
        return say(run("set_brightness", {"room": room.name, "level": level})["detail"])

    # 3) activate an EXISTING scene — match a real scene name in the message
    if not is_question:
        for r in ([room] if room else rooms):
            for s in service.list_scenes_for_room(r.room_id):
                if s.name.lower() in m:
                    return say(run("activate_scene", {"room": r.name, "scene": s.name})["detail"])
        if scene_word and room:
            avail = [s.name for s in service.list_scenes_for_room(room.room_id)]
            return say(f"I couldn't find that scene in {room.name}. Available: {', '.join(avail)}.")

    # 4) status / metrics
    if is_question or any(w in m for w in ("status", "current", "what's on", "whats on")):
        if room:
            d = run("room_status", {"room": room.name})["detail"]
            return say(f"The {d['room']} is " + (f"on at {d['brightness']}%." if d["on"] else "off."))
        parts = [f"{x['room']} is " + (f"on at {x['brightness']}%" if x["on"] else "off")
                 for x in run("list_rooms", {})["detail"]]
        return say("; ".join(parts) + ".")

    # 5) power on/off
    if re.search(r"\b(on|off|turn|switch|toggle|shut|kill)\b", m):
        if not room:
            return say("Which room? e.g. 'turn off the bedroom'.")
        on = "off" not in m and "shut" not in m and "kill" not in m
        return say(run("set_power", {"room": room.name, "on": on})["detail"])

    return say("Try: 'turn on the bedroom', 'set kitchen to 30%', "
               "'list bedroom scenes', or 'switch bedroom to Candle'.")