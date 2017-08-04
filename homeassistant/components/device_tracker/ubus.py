"""
Support for OpenWRT (ubus) routers.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/device_tracker.ubus/
"""
import logging
import attr
from pprint import pformat as pf
from typing import Dict, List

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.device_tracker import (
    DOMAIN, PLATFORM_SCHEMA, DeviceScanner)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME


_LOGGER = logging.getLogger(__name__)

#REQUIREMENTS = ['https://github.com/rytilahti/python-ubus/archive/master.zip#ubus==0.0.0']

CONF_LEASE_FILE = "lease_file"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Optional(CONF_LEASE_FILE, default=None): cv.string,
})


@attr.s
class Lease:
    """Represents a lease."""
    expires = attr.ib(repr=False)
    mac = attr.ib()
    ip = attr.ib()
    hostname = attr.ib()
    client_id = attr.ib(repr=False)


def get_scanner(hass, config):
    """Validate the configuration and return an ubus scanner."""
    scanner = UbusDeviceScanner(config[DOMAIN])

    return scanner if scanner.success_init else None


class UbusDeviceScanner(DeviceScanner):
    """
    This class queries a wireless router running OpenWrt or LEDE firmware
    over ubus' JSON-RPC interface.

    Requires the following rpcd ACLs:
    * hostapd.* ["get_clients"]
    * dhcp ["ipv4leases", "ipv6leases"] (optional for odhcp support)
    * file ["read"] (required if no lease file configuration option is given)

    Adapted (long ago) from Tomato scanner.
    """

    def __init__(self, config):
        """Initialize the scanner."""
        from ubus import Ubus
        host = config[CONF_HOST]
        self.username = config[CONF_USERNAME]
        self.password = config[CONF_PASSWORD]
        self.lease_file = config[CONF_LEASE_FILE]

        self.ubus = Ubus(host, self.username, self.password)  # type: Ubus
        with self.ubus:
            self.success_init = self.ubus.is_valid_session()

    def _parse_clients(self, data):
        clients = {}
        if "clients" in data:
            for mac, info in data["clients"].items():
                clients[mac] = info
        else:
            _LOGGER.warning("No 'clients' key in data")

        # use only connected clients
        clients = {k:v for k,v in clients.items() if v["authorized"]}

        return clients

    def _get_connected_devices(self) -> Dict[str, Dict]:
        """Return a list of devices connected over wifi."""
        from ubus import UbusException

        clients = {}
        try:
            for iface in self.ubus:
                if iface.name.startswith("hostapd"):
                    clients.update(self._parse_clients(iface["get_clients"]()))

            _LOGGER.debug("Total %s connected devices: %s", len(clients), pf(clients))
        except UbusException as ex:
            _LOGGER.error("Unable to read connected devices: %s", ex)

        return clients

    def _parse_odhcpd_leases(self, data) -> Dict[str, Lease]:
        """Parse leases out from odhcpd's result structure.."""
        leases = {}
        def _format_mac(mac):
            """from https://stackoverflow.com/a/3258596"""
            return ':'.join(a+b for a,b in zip(mac[::2], mac[1::2])).upper()
        for iface, values in data.items():
            for vlist in values.values():
                for lease in vlist:
                    mac = _format_mac(lease['mac'])
                    leases[mac] = Lease(mac=mac,
                                        ip=lease["ip"],
                                        expires=lease["valid"],
                                        hostname=lease["hostname"],
                                        client_id=None)
                    _LOGGER.warning("odhcpd lease: %s", lease)

        return leases

    def _get_odhcpd_leases(self) -> Dict[str, Lease]:
        """Return a dict of active odhcpd leases."""
        leases = {}
        _LOGGER.warning("odhcpd not supported, please report the lines below")
        lease_methods = ["ipv4leases", "ipv6leases"]
        for lease_method in lease_methods:
            for dev in self.ubus["dhcp"][lease_method]().values():
                _LOGGER.warning("RAW lease output, please report: %s", dev)
                return
                _parse_odhcp_leases(dev)

        return leases

    def _get_lease_files(self) -> List[str]:
        """Find dnsmasq lease files."""
        dhcp_config = self.ubus["uci"]["get"](config="dhcp", type="dnsmasq")
        lease_files = [x["leasefile"] for x in dhcp_config["values"]]
        return lease_files

    def _get_dnsmasq_leases(self, lease_file) -> Dict[str, Lease]:
        """Return dnsmasq leases from a given file."""
        leases = {}
        currently_leased = self.ubus["file"]["read"](path=lease_file)
        if "data" not in currently_leased:
            _LOGGER.error("Unable to read the leases file %s", lease_file)
            return leases

        for lease_line in currently_leased["data"].splitlines():
            lease = Lease(*lease_line.split(" "))
            leases[lease.mac.upper()] = lease

        return leases

    def _get_leases(self) -> Dict[str, Lease]:
        """Return a mapping of all active leases."""
        from ubus import UbusException

        leases = {}
        try:
            if "dhcp" in self.ubus:
                leases.update(self._get_odhcpd_leases())
            if self.lease_file is None:
                lease_files = self._get_lease_files()
            else:
                lease_files = [self.lease_file]
            for lease_file in lease_files:
                leases.update(self._get_dnsmasq_leases(lease_file))

            _LOGGER.debug("Found %s leases: %s", len(leases), pf(leases))
        except UbusException as ex:
            _LOGGER.error("Unable to read leases from ubus: %s", ex)

        return leases

    def scan_devices(self) -> List[str]:
        """Scan for new devices and return a list with found device IDs."""
        return list(self._get_connected_devices().keys())

    def get_device_name(self, mac) -> str:
        """Return the name of the given device or None if we don't know."""
        leases = self._get_leases()
        if mac in leases:
            return leases[mac].hostname
