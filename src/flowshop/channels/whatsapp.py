"""The WhatsApp Cloud API channel through PyWa (L1). PyWa is used for sending and media only.

Webhooks are received by our own endpoint, so the simulator and WhatsApp share one parser and one
de-duplication rule.
"""

import logging

from pywa import WhatsApp
from pywa.types import Button, Section, SectionList, SectionRow
from pywa.types.templates import TemplateLanguage

from flowshop.channels.base import Channel, OutMessage
from flowshop.config import Settings
from flowshop.storage import get_storage

log = logging.getLogger(__name__)


class WhatsAppChannel(Channel):
    name = "whatsapp"

    def __init__(self, settings: Settings, client: WhatsApp | None = None):
        self.settings = settings
        self.client = client or WhatsApp(phone_id=settings.wa_phone_id, token=settings.wa_token)

    def send(self, to: str, message: OutMessage) -> str | None:
        message.validate()
        if message.kind == "text":
            sent = self.client.send_message(to=to, text=message.text)
        elif message.kind == "buttons" and message.image_path:
            try:
                # Upload the photo file itself rather than sending a link: an upload fails at once if
                # something is wrong, while a link Meta cannot fetch fails later, after we have moved on.
                key = message.image_path.removeprefix("/api/images/")
                data = get_storage().get(key)
                sent = self.client.send_image(
                    to=to, image=data, mime_type="image/png" if key.endswith(".png") else "image/jpeg",
                    caption=message.text,
                    buttons=[Button(title=b.title, callback_data=b.id) for b in message.buttons],
                )
            except Exception:
                # The customer still needs the text and buttons, so send them without the photo.
                log.exception("photo message failed, sending without the photo: %s", message.image_path)
                sent = self._send_buttons(to, message)
        elif message.kind == "buttons":
            sent = self._send_buttons(to, message)
        elif message.kind == "list":
            rows = [SectionRow(title=r.title, callback_data=r.id, description=r.description or None)
                    for r in message.rows]
            sent = self.client.send_message(
                to=to, text=message.text,
                buttons=SectionList(button_title=message.list_button,
                                    sections=[Section(title=message.section_title, rows=rows)]),
            )
        elif message.kind == "template":
            body = [{"type": "text", "text": p} for p in message.template_params]
            components = [{"type": "body", "parameters": body}]
            sent = self.client.send_template(
                to=to, name=message.template_name,
                language=TemplateLanguage(self.settings.wa_template_language), params=components,
            )
        else:
            raise ValueError(f"unknown message kind {message.kind}")
        return getattr(sent, "id", None)

    def _send_buttons(self, to: str, message: OutMessage):
        return self.client.send_message(
            to=to, text=message.text, buttons=[Button(title=b.title, callback_data=b.id) for b in message.buttons]
        )

    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        media = self.client.get_media_url(media_id)
        return self.client.get_media_bytes(media.url), media.mime_type
