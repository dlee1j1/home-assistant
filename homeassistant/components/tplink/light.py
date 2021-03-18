"""Support for TPLink lights."""
from datetime import datetime, timedelta
import logging

from kasa import SmartBulb, SmartDeviceException

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    LightEntity,
)
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util.color import (
    color_temperature_kelvin_to_mired as kelvin_to_mired,
    color_temperature_mired_to_kelvin as mired_to_kelvin,
)

from .common import TPLinkCommon

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=5)

_LOGGER = logging.getLogger(__name__)

ATTR_CURRENT_POWER_W = "current_power_w"
ATTR_DAILY_ENERGY_KWH = "daily_energy_kwh"
ATTR_MONTHLY_ENERGY_KWH = "monthly_energy_kwh"


__platform_async_add_entities__ = None


async def async_setup_entry(hass: HomeAssistantType, config_entry, async_add_entities):
    """Only grab async_add_entities method here. The setup is really done in TPLinkUpdater class."""
    global __platform_async_add_entities__  # pylint: disable=global-statement
    __platform_async_add_entities__ = async_add_entities
    return True


def brightness_to_percentage(byt):
    """Convert brightness from absolute 0..255 to percentage."""
    return round((byt * 100.0) / 255.0)


def brightness_from_percentage(percent):
    """Convert percentage to absolute value 0..255."""
    return round((percent * 255.0) / 100.0)


class TPLinkSmartBulb(TPLinkCommon, LightEntity):
    """Representation of a TPLink Smart Bulb."""

    def __init__(self, smartbulb: SmartBulb) -> None:
        """Initialize the bulb."""
        super().__init__(smartbulb)
        self._is_available = False
        self._min_mireds = None
        self._max_mireds = None
        self._supported_features = None
        self._device_state_attributes = {}

    @property
    def smartbulb(self):
        """Return the device. Reduces changes from previous calls."""
        return self.device

    @property
    def _platform_async_add_entities(self):
        return __platform_async_add_entities__

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        return self._device_state_attributes

    async def try_set(self, coro):
        """Execute a bulb command and handle exceptions gracefully."""
        try:
            await coro
        except SmartDeviceException as ex:
            _LOGGER.error("Unable to change the state: %s", ex)
            self._is_available = False
        else:
            self._is_available = True

    async def async_turn_on(self, **kwargs):
        """Turn the light on."""
        brightness = None

        transition = kwargs.get("transition")
        if transition is not None:
            transition = int(transition * 1_000)
            _LOGGER.debug("Got transition: %s", transition)

        if ATTR_BRIGHTNESS in kwargs:
            brightness = brightness_to_percentage(int(kwargs[ATTR_BRIGHTNESS]))
            _LOGGER.debug("Got brightness: %s", brightness)

        if ATTR_COLOR_TEMP in kwargs:
            color_temp = int(mired_to_kelvin(int(kwargs[ATTR_COLOR_TEMP])))
            _LOGGER.debug("Setting color temp to %s", color_temp)
            return await self.try_set(
                self.smartbulb.set_color_temp(
                    color_temp, brightness=brightness, transition=transition
                )
            )

        elif ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            # Use the existing brightness is no new one is defined
            if brightness is None:
                brightness = brightness_to_percentage(self.brightness)

            _LOGGER.debug("Setting hsv to %s %s %s", int(hue), int(sat), brightness)

            return await self.try_set(
                self.smartbulb.set_hsv(
                    int(hue), int(sat), brightness, transition=transition
                )
            )

        elif brightness is not None and self.smartbulb.is_dimmable:
            return await self.try_set(
                self.smartbulb.set_brightness(brightness, transition=transition)
            )

        else:
            return await self.try_set(self.smartbulb.turn_on(transition=transition))

    async def async_turn_off(self, **kwargs):
        """Turn the light off."""
        transition = kwargs.get("transition")
        if transition is not None:
            transition = int(transition * 1_000)

        return await self.try_set(self.smartbulb.turn_off(transition=transition))

    @property
    def min_mireds(self):
        """Return minimum supported color temperature."""
        return self._min_mireds

    @property
    def max_mireds(self):
        """Return maximum supported color temperature."""
        return self._max_mireds

    @property
    def color_temp(self):
        """Return the color temperature of this light in mireds for HA."""
        if self.smartbulb.color_temp is not None and self.smartbulb.color_temp != 0:
            return kelvin_to_mired(self.smartbulb.color_temp)

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        return brightness_from_percentage(self.smartbulb.brightness)

    @property
    def hs_color(self):
        """Return the color."""
        hue, sat, _ = self.smartbulb.hsv
        return hue, sat

    @property
    def is_on(self):
        """Return True if device is on."""
        return self.smartbulb.is_on

    def update_state_from_device(self):
        """Update light state when tracking device changes."""
        self.update_emeter_state()
        self._supported_features = self.get_light_features()
        self._is_available = True

    async def async_update(self):
        """Update the TP-Link Bulb's state."""
        try:
            await self.smartbulb.update()
            self.update_state_from_device()
            self._last_updated = datetime.now()
        except (SmartDeviceException, OSError) as ex:
            if self._is_available:
                _LOGGER.warning(
                    "Could not read data for %s: %s", self.smartbulb.host, ex
                )
            self._is_available = False

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    def get_light_features(self):
        """Determine all supported features in one go."""
        supported_features = 0

        if self.smartbulb.is_dimmable:
            supported_features += SUPPORT_BRIGHTNESS
        if self.smartbulb.is_variable_color_temp:
            supported_features += SUPPORT_COLOR_TEMP
            self._min_mireds = kelvin_to_mired(
                self.smartbulb.valid_temperature_range[1]
            )
            self._max_mireds = kelvin_to_mired(
                self.smartbulb.valid_temperature_range[0]
            )
        if self.smartbulb.is_color:
            supported_features += SUPPORT_COLOR

        return supported_features

    def update_emeter_state(self):
        """Get the light state."""
        emeter_params = {}

        if self.smartbulb.has_emeter:
            emeter_params[ATTR_CURRENT_POWER_W] = "{:.1f}".format(
                self.smartbulb.emeter_realtime["power"]
            )

            consumption_today = self.smartbulb.emeter_today
            consumption_this_month = self.smartbulb.emeter_this_month
            if consumption_today is not None:
                emeter_params[ATTR_DAILY_ENERGY_KWH] = "{:.3f}".format(
                    consumption_today
                )
            if consumption_this_month is not None:
                emeter_params[ATTR_MONTHLY_ENERGY_KWH] = "{:.3f}".format(
                    consumption_this_month
                )

        self._device_state_attributes = emeter_params
