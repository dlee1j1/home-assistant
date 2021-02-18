from abc import ABC,abstractclassmethod,abstractproperty
"""Common code for TPLink"""

from homeassistant.helpers.entity import Entity
from datetime import timedelta, datetime
import homeassistant.helpers.device_registry as dr
from kasa import (
    SmartDevice
)

class TPLinkCommon(Entity):
    """class for Common methods for TPLink Kasa smart devices"""
    def __init__(self,device:SmartDevice):
        self._last_updated = datetime.min
        self._added_to_platform = False
        self.device = device

    @abstractproperty
    def _platform_async_add_entities(self):
        """Returns the function to be used to add this entity 
            to the specific HA platform that the entity belongs.
        """
        pass

    @abstractclassmethod
    def update_state_from_device(self):
        """This method should update the state of the device
            when the tracking device changes. 
            This is its own method so we can call the same method whether
            the device is updated by an explicit update call or from a UDP discovery call.
        """
        pass

    def add_self_to_platform(self):
        """ Add this entity to its platform."""
        async_add_entities = self._platform_async_add_entities
        if (not self._added_to_platform) and (async_add_entities is not None):
            # First time we have an update for this entity 
            # so add ourselves to the platform
            self._added_to_platform = True
            async_add_entities([self])

    def update_device(self,device: SmartDevice):
        """Set the tracking device for this entity to be the newly minted device from 
            the discovery call replacing the previous device instance.
            This is the call that sets the state of the device. 
            We also check here if we'this entity has been added to the platform. 
            We add the entity here rather than outside so we can accomodate late discoveries.     
        """
        self.device = device
        self.update_state_from_device()
        self._last_updated = datetime.now()
        self.add_self_to_platform()

        if self.hass is not None:
            # we could have fired the signal to add ourselves to the platform
            # but that might not have executed yet so we check self.hass instad of self._added_to_platform
            self.async_write_ha_state()

    def check_forced_update(self,now:datetime):
        """check when the last time this got updated. 
            If it's more than 5-seconds, we force an update through a direct TCP call in case UDP packets are getting lost.
        """
        time_since_last_update = now - self._last_updated
        if (time_since_last_update.total_seconds() > 5):
            self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def should_poll(self) -> bool:
        """The device update now happens in TPLinkUpdater so we don't poll the individual devices.
        """
        return False

    @property
    def available(self) -> bool:
        """Return if devuce is available."""
        time_since_last_updated = datetime.now() - self._last_updated
        return time_since_last_updated.total_seconds() < 60

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.device.mac

    @property
    def name(self):
        """Return the name of the Smart Bulb."""
        return self.device.alias

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "name": self.device.alias,
            "model": self.device.model,
            "manufacturer": "TP-Link",
            "connections": {(dr.CONNECTION_NETWORK_MAC, self.device.mac)},
            "sw_version": self.device.sys_info["sw_ver"],
        }

