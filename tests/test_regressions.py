"""Regression tests for stale state, ownership and offline safety controls."""

import asyncio
from copy import deepcopy

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.punifi_macfilter.const import DOMAIN
from custom_components.punifi_macfilter.policy import ProviderError, identifier
from custom_components.punifi_macfilter.transport import endpoint

from .conftest import DATA, MAPPING
from .test_flows import configure, mapping_screen
from .test_runtime import enable, start


async def test_pause_available_when_provider_offline(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)
    clients[0].read.side_effect = ProviderError("cannot_connect", "pfsense")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["finish"]
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "finish"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"sync_enabled": False})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["sync_enabled"] is False
    assert c.stopping
    clients[1].apply.assert_not_awaited()


async def test_invalid_source_during_write_stops_remaining_targets(hass, entry, clients, source, target):
    c = await start(hass, entry)
    options = deepcopy(dict(entry.options))
    options["sync_enabled"] = True
    options["mappings"][0]["sync_enabled"] = True
    options["mappings"].append(dict(options["mappings"][0], unifi_wlan_id="second"))
    target["wlans"]["second"] = dict(target["wlans"]["wlan-test"], id="second", name="Second")
    hass.config_entries.async_update_entry(entry, options=options)
    apply = clients[1].apply.side_effect

    async def poison(snapshot, key, intent):
        await apply(snapshot, key, intent)
        clients[0].read.side_effect = ProviderError("invalid_mac", "pfsense")

    clients[1].apply.side_effect = poison
    await c.async_refresh()
    assert clients[1].apply.await_count == 1
    assert clients[1].apply.await_args.args[1] == "wlan-test"
    assert not c.last_update_success


async def test_wrong_readback_not_synced(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)

    async def no_effect(*args):
        pass

    clients[1].apply.side_effect = no_effect
    await c.async_refresh()
    assert c.data["sync"]["wlan-test"]["state"] == "Out of sync"
    await c.manual("wlan-test")
    assert clients[1].apply.await_count == 1
    assert c.data["sync"]["wlan-test"]["paused_reason"] == "retry_backoff"


async def test_cross_entry_conflict(hass, clients):
    other_data = dict(DATA, pfsense_id="other-firewall")
    other = MockConfigEntry(
        domain=DOMAIN,
        data=other_data,
        unique_id="other",
        options={"mappings": [deepcopy(MAPPING)], "sync_enabled": False},
    )
    other.add_to_hass(hass)
    result = await mapping_screen(hass)
    result = await configure(hass, result, {"next_step_id": "pair"})
    result = await configure(
        hass, result, {"pfsense_interface_id": "opt1", "unifi_wlan_id": "wlan-test", "sync_enabled": False}
    )
    result = await configure(hass, result, {"confirm": True})
    result = await configure(hass, result, {"next_step_id": "finish"})
    result = await configure(hass, result, {"sync_enabled": False})
    assert result["errors"] == {"base": "duplicate_target"}
    clients[1].apply.assert_not_awaited()


async def test_options_stale_editor_refused(hass, entry, clients):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "finish"})
    changed = dict(entry.options, mappings=[])
    hass.config_entries.async_update_entry(entry, options=changed)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"sync_enabled": False})
    assert result["errors"] == {"base": "configuration_changed"}
    assert entry.options["mappings"] == []


async def test_large_allowlist(hass, entry, clients, source):
    source["interfaces"]["opt1"]["macs"] = [f"02:00:00:00:00:{i:02x}" for i in range(1, 142)]
    c = await start(hass, entry)
    enable(hass, entry)
    await c.manual("wlan-test")
    assert len(clients[1].apply.await_args.args[2]["mac_filter_list"]) == 141
    assert c.data["sync"]["wlan-test"]["state"] == "Synced"


async def test_unload_during_write(hass, entry, clients):
    c = await start(hass, entry)
    enable(hass, entry)
    began, finish = asyncio.Event(), asyncio.Event()
    apply = clients[1].apply.side_effect

    async def slow(snapshot, key, intent):
        began.set()
        await finish.wait()
        await apply(snapshot, key, intent)

    clients[1].apply.side_effect = slow
    running = asyncio.create_task(c.manual("wlan-test"))
    await began.wait()
    unload = asyncio.create_task(hass.config_entries.async_unload(entry.entry_id))
    await asyncio.sleep(0)
    assert not unload.done()
    finish.set()
    await running
    assert await unload
    assert c.session.closed
    assert clients[1].apply.await_count == 1


@pytest.mark.parametrize("bad", [".", "..", "../x", "x/y", "x?y", "%2f"])
def test_path_injection(bad):
    with pytest.raises(ProviderError):
        identifier(bad)


def test_ipv6_zone_rejected():
    with pytest.raises(ProviderError):
        endpoint("fe80::1%eth0", 443)


async def test_credential_sentinels_absent_from_runtime_outputs(hass, entry, clients, caplog):
    c = await start(hass, entry)
    enable(hass, entry)
    await c.manual("wlan-test")
    for state in hass.states.async_all():
        assert "SENTINEL" not in str(state.as_dict())
    assert "SENTINEL" not in caplog.text
