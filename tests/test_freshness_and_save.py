"""Source-age and save-time race regressions with real HA entries."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.punifi_macfilter import coordinator
from custom_components.punifi_macfilter.config_flow import MappingEditor
from custom_components.punifi_macfilter.const import DOMAIN
from custom_components.punifi_macfilter.policy import ProviderError

from .conftest import DATA, MAPPING
from .test_runtime import enable, start


@pytest.mark.parametrize("collection_delay,target_delay,writes", [(31, 0, 0), (25, 6, 0), (25, 5, 1)])
async def test_source_budget_includes_all_unifi_reads(
    hass, entry, clients, target, monkeypatch, collection_delay, target_delay, writes
):
    c = await start(hass, entry)
    enable(hass, entry)
    clock = [0.0]
    monkeypatch.setattr(coordinator, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def read(site):
        clock[0] += collection_delay
        return deepcopy(target)

    async def exact(snapshot, key):
        clock[0] += target_delay
        return deepcopy(target["wlans"][key])

    clients[1].read.side_effect = read
    clients[1].target.side_effect = exact
    await c.async_refresh()
    assert clients[1].apply.await_count == writes
    assert c.last_update_success is bool(writes)
    if not writes:
        assert str(c.last_exception) == "stale_source"


async def test_refreshed_source_keeps_original_read_timestamp(hass, entry, clients, target, monkeypatch):
    c = await start(hass, entry)
    enable(hass, entry)
    options = deepcopy(dict(entry.options))
    options["mappings"].insert(0, dict(options["mappings"][0], unifi_wlan_id="paused", sync_enabled=False))
    target["wlans"]["paused"] = dict(target["wlans"]["wlan-test"], id="paused")
    hass.config_entries.async_update_entry(entry, options=options)
    clock = [0.0]
    monkeypatch.setattr(coordinator, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    original_enabled = c.enabled

    def enabled(mapping):
        if mapping["unifi_wlan_id"] == "wlan-test":
            clock[0] = 31.0
        return original_enabled(mapping)

    monkeypatch.setattr(c, "enabled", enabled)
    reads = 0

    async def read(site):
        nonlocal reads
        reads += 1
        if reads == 2:
            clock[0] += 25
        return deepcopy(target)

    async def exact(snapshot, key):
        clock[0] += 6
        return deepcopy(target["wlans"][key])

    clients[1].read.side_effect = read
    clients[1].target.side_effect = exact
    await c.async_refresh()
    assert reads == 2
    clients[1].apply.assert_not_awaited()
    assert not c.last_update_success
    assert str(c.last_exception) == "stale_source"


@pytest.mark.parametrize("change", ["baseline", "ownership", "cancel"])
async def test_save_wait_rechecks_and_preserves_runtime(hass, entry, clients, change):
    c = await start(hass, entry)
    editor = MappingEditor()
    editor.hass = hass
    editor.init_editor(entry.data, entry.options, entry)
    await c.lock.acquire()
    entered = False

    async def save():
        nonlocal entered
        async with editor.save_guard():
            entered = True

    pending = asyncio.create_task(save())
    await asyncio.sleep(0)
    assert not pending.done()
    assert not c.stopping
    if change == "baseline":
        hass.config_entries.async_update_entry(entry, options=dict(entry.options, mappings=[]))
    elif change == "ownership":
        other = MockConfigEntry(
            domain=DOMAIN, data=dict(DATA, pfsense_id="other"), options={"mappings": [deepcopy(MAPPING)]}
        )
        other.add_to_hass(hass)
    else:
        pending.cancel()
    c.lock.release()
    with pytest.raises(asyncio.CancelledError if change == "cancel" else ProviderError):
        await pending
    assert not entered
    assert not c.stopping
    assert not c.lock.locked()


async def test_failed_save_restores_admission(hass, entry, clients):
    c = await start(hass, entry)
    editor = MappingEditor()
    editor.hass = hass
    editor.init_editor(entry.data, entry.options, entry)
    with pytest.raises(ProviderError):
        async with editor.save_guard():
            assert c.stopping
            raise ProviderError("configuration_changed")
    assert not c.stopping
    assert not c.lock.locked()
