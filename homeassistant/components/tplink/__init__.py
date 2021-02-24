"""Component to embed TP-Link smart home devices."""
import logging

from homeassistant import config_entries
from homeassistant.helpers.typing import HomeAssistantType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIG = "config"


async def async_setup(hass: HomeAssistantType, config):
    """Set up this module."""
    conf = config.get(DOMAIN)

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][ATTR_CONFIG] = conf

    if conf is not None:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
            )
        )

    return True


async def async_setup_entry(hass, config):
    """Forward the set up to the other platforms."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config, "light")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config, "switch")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(config, "binary_sensor")
    )

    return True


async def async_unload_entry(hass, entry):
    """Forward the unload entry."""
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
