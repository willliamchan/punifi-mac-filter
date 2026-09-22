"""Strict provider models and pure one-way policy calculation."""

import re
from uuid import UUID

from .const import POLICIES


class ProviderError(Exception):
    """Safe error codes only; never attach raw responses or credentials."""

    def __init__(self, code, provider=None):
        super().__init__(code)
        self.code = code
        self.provider = provider


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ProviderError("unsupported_schema")
    return value


def identifier(value):
    value = text(value)
    if value in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise ProviderError("unsupported_schema")
    return value


def vlan(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ProviderError("unsupported_schema")
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if type(value) is not int or not 1 <= value <= 4094:
        raise ProviderError("unsupported_schema")
    return value


def normalize(values):
    if not isinstance(values, list):
        raise ProviderError("unsupported_schema")
    result = set()
    for raw in values:
        if not isinstance(raw, str):
            raise ProviderError("invalid_mac")
        value = raw.strip().lower()
        if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", value):
            raise ProviderError("invalid_mac")
        if value == "00:00:00:00:00:00" or int(value[:2], 16) & 1:
            raise ProviderError("invalid_mac")
        result.add(value)
    return sorted(result)


def parse_source(raw):
    try:
        uid = UUID(raw["identity"])
        if not uid.int:
            raise ValueError
        rows = raw["interfaces"]
        if not isinstance(rows, list):
            raise ValueError
        result = {}
        for row in rows:
            key = identifier(row["id"])
            if key in result or row["policy"] not in POLICIES:
                raise ValueError
            result[key] = {
                "id": key,
                "name": text(row["interface"]),
                "subnet": str(row["ip_address"]) + "/" + str(row["subnet_prefix"]),
                "vlan": vlan(row["vlan_id"]),
                "policy": row["policy"],
                "macs": normalize(row["mac_addresses"]),
            }
        return {"identity": str(uid), "interfaces": result}
    except KeyError, TypeError, ValueError, AttributeError:
        raise ProviderError("unsupported_schema", "pfsense") from None


def parse_wlan(raw, networks):
    try:
        key = identifier(raw["_id"])
        network_id = identifier(raw["networkconf_id"])
        network = networks[network_id]
        enabled = raw["mac_filter_enabled"]
        mode = raw["mac_filter_policy"]
        if type(enabled) is not bool or mode not in ("allow", "deny"):
            raise ValueError
        tag_enabled = network.get("vlan_enabled", False)
        if type(tag_enabled) is not bool:
            raise ValueError
        tag = vlan(network["vlan"]) if tag_enabled else None
        if tag_enabled and tag is None:
            raise ValueError
        macs = normalize(raw["mac_filter_list"])
        return {
            "id": key,
            "name": text(raw["name"]),
            "network_id": network_id,
            "network_name": text(network["name"]),
            "vlan": tag,
            "enabled": enabled,
            "mode": mode,
            "macs": macs,
            "raw_count": len(raw["mac_filter_list"]),
        }
    except KeyError, TypeError, ValueError:
        raise ProviderError("unsupported_schema", "unifi") from None


def desired(source, interface):
    if interface not in source["interfaces"]:
        raise ProviderError("missing_source")
    row = source["interfaces"][interface]
    if row["policy"] == "disabled":
        return {"mac_filter_enabled": False}
    macs = row["macs"]
    if row["policy"] == "enabled":
        macs = sorted({m for r in source["interfaces"].values() for m in r["macs"]})
    if not macs:
        raise ProviderError("empty_allowlist")
    return {"mac_filter_enabled": True, "mac_filter_policy": "allow", "mac_filter_list": list(macs)}


def matches(observed, intent):
    if observed["enabled"] != intent["mac_filter_enabled"]:
        return False
    if not intent["mac_filter_enabled"]:
        return True
    return (
        observed["mode"] == "allow"
        and observed["macs"] == intent["mac_filter_list"]
        and observed["raw_count"] == len(intent["mac_filter_list"])
    )


def mapping_reason(source, target, mapping):
    row = source["interfaces"].get(mapping["pfsense_interface_id"])
    if row is None:
        return "missing_source"
    if target is None:
        return "missing_target"
    if (
        row["vlan"] != mapping["pfsense_vlan_id"]
        or target["network_id"] != mapping["unifi_network_id"]
        or target["vlan"] != mapping["unifi_vlan_id"]
    ):
        return "mapping_changed"
    return None
