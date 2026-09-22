"""HA lifecycle: one owned session/coordinator; no provider changes on unload."""

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import PLATFORMS
from .coordinator import Coordinator
from .pfsense import PfSense
from .unifi import UniFi


async def async_setup_entry(hass, entry):
    session = async_create_clientsession(hass, auto_cleanup=False)
    try:
        coordinator = Coordinator(
            hass, entry, PfSense(session, entry.data), UniFi(session, entry.data), session
        )
    except BaseException:
        session.detach()
        raise
    entry.runtime_data = coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
        # Retire mapping entities and source sensors no longer used by a pair.
        sources = {m["pfsense_interface_id"] for m in entry.options.get("mappings", [])}
        targets = {m["unifi_wlan_id"] for m in entry.options.get("mappings", [])}
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            source_prefix = f"{entry.entry_id}:pf:"
            if entity.unique_id.startswith(source_prefix):
                expected = {f"{source_prefix}{entry.data['pfsense_id']}:{key}" for key in sources}
                if entity.unique_id not in expected:
                    registry.async_remove(entity.entity_id)
                continue
            for role in ("sync", "button"):
                prefix = f"{entry.entry_id}:{role}:"
                if entity.unique_id.startswith(prefix) and entity.unique_id[len(prefix) :] not in targets:
                    registry.async_remove(entity.entity_id)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.close()
        raise
    return True


async def async_unload_entry(hass, entry):
    coordinator = entry.runtime_data
    await coordinator.drain()
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await coordinator.close()
        return True
    coordinator.stopping = False
    return False
