"""Const for TP-Link."""
import datetime

DOMAIN = "tplink"

MIN_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=5)
STARTUP_COOLDOWN_TIME = datetime.timedelta(seconds=15)
MIN_TIME_BETWEEN_DISCOVERS = datetime.timedelta(seconds=1)
MIN_TIME_BETWEEN_STATIC_PROBES = datetime.timedelta(seconds=60)
