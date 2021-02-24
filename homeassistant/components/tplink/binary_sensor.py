"""This is the updater for tplink."""

from datetime import datetime, timedelta
import logging
from typing import Dict

from kasa import (
    Discover,
    SmartBulb,
    SmartDevice,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
)
import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import CONF_HOST
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import HomeAssistantType

from .common import TPLinkCommon
from .const import (
    DOMAIN,
    MIN_TIME_BETWEEN_DISCOVERS,
    MIN_TIME_BETWEEN_UPDATES,
    STARTUP_COOLDOWN_TIME,
)
from .light import TPLinkSmartBulb
from .switch import TPLinkSmartPlugSwitch

ATTR_CONFIG = "config"
CONF_DIMMER = "dimmer"
CONF_DISCOVERY = "discovery"
CONF_DISCOVERY_BROADCAST_DOMAIN = "discovery-broadcast-domain"
CONF_LIGHT = "light"
CONF_STRIP = "strip"
CONF_SWITCH = "switch"
CONF_LIGHTSTRIP = "lightstrip"

_LOGGER = logging.getLogger(__name__)

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
                vol.Optional(
                    CONF_DISCOVERY_BROADCAST_DOMAIN, default="255.255.255.255"
                ): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SCAN_INTERVAL = timedelta(seconds=1)


async def async_setup_entry(hass: HomeAssistantType, config_entry, async_add_entities):
    """Set up the TP-Link platform."""
    config_data = hass.data[DOMAIN].get(ATTR_CONFIG)

    entities = {}
    broadcast_domain = "255.255.255.255"

    # find the static config entities
    if config_data is not None:
        entities = add_static_devices(config_data)
        broadcast_domain = config_data.get(
            CONF_DISCOVERY_BROADCAST_DOMAIN, broadcast_domain
        )

    # add the updater
    hass.data[DOMAIN][CONF_DISCOVERY_BROADCAST_DOMAIN] = broadcast_domain
    updater = TPLinkUpdater(broadcast_domain, entities)
    async_add_entities([updater])
    hass.data[DOMAIN][CONF_HOST] = entities
    hass.data[DOMAIN]["updater"] = updater

    return True


def add_static_devices(config_data) -> Dict[str, TPLinkCommon]:
    """Get statically defined devices in the config."""
    _LOGGER.debug("Getting static devices")
    entities = {}

    for type_ in [CONF_LIGHT, CONF_SWITCH, CONF_STRIP, CONF_DIMMER, CONF_LIGHTSTRIP]:
        for entry in config_data.get(type_, []):
            host = entry.get("host")
            if host is None:
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

            if new_entity:
                entities[host] = new_entity
    return entities


class TPLinkUpdater(BinarySensorEntity):
    """Update TPLimk SmartBulb and SmartSwitches entities using the Kasa discovery protocol."""

    def __init__(self, broadcast_domain, static_entities: Dict[str, TPLinkCommon]):
        """Initialize me."""
        self._broadcast_domain = broadcast_domain
        self._entities = static_entities
        self._static_entities = list(static_entities.values())
        self._last_updated = datetime.min
        self._last_static_check = None
        self._first_discovery_done = False
        self._start_time = datetime.now()

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

    def schedule_discovery(self):
        """Ask HASS to schedule a single discovery call."""
        self.hass.async_create_task(
            Discover.discover(
                target=self._broadcast_domain, on_discovered=self.update_from_discovery
            )
        )

    async def async_update(self):
        """Kicks off another set of discoveries if it's been a while. Otherwise, it waits for the next tick."""
        time = datetime.now()
        if time - self._start_time < STARTUP_COOLDOWN_TIME:
            # Wait a little bit before we aggressively update the switches so start up can finish. Otherwise,
            # HomeAssistant will think it is not yet done bootstrapping
            if not self._first_discovery_done:
                # do the first time discovery
                self.schedule_discovery()
                self._first_discovery_done = True
            return

        # kick off the discovery cycle but we wait for the devices to have gone silent for a while
        if time - self._last_updated > MIN_TIME_BETWEEN_DISCOVERS:
            self.schedule_discovery()

        # check each of the static entries, if they haven't updated through UDP, force a TCP update
        if self._last_static_check is None:
            self._last_static_check = time

        if time - self._last_static_check > MIN_TIME_BETWEEN_UPDATES:
            # check static devices only every 5 seconds
            for entity in self._static_entities:
                entity.check_forced_update(time)
            self._last_static_check = time

    def create_entity_from_discovery(self, device: SmartDevice, is_child=False):
        """Create a device entity from discovery.

        Note that the entity is not added to platform in this step but rather
        in the update step.
        We add to the platform later for two reasons:
          (1) static entities may never be found; and
          (2) we discover devices in the TPLinkUpdater but the light and switch platforms may
            not yet have been set up by the time the first discovery call is executed.
        """
        if device.is_plug:
            entity = TPLinkSmartPlugSwitch(device, is_child=False)
        elif device.is_dimmer or device.is_bulb or device.is_lightstrip:
            entity = TPLinkSmartPlugSwitch(device)
        elif device.is_strip:
            children = [
                self.create_entity_from_discovery(plug, is_child=True)
                for plug in device.children
            ]
            entity = TPLinkSmartPlugSwitch(device, children=children)
            _LOGGER.debug("Found strip %s with %s children", device, len(children))
        else:
            _LOGGER.error("Unknown smart device type: %s", device.device_type)
            return
        self._entities[device.host] = entity
        return entity

    async def update_from_discovery(self, device: SmartDevice):
        """Update entities based on replies from discovery broadcast request. Called each time the discovery prototocol gets an update for a device."""
        self._last_updated = datetime.now()

        entity = self._entities.get(device.host)

        # create entity if it's not there yet
        if entity is None:
            entity = self.create_entity_from_discovery(device)

        entity.update_device(device)
        if device.is_strip:
            for plug in device.children:
                plug.update_from_discovery(plug)
