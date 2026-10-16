"""Talking to the local timing server. Every call tolerates the server being
down (it restarts in its own loop): the pilot just tries again next tick."""

import json
import urllib.error
import urllib.request


class Server:
    def __init__(self, url: str, token: str, log=print):
        self.url, self.token, self.log = url, token, log
        self._down = False

    def _call(self, method: str, path: str, body=None):
        req = urllib.request.Request(
            self.url + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                out = json.loads(resp.read().decode() or "{}")
            if self._down:
                self.log("server reachable again")
            self._down = False
            return out
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if not self._down:
                self.log(f"server unreachable ({exc})")
            self._down = True
            return None

    def state(self):
        return self._call("GET", "/api/state")

    def phase(self, body: dict) -> None:
        self._call("POST", "/api/expo/phase", body)

    def assign(self, client_id: str, name: str) -> bool:
        out = self._call("POST", f"/api/laps/{client_id}/assign",
                         {"driver_name": name})
        return bool(out and out.get("ok"))

    def post_lap(self, payload: dict) -> bool:  # demo sim only
        return self._call("POST", "/api/laps", payload) is not None
