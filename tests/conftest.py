"""Synthetic provider fixtures only; no live configuration or credentials."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.punifi_macfilter.const import DOMAIN

SOURCE = {
    "identity": "11111111-1111-4111-8111-111111111111",
    "interfaces": {
        "opt1": {
            "id": "opt1",
            "name": "IoT",
            "subnet": "192.0.2.1/24",
            "vlan": 10,
            "policy": "class",
            "macs": ["02:00:00:00:00:01"],
        },
        "opt2": {
            "id": "opt2",
            "name": "Guest",
            "subnet": "198.51.100.1/24",
            "vlan": 20,
            "policy": "disabled",
            "macs": ["02:00:00:00:00:02"],
        },
    },
}
TARGET = {
    "identity": "controller-test",
    "site": {"id": "site-test", "reference": "default", "name": "Test Site"},
    "networks": {"network-test": {"name": "IoT network", "vlan_enabled": True, "vlan": 10}},
    "wlans": {
        "wlan-test": {
            "id": "wlan-test",
            "name": "Smart Home",
            "network_id": "network-test",
            "network_name": "IoT network",
            "vlan": 10,
            "enabled": False,
            "mode": "allow",
            "macs": [],
            "raw_count": 0,
        }
    },
}
DATA = {
    "pfsense_host": "firewall.example.com",
    "pfsense_port": 443,
    "pfsense_username": "synthetic-user",
    "pfsense_password": "PASSWORD_SENTINEL_not_real",
    "pfsense_id": SOURCE["identity"],
    "unifi_host": "controller.example.com",
    "unifi_port": 443,
    "unifi_api_key": "KEY_SENTINEL_not_real",
    "unifi_id": TARGET["identity"],
    "unifi_site_id": "site-test",
    "unifi_site_reference": "default",
}
MAPPING = {
    "pfsense_interface_id": "opt1",
    "unifi_wlan_id": "wlan-test",
    "unifi_network_id": "network-test",
    "pfsense_vlan_id": 10,
    "unifi_vlan_id": 10,
    "sync_enabled": False,
}


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def source():
    return deepcopy(SOURCE)


@pytest.fixture
def target():
    return deepcopy(TARGET)


@pytest.fixture
def entry(hass):
    item = MockConfigEntry(
        domain=DOMAIN,
        title="pUniFi MAC Filter",
        data=deepcopy(DATA),
        unique_id=f"{SOURCE['identity']}:controller-test:site-test",
        options={"sync_enabled": False, "mappings": [deepcopy(MAPPING)]},
    )
    item.add_to_hass(hass)
    return item


@pytest.fixture
def clients(source, target):
    pf, uf = AsyncMock(), AsyncMock()
    pf.read.side_effect = lambda: deepcopy(source)
    uf.read.side_effect = lambda site: deepcopy(target)
    uf.sites.side_effect = lambda: [deepcopy(target["site"])]
    uf.target.side_effect = lambda snapshot, key: deepcopy(target["wlans"][key])

    async def apply(snapshot, key, intent):
        row = target["wlans"][key]
        row["enabled"] = intent["mac_filter_enabled"]
        if row["enabled"]:
            row.update(
                mode="allow", macs=list(intent["mac_filter_list"]), raw_count=len(intent["mac_filter_list"])
            )

    uf.apply.side_effect = apply
    with (
        patch("custom_components.punifi_macfilter.PfSense", return_value=pf),
        patch("custom_components.punifi_macfilter.UniFi", return_value=uf),
        patch("custom_components.punifi_macfilter.config_flow.PfSense", return_value=pf),
        patch("custom_components.punifi_macfilter.config_flow.UniFi", return_value=uf),
    ):
        yield pf, uf
