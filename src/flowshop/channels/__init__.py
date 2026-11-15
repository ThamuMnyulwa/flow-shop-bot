from functools import lru_cache

from flowshop.channels.base import Channel
from flowshop.config import get_settings

_override: Channel | None = None


@lru_cache
def _configured() -> Channel:
    settings = get_settings()
    if settings.channel == "whatsapp":
        from flowshop.channels.whatsapp import WhatsAppChannel

        return WhatsAppChannel(settings)
    from flowshop.channels.simulator import SimulatorChannel

    return SimulatorChannel()


def get_channel() -> Channel:
    return _override or _configured()


def set_channel(channel: Channel | None) -> None:
    """Swap the channel, for tests."""
    global _override
    _override = channel
