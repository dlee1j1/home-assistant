"""Config flow for TP-Link."""
from homeassistant import config_entries
from homeassistant.helpers import config_entry_flow

# from .common import async_get_discoverable_devices
from .const import DOMAIN

async def updater(hass):
    return ["updater"]

config_entry_flow.register_discovery_flow(
    DOMAIN,
    "TP-Link Smart Home",
#    async_get_discoverable_devices,
#    Discover.discover(),
    updater,
    config_entries.CONN_CLASS_LOCAL_POLL,
)
