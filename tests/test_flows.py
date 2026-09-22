"""Exercise native HA flows, not hand-called flow methods."""

from copy import deepcopy

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.punifi_macfilter.const import DOMAIN
from custom_components.punifi_macfilter.policy import ProviderError

from .conftest import DATA, MAPPING

PF = {
    k: v
    for k, v in DATA.items()
    if k in ("pfsense_host", "pfsense_port", "pfsense_username", "pfsense_password")
}
UF = {k: v for k, v in DATA.items() if k in ("unifi_host", "unifi_port", "unifi_api_key")}


async def configure(hass, result, data):
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def mapping_screen(hass, context=None):
    result = await hass.config_entries.flow.async_init(DOMAIN, context=context or {"source": "user"})
    assert result["step_id"] == "user"
    result = await configure(hass, result, PF)
    assert result["step_id"] == "unifi"
    result = await configure(hass, result, UF)
    assert result["step_id"] == "site"
    result = await configure(hass, result, {"site": "site-test"})
    assert result["step_id"] == "mappings"
    return result


async def test_complete_setup(hass, clients):
    result = await mapping_screen(hass)
    result = await configure(hass, result, {"next_step_id": "pair"})
    assert result["step_id"] == "pair"
    result = await configure(
        hass, result, {"pfsense_interface_id": "opt1", "unifi_wlan_id": "wlan-test", "sync_enabled": False}
    )
    assert result["step_id"] == "pair_preview"
    result = await configure(hass, result, {"confirm": True})
    result = await configure(hass, result, {"next_step_id": "finish"})
    result = await configure(hass, result, {"sync_enabled": False})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.options["mappings"] == [MAPPING]
    assert entry.data["pfsense_password"] == DATA["pfsense_password"]
    assert not any("SENTINEL" in str(v) for v in entry.options.values())
    assert hass.states.get("sensor.punifi_sync_smart_home").state == "Out of sync"
    clients[1].apply.assert_not_awaited()


@pytest.mark.parametrize(
    "error", ["invalid_auth", "tls_error", "insufficient_permissions", "cannot_connect", "unsupported_schema"]
)
async def test_connection_errors_no_secret_echo(hass, clients, error):
    clients[0].read.side_effect = ProviderError(error, "pfsense")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await configure(hass, result, PF)
    assert result["errors"] == {"base": error}
    assert "SENTINEL" not in str(result)
    schema = result["data_schema"]
    assert all(not callable(k.default) or "SENTINEL" not in str(k.default()) for k in schema.schema)
    clients[1].apply.assert_not_awaited()


async def test_reconfigure_blank_secret_preserves_and_cancellation(hass, entry, clients):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    pf = dict(PF, pfsense_host="new-firewall.example.com", pfsense_password="")
    result = await configure(hass, result, pf)
    assert entry.data["pfsense_host"] == DATA["pfsense_host"]
    result = await configure(hass, result, dict(UF, unifi_api_key=""))
    result = await configure(hass, result, {"site": "site-test"})
    result = await configure(hass, result, {"next_step_id": "finish"})
    result = await configure(hass, result, {"sync_enabled": False})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data["pfsense_host"] == "new-firewall.example.com"
    assert entry.data["pfsense_password"] == DATA["pfsense_password"]
    assert entry.options["mappings"] == [MAPPING]
    clients[1].apply.assert_not_awaited()


async def test_changed_identity_remapping(hass, entry, clients, source):
    source["identity"] = "22222222-2222-4222-8222-222222222222"
    result = await mapping_screen(hass, {"source": "reconfigure", "entry_id": entry.entry_id})
    result = await configure(hass, result, {"next_step_id": "finish"})
    assert result["description_placeholders"]["count"] == "0"
    assert entry.data["pfsense_id"] == DATA["pfsense_id"]
    result = await configure(hass, result, {"sync_enabled": False})
    await hass.async_block_till_done()
    assert entry.options == {"sync_enabled": False, "mappings": []}
    clients[1].apply.assert_not_awaited()


async def test_options_remove_and_pausing(hass, entry, clients):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "mappings"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_pair"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"target": "wlan-test"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "finish"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"sync_enabled": False})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["mappings"] == []
    assert not entry.runtime_data.stopping
    clients[1].apply.assert_not_awaited()


async def test_duplicate_target_and_cancel_preview(hass, clients):
    result = await mapping_screen(hass)
    for confirmed in [False, True]:
        result = await configure(hass, result, {"next_step_id": "pair"})
        result = await configure(
            hass,
            result,
            {"pfsense_interface_id": "opt1", "unifi_wlan_id": "wlan-test", "sync_enabled": False},
        )
        result = await configure(hass, result, {"confirm": confirmed})
    result = await configure(hass, result, {"next_step_id": "pair"})
    result = await configure(
        hass, result, {"pfsense_interface_id": "opt2", "unifi_wlan_id": "wlan-test", "sync_enabled": False}
    )
    assert result["errors"] == {"base": "duplicate_target"}
    clients[1].apply.assert_not_awaited()


async def test_reauth_only_affected_provider(hass, entry, clients):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data.auth_provider = "pfsense"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}, data=dict(entry.data)
    )
    assert result["step_id"] == "reauth_confirm"
    assert set(str(k) for k in result["data_schema"].schema) == {"pfsense_username", "pfsense_password"}
    result = await configure(
        hass,
        result,
        {"pfsense_username": DATA["pfsense_username"], "pfsense_password": "replacement-test-only"},
    )
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["unifi_api_key"] == DATA["unifi_api_key"]
    assert entry.data["pfsense_password"] == "replacement-test-only"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_failed_reconfigure_preserves_entry(hass, entry, clients):
    baseline = deepcopy(dict(entry.data))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    clients[0].read.side_effect = ProviderError("tls_error", "pfsense")
    result = await configure(hass, result, dict(PF, pfsense_password="rejected-secret"))
    assert result["errors"] == {"base": "tls_error"}
    assert "rejected-secret" not in str(result)
    assert dict(entry.data) == baseline
    hass.config_entries.flow.async_abort(result["flow_id"])
    assert dict(entry.data) == baseline
