"""Shared integration contract."""

from datetime import timedelta

DOMAIN = "punifi_macfilter"
NAME = "pUniFi MAC Filter"
PLATFORMS = ["sensor", "button"]
POLL_INTERVAL = timedelta(seconds=10)
TIMEOUT = 8
MAX_RESPONSE = 2_000_000
POLICIES = {
    "disabled": "Allow all clients",
    "class": "Allow known clients from only this interface",
    "enabled": "Allow known clients from any interface",
}
FILTER_FIELDS = {"mac_filter_enabled", "mac_filter_policy", "mac_filter_list"}
