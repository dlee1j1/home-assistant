"""
Support for OpenWRT (ubus) routers.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/device_tracker.ubus/
"""
import json
import logging
import re
import threading
from datetime import timedelta

import requests
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.device_tracker import (
    DOMAIN, PLATFORM_SCHEMA, DeviceScanner)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.util import Throttle

# Return cached results if last scan was less then this time ago.
MIN_TIME_BETWEEN_SCANS = timedelta(seconds=5)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_USERNAME): cv.string
})


def get_scanner(hass, config):
    """Validate the configuration and return an ubus scanner."""
    scanner = UbusDeviceScanner(config[DOMAIN])

    return scanner if scanner.success_init else None


class UbusDeviceScanner(DeviceScanner):
    """
    This class queries a wireless router running OpenWrt firmware.

    Adapted from Tomato scanner.
    """

    def __init__(self, config):
        """Initialize the scanner."""
        host = config[CONF_HOST]
        self.username = config[CONF_USERNAME]
        self.password = config[CONF_PASSWORD]

        self.parse_api_pattern = re.compile(r"(?P<param>\w*) = (?P<value>.*);")
        self.lock = threading.Lock()
        self.last_results = {}
        self.url = 'http://{}/ubus'.format(host)
<<<<<<< HEAD

        self.session_id = _get_session_id(self.url, username, password)
        self.hostapd = []
        self.leasefile = None
        self.mac2name = None
        self.success_init = self.session_id is not None

    def scan_devices(self):
        """Scan for new devices and return a list with found device IDs."""
        self._update_info()
        return self.last_results

    def get_device_name(self, device):
        """Return the name of the given device or None if we don't know."""
        with self.lock:
            if self.leasefile is None:
                result = _req_json_rpc(
                    self.url, self.session_id, 'call', 'uci', 'get',
                    config="dhcp", type="dnsmasq")
                if result:
                    values = result["values"].values()
                    self.leasefile = next(iter(values))["leasefile"]
                else:
                    return

            if self.mac2name is None:
                result = _req_json_rpc(
                    self.url, self.session_id, 'call', 'file', 'read',
                    path=self.leasefile)
                if result:
                    self.mac2name = dict()
                    for line in result["data"].splitlines():
                        hosts = line.split(" ")
                        self.mac2name[hosts[1].upper()] = hosts[3]
                else:
                    # Error, handled in the _req_json_rpc
                    return

            return self.mac2name.get(device.upper(), None)

    @Throttle(MIN_TIME_BETWEEN_SCANS)
    def _update_info(self):
        """Ensure the information from the Luci router is up to date.

        Returns boolean if scanning successful.
        """
        if not self.success_init:
            return False

        with self.lock:
            _LOGGER.info("Checking ARP")

            if not self.hostapd:
                hostapd = _req_json_rpc(
                    self.url, self.session_id, 'list', 'hostapd.*', '')
                self.hostapd.extend(hostapd.keys())

            self.last_results = []
            results = 0
            for hostapd in self.hostapd:
                result = _req_json_rpc(
                    self.url, self.session_id, 'call', hostapd, 'get_clients')

                if result:
                    results = results + 1
                    self.last_results.extend(result['clients'].keys())

            return bool(results)
=======
        self.session_id = None  # lazy init, will be fetched on first error

    def login(self):
        """Login and fetch the session id."""
        _LOGGER.debug("Fetching the session id..")
        self.session_id = _get_session_id(self.url,
                                          self.username, self.password)
        _LOGGER.debug("Got session: %s", self.session_id)

    def update(self, see):
        """Fetch clients and leases from the router."""
        clients = self._get_devices()
        leases = self._get_leases()
        _LOGGER.debug("Got %s clients, %s leases", len(clients), len(leases))

        # Note, we may have clients who have leases expired..
        for client in clients:
            mac = client["mac"].replace(":", "").lower()
            lease = [lease for lease in leases if lease["mac"] == mac]
            if lease:
                client["ip"] = lease[0]["ip"]
                client["hostname"] = lease[0]["hostname"]
            else:
                _LOGGER.debug("No lease found for %s, using mac as name",
                              client["mac"])
                client["hostname"] = mac
                client["ip"] = "<no lease>"

            extra_attrs = {
                "ip": client["ip"],
                "signal": client["signal"],
                "noise": client["noise"]
            }

            see(mac=client["mac"], host_name=client["hostname"],
                source_type=SOURCE_TYPE_ROUTER,
                attributes=extra_attrs)

        return True

    def _get_devices(self):
        """Request all connected devices."""
        clients = []

        try:
            ifaces = _req_json_rpc(self.url, self.session_id,
                                   "call", "iwinfo", "devices")
        except UbusException as ex:
            _LOGGER.error("Unable to fetch interfaces: %s", ex)
            self.login()  # try to renew the session
            return clients

        _LOGGER.debug("Found %s ifaces: %s", len(ifaces), ifaces)
        for iface in ifaces["devices"]:
            devices = _req_json_rpc(self.url, self.session_id,
                                    "call", "iwinfo", "assoclist",
                                    device=iface)
            if "results" in devices:
                for dev in devices["results"]:
                    # _LOGGER.debug("device: %s", dev)
                    clients.append(dev)

        # example client
        # [{'signal': -47, 'inactive': 310,
        # 'tx': {'mcs': 7, '40mhz': False, 'rate': 65000, 'short_gi': False},
        # 'mac': 'F0:B4:29:XX:XX:XX',
        # 'rx': {'mcs': 7, '40mhz': False, 'rate': 72200, 'short_gi': True},
        # 'noise': -95}]
        _LOGGER.debug("Found %s clients: %s", len(clients),
                      [client["mac"] for client in clients])

        return clients

    def _get_leases(self):
        """Get all DHCP leases to obtain hostnames."""
        leases = []
        for ip_version in ["ipv4leases", "ipv6leases"]:
            try:
                lease_res = _req_json_rpc(self.url, self.session_id,
                                          "call", "dhcp", ip_version)
            except UbusException as ex:
                _LOGGER.error("Unable to fetch leases: %s", ex)
                self.login()  # try to renew the session
                return leases
            for network in lease_res["device"]:
                for lease in lease_res["device"][network]["leases"]:
                    _LOGGER.debug("[%s] client: %s", network, lease)
                    leases.append(lease)

        # example lease
        # {'mac': '286c07xxxxxx', 'valid': -7471,
        # 'hostname': 'XXXXX','ip': '192.168.250.132'}

        return leases
>>>>>>> ubus: do not do i/o on setup_scanner(), try to re-login on expired/failed sessions


def _req_json_rpc(url, session_id, rpcmethod, subsystem, method, **params):
    """Perform one JSON RPC operation."""
    data = json.dumps({"jsonrpc": "2.0",
                       "id": 1,
                       "method": rpcmethod,
                       "params": [session_id,
                                  subsystem,
                                  method,
                                  params]})

    try:
        res = requests.post(url, data=data, timeout=5)

    except requests.exceptions.Timeout:
        return

    if res.status_code == 200:
        response = res.json()

        if rpcmethod == "call":
            return response["result"][1]
        else:
            return response["result"]


def _get_session_id(url, username, password):
    """Get the authentication token for the given host+username+password."""
    res = _req_json_rpc(url, "00000000000000000000000000000000", 'call',
                        'session', 'login', username=username,
                        password=password)
    return res["ubus_rpc_session"]
<<<<<<< HEAD
=======


def setup_scanner(hass, config, see):
    """Setup an endpoint for the ubus logger."""
    try:
        _LOGGER.debug("Trying to start the scanner..")
        scanner = UbusDeviceScanner(config)
        interval = DEFAULT_SCAN_INTERVAL
        _LOGGER.debug("Started ubustracker with interval=%s", interval)

        def update(now):
            """Update all the hosts on every interval time."""
            scanner.update(see)
            track_point_in_utc_time(hass, update, now + interval)
            return True

        return update(util.dt.utcnow())
    except UbusException as ex:
        _LOGGER.error("Got exception: %s", ex)
        return False

    return True
>>>>>>> ubus: do not do i/o on setup_scanner(), try to re-login on expired/failed sessions
