"""
Support for the SamyGO web interface.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.samygo/
"""
import voluptuous as vol
import logging
import requests
from collections import defaultdict

from homeassistant.components.media_player import (
    MEDIA_TYPE_CHANNEL, MEDIA_TYPE_TVSHOW, MEDIA_TYPE_VIDEO, SUPPORT_PAUSE, SUPPORT_PLAY_MEDIA,
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_STOP, PLATFORM_SCHEMA,
    SUPPORT_NEXT_TRACK, SUPPORT_PREVIOUS_TRACK, SUPPORT_PLAY, SUPPORT_SELECT_SOURCE,
    SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_STEP, SUPPORT_VOLUME_SET,
    DOMAIN,
    MediaPlayerDevice)
from homeassistant.const import (
    CONF_HOST, CONF_PORT, CONF_NAME, CONF_TOKEN, STATE_ON, STATE_OFF)
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = []

DEFAULT_NAME = 'SamyGO TV'
DEFAULT_PORT = 1080

SUPPORT_SAMYGO = SUPPORT_TURN_ON | SUPPORT_TURN_OFF | \
    SUPPORT_PREVIOUS_TRACK | SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_STEP | \
    SUPPORT_NEXT_TRACK | SUPPORT_PREVIOUS_TRACK


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=1080): cv.positive_int,
    vol.Required(CONF_TOKEN): cv.string,

})

_LOGGER = logging.getLogger(__name__)

DATA_SAMYGO = "samygo"

SEND_KEY_SCHEMA = vol.Schema({
    vol.Optional("key"): str,
})

SERVICE_SEND_KEY = "samygo_send_key"
SERVICE_REBOOT = "samygo_reboot"

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the SamyGO platform."""
    dev = SamyGODevice(config[CONF_NAME], config[CONF_HOST],
                       config[CONF_PORT], config[CONF_TOKEN])

    if DATA_SAMYGO not in hass.data:
        hass.data[DATA_SAMYGO] = []

    hass.data[DATA_SAMYGO].append(dev)

    add_devices(hass.data[DATA_SAMYGO])


    def service_handle(service):
        """Handle for services."""
        entity_ids = service.data.get('entity_id')

        if entity_ids:
            devices = [device for device in hass.data[DATA_SAMYGO]
                       if device.entity_id in entity_ids]
        else:
            devices = hass.data[DATA_SAMYGO]

        for device in devices:
            if service.service == SERVICE_REBOOT:
                device.reboot()
            elif service.service == SERVICE_SEND_KEY:
                device.send_key(**service.data)

            device.schedule_update_ha_state(True)

    hass.services.register(
        DOMAIN,
        SERVICE_REBOOT,
        service_handle,
        {'description':"Reboot device"})
    hass.services.register(
        DOMAIN,
        SERVICE_SEND_KEY,
        service_handle,
        {'description': "Send key"},
        schema=SEND_KEY_SCHEMA)

    return True


class SamyGODevice(MediaPlayerDevice):
    """Representation of a SamyGO TV."""

    def __init__(self, name, host, port, secret):
        """Initialize the device."""

        self._baseurl = "http://%s:%s/cgi-bin/samygo-web-api.cgi" % (host, port)
        self._name = name
        self._secret = secret
        self._is_on = None
        self._current = None
        self._info = defaultdict(lambda: None)
        self._timeout = 2

    def fetch(self, parameters):
        parameters.update({
            "challenge": self._secret})
        try:
            res = requests.get(self._baseurl, parameters, timeout=self._timeout).json()
            _LOGGER.debug("Received: %s" % res)
            return res
        except requests.ConnectionError as ex:
            _LOGGER.debug("Got a connection error, device unavailable: %s" % ex)
            return {}

    def reboot(self):
        """Reboot the device."""
        return self.fetch({"action": "REBOOT"})

    def send_key(self, key):
        """Send a command to the device."""
        return self.fetch({"action": "KEY", "key": key})

    def update(self):
        """Retrieve latest state."""
        self._info = self.fetch({"action": "CHANNELINFO"})

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_SAMYGO

    @property
    def state(self):
        """Return the state of the device."""
        if self._info is not None and len(self._info) > 0:
            return STATE_ON
        return STATE_OFF

    @property
    def source(self):
        """Return currently used source."""
        return self._info["source"]

    @property
    def volume_level(self):
        """Return the current volume level."""
        if self._info["volume"] is None:
            return None
        if "(mute)" in self._info["volume"]:
            return self._info["volume"].split(" ")[0]
        else:
            return self._info["volume"]

    @property
    def is_volume_muted(self):
        """Return whether volume is muted or not."""
        if self._info["volume"] is None:
            return None
        return "mute" in self._info["volume"]

    @property
    def media_title(self):
        """Return the title of current playing media."""
        if self._info["program_name"] is None:
            return None

        if "Non-TV" in self._info["program_name"]:
            return self.source

        return self._info["program_name"]

    @property
    def media_channel(self):
        """Return the channel current playing media."""
        return self._info["channel_name"]

    def turn_on(self):
        """Turn on the receiver."""
        self.send_key("KEY_POWERON")

    def turn_off(self):
        """Turn off the receiver."""
        self.send_key("KEY_POWEROFF")

    def volume_up(self):
        """Turn volume up."""
        self.send_key("KEY_VOLUP")

    def volume_down(self):
        """Turn volume down."""
        self.send_key("KEY_VOLDOWN")

    def mute_volume(self, mute):
        """Toggle mute."""
        self.send_key("KEY_MUTE")

    def media_play(self):
        self.send_key("KEY_PLAY")

    def media_pause(self):
        self.send_key("KEY_PAUSE")

    def media_stop(self):
        self.send_key("KEY_STOP")
