"""Source, observed-filter and reconciliation sensors."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import POLICIES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def add_new():
        if not coordinator.data or not coordinator.data.get("source"):
            return
        keys = [("source", k) for k in coordinator.data["source"]["interfaces"]]
        keys += [("observed", k) for k in coordinator.data["target"]["wlans"]]
        keys += [("sync", m["unifi_wlan_id"]) for m in entry.options.get("mappings", [])]
        new = [key for key in keys if key not in seen]
        async_add_entities(PUniFiSensor(coordinator, entry, *key) for key in new)
        seen.update(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PUniFiSensor(CoordinatorEntity, SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator, entry, role, key):
        super().__init__(coordinator)
        self.role, self.key = role, key
        source = coordinator.data["source"]["interfaces"]
        target = coordinator.data["target"]["wlans"]
        if role == "source":
            label = source[key]["name"]
            self._attr_unique_id = f"{entry.entry_id}:pf:{entry.data['pfsense_id']}:{key}"
            name, prefix = "pUniFi pfSense DHCP", "punifi_pfsense_dhcp"
            self._attr_icon = "mdi:router-network"
        else:
            label = target.get(key, {}).get("name", "Missing target")
            if role == "observed":
                self._attr_unique_id = (
                    f"{entry.entry_id}:uf:{entry.data['unifi_id']}:{entry.data['unifi_site_id']}:{key}"
                )
                name, prefix = "pUniFi UniFi MAC Filter", "punifi_unifi_macfilter"
                self._attr_icon = "mdi:wifi-lock"
            else:
                self._attr_unique_id = f"{entry.entry_id}:sync:{key}"
                name, prefix = "pUniFi Sync", "punifi_sync"
                self._attr_icon = "mdi:sync"
        self._attr_name = f"{name} {label}"
        self.entity_id = f"sensor.{prefix}_{slugify(label)}"

    @property
    def row(self):
        data = self.coordinator.data or {}
        if self.role == "source":
            return (data.get("source") or {}).get("interfaces", {}).get(self.key)
        if self.role == "observed":
            return (data.get("target") or {}).get("wlans", {}).get(self.key)
        return data.get("sync", {}).get(self.key)

    @property
    def available(self):
        return (
            super().available
            and self.row is not None
            and (self.role != "sync" or self.row["state"] is not None)
        )

    @property
    def native_value(self):
        row = self.row
        if row is None:
            return None
        if self.role == "source":
            return POLICIES[row["policy"]]
        if self.role == "observed":
            return "Disabled" if not row["enabled"] else ("Allow" if row["mode"] == "allow" else "Deny")
        return row["state"]

    @property
    def extra_state_attributes(self):
        row = self.row
        if row is None:
            return {}
        if self.role == "source":
            return {"interface": row["name"], "mac_addresses": row["macs"]}
        if self.role == "observed":
            return {
                "mac_filter_enabled": row["enabled"],
                "mac_filter_policy": row["mode"],
                "mac_filter_list": row["macs"],
            }
        return {k: v for k, v in row.items() if k != "state"}
