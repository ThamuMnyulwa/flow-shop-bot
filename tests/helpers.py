from fastapi.testclient import TestClient


def csrf(client: TestClient) -> str:
    """Load a page so the session gets a CSRF token, then read it from the meta tag."""
    page = client.get("/admin/login").text
    marker = 'name="csrf" content="'
    start = page.index(marker) + len(marker)
    return page[start:page.index('"', start)]


class SimCustomer:
    """Plays a customer in the fake chat, the way a person taps through WhatsApp."""

    def __init__(self, client: TestClient, wa_id: str = "27820000001", name: str = "Thandi Test"):
        self.client = client
        self.wa_id = wa_id
        self.name = name
        self.token = csrf(client)
        self.seen = 0

    def _post(self, path: str, **kwargs):
        r = self.client.post(path, headers={"X-CSRF-Token": self.token}, **kwargs)
        assert r.status_code == 200, r.text
        return r

    def messages(self) -> list[dict]:
        return self.client.get("/simulator/messages", params={"wa_id": self.wa_id}).json()["messages"]

    def new_replies(self) -> list[dict]:
        msgs = self.messages()
        fresh = [m for m in msgs if m["id"] > self.seen and m["direction"] == "out"]
        if msgs:
            self.seen = msgs[-1]["id"]
        return fresh

    def say(self, text: str) -> list[dict]:
        self._post("/simulator/text", json={"wa_id": self.wa_id, "name": self.name, "text": text})
        return self.new_replies()

    def last_bot(self) -> dict:
        return [m for m in self.messages() if m["direction"] == "out"][-1]

    def tap(self, title: str) -> list[dict]:
        """Tap a button or list row on the bot's latest interactive message."""
        for m in reversed(self.messages()):
            if m["direction"] != "out" or m["kind"] not in ("buttons", "list"):
                continue
            options = m["payload"]["buttons"] + m["payload"]["rows"]
            for opt in options:
                if opt["title"] == title:
                    self._post("/simulator/reply", json={"wa_id": self.wa_id, "name": self.name, "reply_id": opt["id"],
                                                         "title": opt["title"], "list_reply": m["kind"] == "list"})
                    return self.new_replies()
            raise AssertionError(f"No option {title!r} in {[o['title'] for o in options]}")
        raise AssertionError("No interactive message to tap")

    def send_file(self, content: bytes = b"\xff\xd8\xff fake jpeg", content_type: str = "image/jpeg") -> list[dict]:
        self._post("/simulator/file", data={"wa_id": self.wa_id, "name": self.name},
                   files={"file": ("proof.jpg", content, content_type)})
        return self.new_replies()


def texts(replies: list[dict]) -> str:
    return "\n".join(m["text"] for m in replies)
