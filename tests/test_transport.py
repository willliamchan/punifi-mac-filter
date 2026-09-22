"""Transport-level assertions on real clients with synthetic wire responses."""

import json
import ssl
import xmlrpc.client
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.punifi_macfilter.pfsense import COLLECTOR, PAYLOAD, PfSense
from custom_components.punifi_macfilter.policy import ProviderError
from custom_components.punifi_macfilter.transport import Transport
from custom_components.punifi_macfilter.unifi import UniFi

from .conftest import DATA


class Response:
    def __init__(self, body=b"{}", status=200):
        self.status = status
        self.body = body
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def iter_chunked(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i : i + size]


def session_for(*responses):
    session = MagicMock()
    session.request.side_effect = responses
    return session


@pytest.mark.parametrize(
    "status,code",
    [
        (301, "redirect_blocked"),
        (302, "redirect_blocked"),
        (303, "redirect_blocked"),
        (307, "redirect_blocked"),
        (308, "redirect_blocked"),
        (401, "invalid_auth"),
        (403, "insufficient_permissions"),
        (404, "unsupported_api"),
        (500, "cannot_connect"),
    ],
)
async def test_status_no_redirect_or_body_leak(status, code, caplog):
    session = session_for(Response(b"RAW_PRIVATE_SENTINEL", status))
    t = Transport(session, "controller.example.com", 443, "unifi", {"X-API-Key": "SECRET_SENTINEL"})
    with pytest.raises(ProviderError) as caught:
        await t.request("GET", "/fixed/path")
    assert str(caught.value) == code
    assert "SENTINEL" not in caplog.text
    assert session.request.call_count == 1
    kwargs = session.request.call_args.kwargs
    assert kwargs["allow_redirects"] is False and kwargs["ssl"] is True


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("RAW_PRIVATE_SENTINEL"), "cannot_connect"),
        (aiohttp.ClientConnectionError("RAW_PRIVATE_SENTINEL"), "cannot_connect"),
        (ssl.SSLError("RAW_PRIVATE_SENTINEL"), "tls_error"),
    ],
)
async def test_network_exceptions_safe(failure, code):
    t = Transport(session_for(failure), "x.example.com", 443, "pfsense")
    with pytest.raises(ProviderError) as caught:
        await t.request("POST", "/xmlrpc.php")
    assert str(caught.value) == code
    assert caught.value.__suppress_context__


async def test_bounded_response():
    t = Transport(session_for(Response(b"x" * 2_000_001)), "x.example.com", 443, "pfsense")
    with pytest.raises(ProviderError, match="unsupported_schema"):
        await t.request("GET", "/fixed")


async def test_fixed_xmlrpc_wire_contract(source):
    raw = {
        "identity": source["identity"],
        "interfaces": [
            {
                "id": "opt1",
                "interface": "IoT",
                "ip_address": "192.0.2.1",
                "subnet_prefix": "24",
                "vlan_id": "10",
                "policy": "class",
                "mac_addresses": ["02:00:00:00:00:01"],
            }
        ],
    }
    session = session_for(Response(xmlrpc.client.dumps((raw,), methodresponse=True).encode()))
    result = await PfSense(session, DATA).read()
    assert result["interfaces"]["opt1"]["policy"] == "class"
    method, url = session.request.call_args.args
    assert method == "POST" and url.path == "/xmlrpc.php"
    params, method_name = xmlrpc.client.loads(session.request.call_args.kwargs["data"])
    assert method_name == "pfsense.exec_php" and params == (COLLECTOR,)
    assert session.request.call_args.kwargs["data"] == PAYLOAD
    for forbidden in [
        "write_config",
        "config_set_path",
        "config_del_path",
        "file_put_contents",
        "exec_service",
    ]:
        assert forbidden not in COLLECTOR
    assert "def apply" not in __import__("inspect").getsource(PfSense)


@pytest.mark.parametrize(
    "body",
    [
        b"not xml",
        b"<!DOCTYPE x><x/>",
        xmlrpc.client.dumps(xmlrpc.client.Fault(1, "RAW_PRIVATE_SENTINEL")).encode(),
    ],
)
async def test_xmlrpc_malformed_no_leak(body):
    with pytest.raises(ProviderError) as caught:
        await PfSense(session_for(Response(body)), DATA).read()
    assert "SENTINEL" not in str(caught.value)


async def test_sites_pagination():
    def page(rows, total):
        return Response(json.dumps({"data": rows, "totalCount": total}).encode())

    s1 = {"id": "s1", "internalReference": "default", "name": "Site 1"}
    s2 = {"id": "s2", "internalReference": "next", "name": "Site 2"}
    session = session_for(page([s1], 2), page([s2], 2))
    result = await UniFi(session, DATA).sites()
    assert len(result) == 2
    assert session.request.call_args_list[1].args[1].query["offset"] == "1"
    session = session_for(page([s1], 2), page([], 2))
    with pytest.raises(ProviderError):
        await UniFi(session, DATA).sites()
    session = session_for(page([s1], 2), page([s1], 2))
    with pytest.raises(ProviderError):
        await UniFi(session, DATA).sites()


async def test_exact_narrow_unifi_write(target):
    session = session_for(Response())
    client = UniFi(session, DATA)
    intent = {
        "mac_filter_enabled": True,
        "mac_filter_policy": "allow",
        "mac_filter_list": ["02:00:00:00:00:01"],
    }
    await client.apply(target, "wlan-test", intent)
    method, url = session.request.call_args.args
    assert method == "PUT" and url.path == "/proxy/network/api/s/default/rest/wlanconf/wlan-test"
    assert session.request.call_args.kwargs["json"] == intent
    assert session.request.call_args.kwargs["headers"]["X-API-Key"] == DATA["unifi_api_key"]
    for invalid in [
        dict(intent, name="new name"),
        dict(intent, mac_filter_list=[]),
        {"mac_filter_enabled": False, "mac_filter_list": []},
    ]:
        with pytest.raises(ProviderError):
            await client.apply(target, "wlan-test", invalid)
    with pytest.raises(ProviderError):
        await client.apply(target, "unmanaged", intent)
    assert session.request.call_count == 1


async def test_readback_single_object_identity(target):
    client = UniFi(MagicMock(), DATA)
    client._legacy = AsyncMock(
        return_value=[
            {
                "_id": "wrong",
                "networkconf_id": "network-test",
                "name": "WiFi",
                "mac_filter_enabled": False,
                "mac_filter_policy": "allow",
                "mac_filter_list": [],
            }
        ]
    )
    with pytest.raises(ProviderError, match="identity_changed"):
        await client.target(target, "wlan-test")
