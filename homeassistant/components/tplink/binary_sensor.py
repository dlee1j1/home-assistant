"""Common code for tplink."""
import asyncio
from dataclasses import dataclass
from datetime import timedelta, datetime
now = datetime.now

import logging
from typing import Any, Awaitable, Callable, List, Dict
import voluptuous as vol

from kasa import (
    Discover,
    SmartBulb,
    SmartLightStrip,
    SmartDevice,
    SmartDeviceException,
    SmartDimmer,
    SmartPlug,
    SmartStrip,
)

from .light import TPLinkSmartBulb
from .switch import TPLinkSmartPlugSwitch
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import Entity

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv

from homeassistant.helpers.typing import ConfigType, HomeAssistantType

_LOGGER = logging.getLogger(__name__)

from .const import DOMAIN, LIGHTS_REMAINING, SWITCHES_REMAINING


ATTR_CONFIG = "config"
CONF_DIMMER = "dimmer"
CONF_DISCOVERY = "discovery"
CONF_DISCOVERY_BROADCAST_DOMAIN = "discovery-broadcast-domain"
CONF_LIGHT = "light"
CONF_STRIP = "strip"
CONF_SWITCH = "switch"
CONF_LIGHTSTRIP = "lightstrip"




TPLINK_HOST_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_LIGHT, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_SWITCH, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_STRIP, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_DIMMER, default=[]): vol.All(
                    cv.ensure_list, [TPLINK_HOST_SCHEMA]
                ),
                vol.Optional(CONF_DISCOVERY, default=True): cv.boolean,
                vol.Optional(CONF_DISCOVERY_BROADCAST_DOMAIN, default="255.255.255.255"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SCAN_INTERVAL = timedelta(seconds=1)

async def async_setup_entry(hass: HomeAssistantType, config_entry, async_add_entities):
    """Set up the TP-Link platform."""
    config_data = hass.data[DOMAIN].get(ATTR_CONFIG)

    # find the static config entities 
    hass.data[DOMAIN][LIGHTS_REMAINING] = []
    hass.data[DOMAIN][SWITCHES_REMAINING] = []

    entities = {}
    broadcast_domain = "255.255.255.255"
    if config_data is not None:
        entities = add_static_devices(config_data)
        broadcast_domain = config_data.get(CONF_DISCOVERY_BROADCAST_DOMAIN,"255.255.255.255")

    # add the updater
    hass.data[DOMAIN][CONF_DISCOVERY_BROADCAST_DOMAIN] = broadcast_domain
    updater = TPLinkUpdater(config_data,broadcast_domain,entities)
    async_add_entities([updater])
    hass.data[DOMAIN][CONF_HOST] = entities
    hass.data[DOMAIN]["updater"] = updater

    return True


def add_static_devices(config_data) -> Dict[str,Entity]:
    """Get statically defined devices in the config."""
    _LOGGER.debug("Getting static devices")
    entities = {}

    for type_ in [CONF_LIGHT, CONF_SWITCH, CONF_STRIP, CONF_DIMMER, CONF_LIGHTSTRIP]:
        for entry in config_data.get(type_,[]):
            host = entry.get("host")
            if (host is None):
                continue

            new_entity = None 

            if type_ == CONF_LIGHT:
                new_entity = TPLinkSmartBulb(SmartBulb(host))
            elif type_ == CONF_SWITCH:
                new_entity = TPLinkSmartPlugSwitch(SmartPlug(host))
            elif type_ == CONF_STRIP:
                new_entity = TPLinkSmartPlugSwitch(SmartStrip(host))
            elif type_ == CONF_DIMMER:
                new_entity = TPLinkSmartBulb(SmartDimmer(host))
            elif type_ == CONF_LIGHTSTRIP:
                new_entity = TPLinkSmartBulb(SmartLightStrip(host))

            if (new_entity):
                entities[host] = new_entity
    return entities


class TPLinkUpdater(BinarySensorEntity):
    """Update TPLimk SmartBulb and SmartSwitches entities using the discovery protocol"""

    def __init__(self,config,broadcast_domain,static_entities:Dict[str,Entity]):
        self._config = config
        self._broadcast_domain = broadcast_domain
        self._entities = static_entities
        self._last_updated = datetime.min
    
    @property
    def name(self) -> str:
        """Return the name of the binary sensor, if any."""
        return "TPLinkUpdater"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return "tplink-updater"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self._last_updated == datetime.min:
            return False
        return True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        avail = self._last_updated != datetime.min
        return avail

    # TODO: check on static devices and force an update if they haven't done it in a while
    async def async_update(self):
        """Checks when the last update happened. If it's been a while, kicks off a new round. Otherwise, it waits for the next tick"""
        time_since_last_updated:timedelta = now() - self._last_updated
        if time_since_last_updated.total_seconds() > 1:
            # kick off the discovery cycle
            self.hass.async_create_task(Discover.discover(target=self._broadcast_domain,on_discovered=self.update_from_discovery))

    async def update_from_discovery(self,device:SmartDevice):
        """This is called every time the discovery prototocol gets an update.""" 
        self._last_updated = now()

        entity = self._entities.get(device.host)

        # create entity if it's not there yet 
        if (entity is None):
            if device.is_strip or device.is_plug:
                entity = TPLinkSmartPlugSwitch(device)
            elif device.is_dimmer or device.is_bulb or device.is_lightstrip:
                entity = TPLinkSmartPlugSwitch(device)
            else:
                _LOGGER.error("Unknown smart device type: %s", dev.device_type)
                return
            self._entities[device.host] = entity
        
        entity.update_device(device)
        
