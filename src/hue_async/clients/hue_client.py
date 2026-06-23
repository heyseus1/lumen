from __future__ import annotations

"""
HueClient: a thin HTTP wrapper around the Philips Hue v2 local API.

Intentionally dumb — it knows URLs, headers, and GET/PUT. No business logic
(room/scene selection lives in the service layer). Sync `requests` is fine for
local use; swap to httpx later if you want async.

The bridge ships a self-signed cert, so verify=False here. The correct
production fix is to pin the bridge certificate, not to disable verification.
"""

from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HueClient:
    def __init__(self, bridge_ip: str, app_key: str) -> None:
        self.bridge_ip = bridge_ip
        self.app_key = app_key

    def _url(self, path: str) -> str:
        return f"https://{self.bridge_ip}{path}"

    def _headers(self, json: bool = False) -> dict[str, str]:
        headers = {"hue-application-key": self.app_key, "Accept": "application/json"}
        if json:
            headers["Content-Type"] = "application/json"
        return headers

    def get(self, path: str) -> dict[str, Any]:
        r = requests.get(self._url(path), headers=self._headers(), verify=False, timeout=10)
        r.raise_for_status()
        return r.json()

    def put(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.put(self._url(path), headers=self._headers(json=True),
                         json=body, verify=False, timeout=10)
        r.raise_for_status()
        return r.json() if r.content else {}
