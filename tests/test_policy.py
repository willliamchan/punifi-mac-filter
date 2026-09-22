"""Policy boundaries and full strict source validation."""

from copy import deepcopy

import pytest

from custom_components.punifi_macfilter.policy import (
    ProviderError,
    desired,
    matches,
    normalize,
    parse_source,
    parse_wlan,
)
from custom_components.punifi_macfilter.transport import endpoint


def test_policies(source, target):
    assert desired(source, "opt2") == {"mac_filter_enabled": False}
    assert desired(source, "opt1")["mac_filter_list"] == ["02:00:00:00:00:01"]
    source["interfaces"]["opt1"]["policy"] = "enabled"
    assert desired(source, "opt1")["mac_filter_list"] == ["02:00:00:00:00:01", "02:00:00:00:00:02"]
    assert source["interfaces"]["opt1"]["macs"] == ["02:00:00:00:00:01"]
    row = target["wlans"]["wlan-test"]
    row.update(mode="deny", macs=["02:00:00:00:00:aa"], raw_count=1)
    assert matches(row, {"mac_filter_enabled": False})


def test_normalization():
    assert normalize(["02:AA:BB:CC:DD:EE", "02:aa:bb:cc:dd:ee"]) == ["02:aa:bb:cc:dd:ee"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        "02:00:00:00:00:01",
        [None],
        [""],
        ["invalid"],
        ["00:00:00:00:00:00"],
        ["ff:ff:ff:ff:ff:ff"],
        ["01:00:00:00:00:00"],
    ],
)
def test_invalid_macs(value):
    with pytest.raises(ProviderError):
        normalize(value)


def test_empty_restricted(source):
    source["interfaces"]["opt1"]["macs"] = []
    with pytest.raises(ProviderError, match="empty_allowlist"):
        desired(source, "opt1")


def test_duplicate_observed_not_equal(source, target):
    row = target["wlans"]["wlan-test"]
    row.update(enabled=True, macs=["02:00:00:00:00:01"], raw_count=2)
    assert not matches(row, desired(source, "opt1"))


@pytest.mark.parametrize(
    "host,port",
    [
        ("https://x", 443),
        ("user@x", 443),
        ("x/path", 443),
        ("x?q=1", 443),
        ("x#y", 443),
        ("x:443", 443),
        (" x", 443),
        ("[::1]", 443),
        ("x", 0),
        ("x", 65536),
        ("x", True),
    ],
)
def test_invalid_endpoints(host, port):
    with pytest.raises(ProviderError, match="invalid_endpoint"):
        endpoint(host, port)


@pytest.mark.parametrize("host", ["firewall.example.com", "192.0.2.1", "2001:db8::1"])
def test_endpoints(host):
    assert endpoint(host, 10443).scheme == "https"
    assert endpoint(host, 10443).host == host


def test_source_validation(source):
    row = {
        "id": "opt1",
        "interface": "IoT",
        "ip_address": "192.0.2.1",
        "subnet_prefix": "24",
        "vlan_id": "10",
        "policy": "class",
        "mac_addresses": ["02:00:00:00:00:01"],
    }
    raw = {"identity": source["identity"], "interfaces": [row]}
    assert parse_source(raw)["interfaces"]["opt1"]["vlan"] == 10
    for change in [{"policy": "unknown"}, {"vlan_id": True}, {"mac_addresses": ["bad"]}]:
        broken = deepcopy(raw)
        broken["interfaces"][0].update(change)
        with pytest.raises(ProviderError):
            parse_source(broken)
    raw["interfaces"].append(row)
    with pytest.raises(ProviderError):
        parse_source(raw)


def test_no_network_guessing():
    raw = {
        "_id": "w1",
        "name": "WiFi",
        "networkconf_id": "n1",
        "mac_filter_enabled": False,
        "mac_filter_policy": "allow",
        "mac_filter_list": [],
    }
    networks = {"n1": {"name": "No tag"}}
    assert parse_wlan(raw, networks)["vlan"] is None
    with pytest.raises(ProviderError):
        parse_wlan(raw, {})
