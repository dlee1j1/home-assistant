"""Component to embed TP-Link smart home devices."""
import asyncio
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
from .const import DOMAIN
import logging
_LOGGER = logging.getLogger(__name__)


ATTR_CONFIG = "config"


async def async_setup(hass: HomeAssistantType, config):
    _LOGGER.debug("In async_setup")
    conf = config.get(DOMAIN)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][ATTR_CONFIG] = conf

    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
            )
        )

#    hass.async_create_task(
#        discovery.async_load_platform(hass, "binary_sensor", DOMAIN, ["updater"], config)
#    )
    _LOGGER.debug("Done with async_setup")
    return True

async def async_setup_entry(hass,config):
    # hass.async_create_task(hass.config_entries.async_forward_entry_setup(config,"common"))
    _LOGGER.debug("In async setup entry")
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(config,"light"))
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(config,"switch"))
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(config,"binary_sensor"))

    return True


async def async_unload_entry(hass, entry):
    forward_unload = hass.config_entries.async_forward_entry_unload
    remove_lights = remove_switches = remove_updater = False

    remove_lights = await forward_unload(entry, "light")
    remove_switches = await forward_unload(entry, "switch")
    remove_switches = await forward_unload(entry, "binary_sensor")

    if remove_lights and remove_switches and remove_updater:
        hass.data[DOMAIN].clear()
        return True
    else:
        # We were not able to unload the platforms, because
        # one of the forward_unloads failed.
        return False
