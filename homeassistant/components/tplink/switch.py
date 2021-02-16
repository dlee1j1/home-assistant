"""Support for TPLink HS100/HS110/HS200 smart switch."""
import logging
from typing import Union

from kasa import SmartDeviceException, SmartPlug, SmartStrip
from datetime import datetime, timedelta
from homeassistant.components.switch import (
    ATTR_CURRENT_POWER_W,
    ATTR_TODAY_ENERGY_KWH,
    SwitchEntity,
)
from homeassistant.const import ATTR_VOLTAGE
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.typing import HomeAssistantType

from .const import DOMAIN, SWITCHES_REMAINING
_LOGGER = logging.getLogger(__name__)

ATTR_TOTAL_ENERGY_KWH = "total_energy_kwh"
ATTR_CURRENT_A = "current_a"


async def add_entity_OLD(device: Union[SmartPlug, SmartStrip], async_add_entities):
    """Check if device is online and add the entity."""
    # Attempt to get the sysinfo. If it fails, it will raise an
    # exception that is caught by async_add_entities_retry which
    # will try again later.
    await device.update()

    entities = []
    if device.is_strip:
        children = [
            SmartPlugSwitch(plug, should_poll=False) for plug in device.children
        ]
        _LOGGER.debug("Found strip %s with %s children", device, len(children))
        entities.extend(children)
        strip = SmartPlugSwitch(device, children=children)
        entities.append(strip)
    else:
        entities.append(SmartPlugSwitch(device))

    _LOGGER.debug("Adding switch entities: %s", entities)
    async_add_entities(entities, update_before_add=True)

__platform_async_add_entities__ = None

async def async_setup_entry(hass: HomeAssistantType, config_entry, async_add_entities):
    """Grab async_add_entities from here."""
    global __platform_async_add_entities__
    __platform_async_add_entities__ = async_add_entities


    return True

# TODO: Deal with Children
class TPLinkSmartPlugSwitch(SwitchEntity):
    """Representation of a TPLink Smart Plug switch."""

    def __init__(self, smartplug: SmartPlug, children=None, should_poll=True):
        """Initialize the switch."""
        self.smartplug = smartplug
        self._is_available = False
        self._emeter_params = {}
        self._should_poll = should_poll
        self._children = children or []
        self._is_on = False
        self._last_updated = datetime.min
        self._added_to_platform = False

    def add_self_to_platform(self):
        if (not self._added_to_platform) and (__platform_async_add_entities__ is not None):
            # First time we have an update for this entity 
            # so add ourselves to the platform
            self._added_to_platform = True
            __platform_async_add_entities__([self])

    def update_device(self,device: SmartPlug):
        self.smartplug = device
        self._last_updated = datetime.now()
        self.update_self_from_device()
        self.add_self_to_platform()

        if self.hass is not None:
            # we could have fired the signal to add ourselves to the platform
            #  but that might not have fired yet so we check self.hass instad of self._added_to_platform
            self.async_write_ha_state()

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        Only parent devices need to be polled for smart strips.
        """
        return False


    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.smartplug.device_id

    @property
    def name(self):
        """Return the name of the Smart Plug."""
        return self.smartplug.alias

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "name": self.smartplug.alias,
            "model": self.smartplug.model,
            "manufacturer": "TP-Link",
            "connections": {(dr.CONNECTION_NETWORK_MAC, self.smartplug.mac)},
            "sw_version": self.smartplug.sys_info["sw_ver"],
        }

    @property
    def available(self) -> bool:
        """Return if switch is available."""
        time_since_last_updated = datetime.now() - self._last_updated
        return time_since_last_updated.total_seconds() < 60

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
    
    def update_self_from_device(self):
        self._is_on = self.smartplug.is_on

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

        # XXX TODO: deal with children!

    async def async_update(self):
        """Update the TP-Link switch's state."""
        try:
            if self.should_poll:
                _LOGGER.debug("Polling device: %s", self.name)
                await self.smartplug.update()
            update_self_from_device()
            self._is_available = True

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
