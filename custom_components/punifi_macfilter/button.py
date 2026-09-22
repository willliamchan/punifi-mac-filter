"""Per-mapping manual synchronization via native button.press."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(SyncButton(entry.runtime_data, entry, m) for m in entry.options.get("mappings", []))


class SyncButton(CoordinatorEntity, ButtonEntity):
    _attr_icon = "mdi:sync"

    def __init__(self, coordinator, entry, mapping):
        super().__init__(coordinator)
        self.mapping = mapping
        self.target = mapping["unifi_wlan_id"]
        label = coordinator.data["target"]["wlans"].get(self.target, {}).get("name", "Missing target")
        self._attr_unique_id = f"{entry.entry_id}:button:{self.target}"
        self._attr_name = f"pUniFi Sync now {label}"
        self.entity_id = f"button.punifi_sync_{slugify(label)}"

    @property
    def available(self):
        # Permit a fresh recovery read when previous observations failed, but
        # never use old data for mutation. Pause always disables the action.
        return bool(self.coordinator.enabled(self.mapping))

    async def async_press(self):
        await self.coordinator.manual(self.target)
