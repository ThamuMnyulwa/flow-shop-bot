"""The fake WhatsApp chat (M1). Outbound messages are stored like any other and the simulator page reads them."""

import uuid

from flowshop.channels.base import Channel, OutMessage
from flowshop.storage import get_storage


class SimulatorChannel(Channel):
    name = "simulator"

    def send(self, to: str, message: OutMessage) -> str | None:
        message.validate()
        return f"sim.{uuid.uuid4().hex}"

    def fetch_media(self, media_id: str) -> tuple[bytes, str]:
        # The simulator uploads files to storage first and uses the storage key as the media id.
        key = media_id.removeprefix("sim-media:")
        content_type = "application/pdf" if key.endswith(".pdf") else "image/jpeg"
        if key.endswith(".png"):
            content_type = "image/png"
        return get_storage().get(key), content_type
