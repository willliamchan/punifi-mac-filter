"""UniFi OS Network API-key client; explicit WLAN targets only."""

import json

from .const import FILTER_FIELDS
from .policy import ProviderError, identifier, normalize, parse_wlan, text
from .transport import Transport


class UniFi:
    def __init__(self, session, data):
        self.transport = Transport(
            session,
            data["unifi_host"],
            data["unifi_port"],
            "unifi",
            {"X-API-Key": data["unifi_api_key"], "Accept": "application/json"},
        )

    async def _get(self, path):
        raw = await self.transport.request("GET", path)
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except ValueError, TypeError:
            raise ProviderError("unsupported_schema", "unifi") from None

    async def sites(self):
        rows, offset, total = [], 0, None
        for _ in range(100):
            data = await self._get(f"/proxy/network/integration/v1/sites?offset={offset}&limit=100")
            batch, count = data.get("data"), data.get("totalCount")
            if (
                not isinstance(batch, list)
                or type(count) is not int
                or count < 0
                or (total is not None and total != count)
            ):
                raise ProviderError("unsupported_schema", "unifi")
            total = count
            try:
                rows.extend(
                    {
                        "id": identifier(s["id"]),
                        "reference": identifier(s["internalReference"]),
                        "name": text(s["name"]),
                    }
                    for s in batch
                )
            except KeyError, TypeError:
                raise ProviderError("unsupported_schema", "unifi") from None
            if len(rows) == total:
                if len({s["id"] for s in rows}) != total or len({s["reference"] for s in rows}) != total:
                    raise ProviderError("unsupported_schema", "unifi")
                return rows
            if not batch or len(rows) > total:
                break
            offset += len(batch)
        raise ProviderError("unsupported_schema", "unifi")

    async def _legacy(self, site, suffix):
        reference = identifier(site)
        value = await self._get(f"/proxy/network/api/s/{reference}/{suffix}")
        if value.get("meta", {}).get("rc") != "ok" or not isinstance(value.get("data"), list):
            raise ProviderError("unsupported_schema", "unifi")
        # Legacy collection routes are unpaginated. Do not accept advertised truncation.
        rows = value["data"]
        for key in ("count", "totalCount"):
            if key in value.get("meta", {}) and value["meta"][key] != len(rows):
                raise ProviderError("unsupported_schema", "unifi")
        return rows

    async def read(self, site_id):
        sites = await self.sites()
        site = next((s for s in sites if s["id"] == site_id), None)
        if site is None:
            raise ProviderError("identity_changed", "unifi")
        info = await self._legacy(site["reference"], "stat/sysinfo")
        try:
            if len(info) != 1:
                raise ValueError
            identity = identifier(info[0]["anonymous_controller_id"])
            networks = {}
            for raw in await self._legacy(site["reference"], "rest/networkconf"):
                key = identifier(raw["_id"])
                if key in networks:
                    raise ValueError
                # Retain only mapping-relevant fields, never provider objects.
                networks[key] = {k: raw[k] for k in ("name", "vlan_enabled", "vlan") if k in raw}
            wlans = {}
            for raw in await self._legacy(site["reference"], "rest/wlanconf"):
                row = parse_wlan(raw, networks)
                if row["id"] in wlans:
                    raise ValueError
                wlans[row["id"]] = row
            return {"identity": identity, "site": site, "networks": networks, "wlans": wlans}
        except KeyError, TypeError, ValueError:
            raise ProviderError("unsupported_schema", "unifi") from None

    async def target(self, snapshot, target):
        rows = await self._legacy(snapshot["site"]["reference"], f"rest/wlanconf/{identifier(target)}")
        if len(rows) != 1:
            raise ProviderError("missing_target", "unifi")
        row = parse_wlan(rows[0], snapshot["networks"])
        if row["id"] != target:
            raise ProviderError("identity_changed", "unifi")
        return row

    async def apply(self, snapshot, target, intent):
        # Defense in depth: no generic controller writer exposed.
        if not set(intent) <= FILTER_FIELDS or type(intent.get("mac_filter_enabled")) is not bool:
            raise ProviderError("unsupported_schema", "unifi")
        if intent["mac_filter_enabled"]:
            if (
                set(intent) != FILTER_FIELDS
                or intent["mac_filter_policy"] != "allow"
                or not intent["mac_filter_list"]
                or normalize(intent["mac_filter_list"]) != intent["mac_filter_list"]
            ):
                raise ProviderError("unsupported_schema", "unifi")
        elif intent != {"mac_filter_enabled": False}:
            raise ProviderError("unsupported_schema", "unifi")
        if target not in snapshot["wlans"]:
            raise ProviderError("missing_target", "unifi")
        site = identifier(snapshot["site"]["reference"])
        await self.transport.request(
            "PUT", f"/proxy/network/api/s/{site}/rest/wlanconf/{identifier(target)}", json=intent
        )
