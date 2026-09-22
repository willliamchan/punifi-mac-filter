"""Real HA entry/registry/entity and guarded writer tests."""

import asyncio
from copy import deepcopy

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.punifi_macfilter.diagnostics import async_get_config_entry_diagnostics
from custom_components.punifi_macfilter.policy import ProviderError


async def start(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


def enable(hass, entry):
    options = deepcopy(dict(entry.options))
    options["sync_enabled"] = True
    options["mappings"][0]["sync_enabled"] = True
    hass.config_entries.async_update_entry(entry, options=options)


async def test_setup_pause_entities_unload(hass, entry, clients):
    c = await start(hass, entry)
    assert (
        hass.states.get("sensor.punifi_pfsense_dhcp_iot").state
        == "Allow known clients from only this interface"
    )
    assert hass.states.get("sensor.punifi_sync_smart_home").state == "Out of sync"
    assert hass.states.get("sensor.punifi_unifi_macfilter_smart_home").state == "Disabled"
    assert hass.states.get("button.punifi_sync_smart_home").state == "unavailable"
    clients[1].apply.assert_not_awaited()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["mapping_count"] == 1
    assert not any(s in str(diag) for s in ["SENTINEL", "192.0.", "02:00:", "site-test", "controller-test"])
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert c.session.closed and c.stopping
    clients[1].apply.assert_not_awaited()


async def test_manual_and_idempotence(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)
    await c.manual("wlan-test")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.punifi_sync_smart_home").state == "Synced"
    assert clients[1].apply.await_count == 1
    await c.manual("wlan-test")
    assert clients[1].apply.await_count == 1
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.punifi_sync_smart_home"}, blocking=True
    )
    assert clients[1].apply.await_count == 1


async def test_drift_and_no_unrelated_fields(hass, entry, clients, target):
    c = await start(hass, entry)
    enable(hass, entry)
    target["wlans"]["unmanaged"] = dict(target["wlans"]["wlan-test"], id="unmanaged", name="Unmanaged")
    await c.async_refresh()
    args = clients[1].apply.await_args.args
    assert args[1] == "wlan-test"
    assert set(args[2]) == {"mac_filter_enabled", "mac_filter_policy", "mac_filter_list"}
    assert target["wlans"]["unmanaged"]["enabled"] is False


@pytest.mark.parametrize("fault", ["empty", "identity", "vlan", "missing", "bad_source"])
async def test_fail_closed(hass, entry, clients, source, target, fault):
    c = await start(hass, entry)
    enable(hass, entry)
    if fault == "empty":
        source["interfaces"]["opt1"]["macs"] = []
    if fault == "identity":
        source["identity"] = "changed"
    if fault == "vlan":
        target["wlans"]["wlan-test"]["vlan"] = 99
    if fault == "missing":
        del target["wlans"]["wlan-test"]
    if fault == "bad_source":
        clients[0].read.side_effect = ProviderError("unsupported_schema", "pfsense")
    await c.async_refresh()
    clients[1].apply.assert_not_awaited()
    assert hass.states.get("sensor.punifi_sync_smart_home").state == "unavailable"


async def test_changed_source_during_apply(hass, entry, clients, source):
    c = await start(hass, entry)
    enable(hass, entry)
    apply = clients[1].apply.side_effect

    async def edit(snapshot, key, intent):
        await apply(snapshot, key, intent)
        source["interfaces"]["opt1"]["macs"] = ["02:00:00:00:00:99"]

    clients[1].apply.side_effect = edit
    await c.async_refresh()
    assert c.data["sync"]["wlan-test"]["state"] == "Out of sync"
    assert clients[1].apply.await_count == 1


async def test_single_writer_pause_drain(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)
    began, finish = asyncio.Event(), asyncio.Event()
    apply = clients[1].apply.side_effect

    async def slow(snapshot, key, intent):
        began.set()
        await finish.wait()
        await apply(snapshot, key, intent)

    clients[1].apply.side_effect = slow
    task = asyncio.create_task(c.manual("wlan-test"))
    await began.wait()
    assert c.data["sync"]["wlan-test"]["state"] == "Processing"
    await c.manual("wlan-test")
    stop = asyncio.create_task(c.drain())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await task
    await stop
    await c.manual("wlan-test")
    assert clients[1].apply.await_count == 1


async def test_permission_stops_retries(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)
    clients[1].apply.side_effect = ProviderError("insufficient_permissions", "unifi")
    await c.async_refresh()
    await c.async_refresh()
    await c.manual("wlan-test")
    assert clients[1].apply.await_count == 1
    assert c.data["sync"]["wlan-test"]["paused_reason"] == "insufficient_permissions"


async def test_ambiguous_timeout_observes_before_retry(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)
    apply = clients[1].apply.side_effect

    async def timeout(snapshot, key, intent):
        await apply(snapshot, key, intent)
        raise ProviderError("cannot_connect", "unifi")

    clients[1].apply.side_effect = timeout
    await c.async_refresh()
    assert c.data["sync"]["wlan-test"]["state"] is None
    await c.async_refresh()
    assert c.data["sync"]["wlan-test"]["state"] == "Synced"
    assert clients[1].apply.await_count == 1


async def test_registry_mapping_remove_and_rename(hass, entry, clients, source, target):
    await start(hass, entry)
    registry = er.async_get(hass)
    original = registry.async_get("sensor.punifi_pfsense_dhcp_iot").unique_id
    source["interfaces"]["opt1"]["name"] = "Renamed"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get("sensor.punifi_pfsense_dhcp_iot").unique_id == original
    options = dict(entry.options, mappings=[])
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get("sensor.punifi_pfsense_dhcp_iot") is None
    assert registry.async_get("sensor.punifi_sync_smart_home") is None
    assert registry.async_get("button.punifi_sync_smart_home") is None
    assert registry.async_get("sensor.punifi_unifi_macfilter_smart_home") is not None


async def test_auth_failure_reauth(hass, entry, clients):
    c = await start(hass, entry)
    clients[0].read.side_effect = ProviderError("invalid_auth", "pfsense")
    await c.async_refresh()
    await hass.async_block_till_done()
    assert c.auth_provider == "pfsense"
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
