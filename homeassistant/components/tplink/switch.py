"""Support for TPLink HS100/HS110/HS200 smart switch."""
from datetime import datetime
import logging
from typing import Union

from kasa import SmartDeviceException, SmartPlug, SmartStrip

from homeassistant.components.switch import (
    ATTR_CURRENT_POWER_W,
    ATTR_TODAY_ENERGY_KWH,
    SwitchEntity,
)
from homeassistant.const import ATTR_VOLTAGE
from homeassistant.helpers.typing import HomeAssistantType

from .common import TPLinkCommon

_LOGGER = logging.getLogger(__name__)

ATTR_TOTAL_ENERGY_KWH = "total_energy_kwh"
ATTR_CURRENT_A = "current_a"

__platform_async_add_entities__ = None


async def async_setup_entry(hass: HomeAssistantType, config_entry, async_add_entities):
    """Retrieve async_add_entities method here. The setup is done in TPLinkUpdater class."""
    global __platform_async_add_entities__  # pylint: disable=global-statement
    __platform_async_add_entities__ = async_add_entities

    return True


class TPLinkSmartPlugSwitch(TPLinkCommon, SwitchEntity):
    """Representation of a TPLink Smart Plug switch."""

    def __init__(
        self, smartplug: Union[SmartPlug, SmartStrip], children=None, is_child=False
    ):
        """Initialize the switch."""
        super().__init__(smartplug)
        self._is_available = False
        self._emeter_params = {}
        self._should_poll = not is_child
        self._children = children or []
        self._is_on = False

    @property
    def smartplug(self):
        """Wrap smartplug property for backward compatibility."""
        return self.device

    @property
    def _platform_async_add_entities(self):
        return __platform_async_add_entities__

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self.smartplug.turn_on()
        self._is_on = True
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self.smartplug.turn_off()
        self._is_on = False
        self.schedule_update_ha_state()

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        return self._emeter_params

    def update_state_from_device(self):
        """Update internal state from the device object the entity points to."""
        self._is_on = self.smartplug.is_on
        self._is_available = True

        if self.smartplug.has_emeter:
            emeter_readings = self.smartplug.emeter_realtime

            self._emeter_params[ATTR_CURRENT_POWER_W] = "{:.2f}".format(
                emeter_readings["power"]
            )
            self._emeter_params[ATTR_TOTAL_ENERGY_KWH] = "{:.3f}".format(
                emeter_readings["total"]
            )
            self._emeter_params[ATTR_VOLTAGE] = "{:.1f}".format(
                emeter_readings["voltage"]
            )
            self._emeter_params[ATTR_CURRENT_A] = "{:.2f}".format(
                emeter_readings["current"]
            )

            consumption_today = self.smartplug.emeter_today
            if consumption_today is not None:
                self._emeter_params[ATTR_TODAY_ENERGY_KWH] = consumption_today

    async def async_update(self):
        """Update the TP-Link switch's state."""
        try:
            if self.should_poll:
                _LOGGER.debug("Polling device: %s", self.name)
                await self.smartplug.update()
            self.update_state_from_device()
            self._last_updated = datetime.now

        except (SmartDeviceException, OSError) as ex:
            if self._is_available:
                _LOGGER.warning(
                    "Could not read state for %s: %s", self.smartplug.host, ex
                )
            self._is_available = False

            return

        if self._children:
            _LOGGER.debug(
                "Going to update %s children of %s", len(self._children), self.name
            )
            for child in self._children:
                child.async_schedule_update_ha_state(force_refresh=True)
