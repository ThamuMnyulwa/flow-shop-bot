"""The channel interface (B1). The simulator and the WhatsApp Cloud API run the same conversation code.

WhatsApp's limits are enforced here, so a message the simulator accepts is one WhatsApp accepts too.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_LIST_ROWS = 10
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_INTERACTIVE_BODY = 1024
MAX_TEXT_BODY = 4096
MAX_CARDS = 10
MAX_CARD_BODY = 160


class ChannelLimitError(ValueError):
    pass


@dataclass(frozen=True)
class Button:
    id: str
    title: str


@dataclass(frozen=True)
class Row:
    id: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class Card:
    """One card in a carousel: a photo, a short text and its own reply buttons."""

    image_url: str  # a public URL; WhatsApp fetches carousel photos itself
    image_path: str  # the same photo as a site path, for the simulator and the inbox
    body: str
    buttons: tuple[Button, ...]


@dataclass
class OutMessage:
    kind: str  # text, buttons, list, carousel, template
    text: str = ""
    buttons: list[Button] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    list_button: str = "Choose"
    section_title: str = "Options"
    template_name: str = ""
    template_params: list[str] = field(default_factory=list)
    image_url: str = ""  # a public URL; WhatsApp shows the image above the text and buttons
    image_path: str = ""  # the same image as a site path, for the simulator and the inbox
    cards: list[Card] = field(default_factory=list)

    def validate(self) -> "OutMessage":
        if self.kind == "text" and len(self.text) > MAX_TEXT_BODY:
            raise ChannelLimitError("text is longer than 4096 characters")
        if self.kind in ("buttons", "list") and len(self.text) > MAX_INTERACTIVE_BODY:
            raise ChannelLimitError("interactive body is longer than 1024 characters")
        if self.kind == "buttons":
            if not 1 <= len(self.buttons) <= MAX_BUTTONS:
                raise ChannelLimitError("reply buttons need 1 to 3 buttons")
            for b in self.buttons:
                if len(b.title) > MAX_BUTTON_TITLE:
                    raise ChannelLimitError(f"button title too long: {b.title!r}")
        if self.kind == "list":
            if not 1 <= len(self.rows) <= MAX_LIST_ROWS:
                raise ChannelLimitError("lists need 1 to 10 rows")
            if len(self.list_button) > MAX_BUTTON_TITLE:
                raise ChannelLimitError("list button label too long")
            for r in self.rows:
                if len(r.title) > MAX_ROW_TITLE or len(r.description) > MAX_ROW_DESCRIPTION:
                    raise ChannelLimitError(f"list row too long: {r.title!r}")
        if self.kind == "carousel":
            if not 2 <= len(self.cards) <= MAX_CARDS:
                raise ChannelLimitError("carousels need 2 to 10 cards")
            if len({len(c.buttons) for c in self.cards}) != 1:
                raise ChannelLimitError("every carousel card needs the same number of buttons")
            for c in self.cards:
                if len(c.body) > MAX_CARD_BODY or c.body.count("\n") > 2:
                    raise ChannelLimitError(f"card text too long: {c.body!r}")
                if not 1 <= len(c.buttons) <= MAX_BUTTONS or any(len(b.title) > MAX_BUTTON_TITLE for b in c.buttons):
                    raise ChannelLimitError("card buttons: 1 to 3, titles up to 20 characters")
            # The list is the fallback when a carousel cannot be sent, so it must be valid too.
            OutMessage("list", self.text, rows=self.rows, list_button=self.list_button).validate()
        return self

    def to_payload(self) -> dict:
        return {
            "kind": self.kind, "text": self.text,
            "buttons": [{"id": b.id, "title": b.title} for b in self.buttons],
            "rows": [{"id": r.id, "title": r.title, "description": r.description} for r in self.rows],
            "list_button": self.list_button, "template_name": self.template_name,
            "template_params": self.template_params, "image_url": self.image_url,
            "image_path": self.image_path,
            "cards": [{"image_url": c.image_url, "image_path": c.image_path, "body": c.body,
                       "buttons": [{"id": b.id, "title": b.title} for b in c.buttons]} for c in self.cards],
        }


def text(body: str) -> OutMessage:
    return OutMessage("text", body).validate()


def buttons(body: str, *items: tuple[str, str], image: tuple[str, str] | None = None) -> OutMessage:
    """Reply buttons, optionally under a photo. `image` is (public URL, site path)."""
    url, path = image or ("", "")
    return OutMessage("buttons", body, buttons=[Button(i, t) for i, t in items], image_url=url,
                      image_path=path).validate()


def menu_list(body: str, rows: list[Row], list_button: str = "Choose") -> OutMessage:
    return OutMessage("list", body, rows=rows, list_button=list_button).validate()


def carousel(body: str, cards: list[Card], fallback_rows: list[Row], list_button: str = "View products") -> OutMessage:
    """Swipeable product cards with photos. `fallback_rows` is the plain list sent if the carousel can't be."""
    return OutMessage("carousel", body, cards=cards, rows=fallback_rows, list_button=list_button).validate()


def template(name: str, params: list[str], preview: str) -> OutMessage:
    return OutMessage("template", preview, template_name=name, template_params=params)


@dataclass
class InboundMessage:
    """A customer message, already parsed from the webhook JSON."""

    message_id: str
    wa_id: str
    name: str
    kind: str  # text, reply, image, document, unsupported
    text: str = ""
    reply_id: str = ""
    media_id: str = ""
    mime_type: str = ""
    timestamp: int = 0


class Channel(ABC):
    name: str

    @abstractmethod
    def send(self, to: str, message: OutMessage) -> str | None:
        """Send a message and return the channel's message id."""

    @abstractmethod
    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        """Return a received file's bytes and content type."""
