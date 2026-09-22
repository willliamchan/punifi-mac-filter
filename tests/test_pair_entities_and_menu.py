"""Pair-only sources and native menu captions, including upgrade cleanup."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.punifi_macfilter.const import DOMAIN

from .test_flows import mapping_screen
from .test_runtime import enable, start

CAPTIONS = {
    "pair": "Add pair",
    "edit_pair": "Edit pair",
    "remove_pair": "Remove pair",
    "finish": "Review sync enablement and save",
}


@pytest.mark.parametrize("options", [False, True])
@pytest.mark.parametrize("empty_translations", [False, True])
async def test_menu_supplies_captions(hass, entry, clients, options, empty_translations):
    async def open_menu():
        if options:
            return await hass.config_entries.options.async_init(entry.entry_id)
        clients[0].read.side_effect = None
        from .conftest import SOURCE

        source = deepcopy(SOURCE)
        source["identity"] = "22222222-2222-4222-8222-222222222222"
        clients[0].read.return_value = source
        return await mapping_screen(hass)

    if empty_translations:
        with patch(
            "custom_components.punifi_macfilter.config_flow.async_get_translations",
            AsyncMock(return_value={}),
        ):
            result = await open_menu()
    else:
        result = await open_menu()
    assert result["menu_options"] == CAPTIONS
    clients[1].apply.assert_not_awaited()


async def test_only_selected_sources_but_complete_union(hass, entry, clients, source):
    source["interfaces"]["opt1"]["policy"] = "enabled"
    c = await start(hass, entry)
    assert hass.states.get("sensor.punifi_pfsense_dhcp_iot") is not None
    assert hass.states.get("sensor.punifi_pfsense_dhcp_guest") is None
    assert set(c.data["source"]["interfaces"]) == {"opt1", "opt2"}
    enable(hass, entry)
    await c.manual("wlan-test")
    assert clients[1].apply.await_args.args[2]["mac_filter_list"] == [
        "02:00:00:00:00:01",
        "02:00:00:00:00:02",
    ]
    assert hass.states.get("sensor.punifi_pfsense_dhcp_iot").attributes["mac_addresses"] == [
        "02:00:00:00:00:01"
    ]


async def test_upgrade_removes_unpaired_registry_entry(hass, entry, clients):
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}:pf:{entry.data['pfsense_id']}:opt2",
        suggested_object_id="punifi_pfsense_dhcp_guest",
        config_entry=entry,
    )
    await start(hass, entry)
    assert registry.async_get(old.entity_id) is None
    assert registry.async_get("sensor.punifi_pfsense_dhcp_iot") is not None
    clients[1].apply.assert_not_awaited()


async def test_shared_source_retained_until_last_pair_removed(hass, entry, clients, target):
    options = deepcopy(dict(entry.options))
    options["mappings"].append(dict(options["mappings"][0], unifi_wlan_id="second"))
    target["wlans"]["second"] = dict(target["wlans"]["wlan-test"], id="second", name="Second")
    hass.config_entries.async_update_entry(entry, options=options)
    await start(hass, entry)
    registry = er.async_get(hass)
    uid = registry.async_get("sensor.punifi_pfsense_dhcp_iot").unique_id
    options["mappings"] = options["mappings"][1:]
    hass.config_entries.async_update_entry(entry, options=deepcopy(options))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get("sensor.punifi_pfsense_dhcp_iot").unique_id == uid
    options["mappings"] = []
    hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get("sensor.punifi_pfsense_dhcp_iot") is None
    assert hass.states.get("sensor.punifi_pfsense_dhcp_iot") is None
    assert hass.states.get("sensor.punifi_unifi_macfilter_smart_home") is not None
    clients[1].apply.assert_not_awaited()
