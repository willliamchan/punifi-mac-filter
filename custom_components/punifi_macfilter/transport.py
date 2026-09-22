"""Bounded HTTPS transport; errors never contain response bodies or endpoints."""

import asyncio
import ipaddress
import re
import ssl

import aiohttp
from yarl import URL

from .const import MAX_RESPONSE, TIMEOUT
from .policy import ProviderError


def endpoint(host, port):
    if not isinstance(host, str) or not host or host != host.strip() or "%" in host:
        raise ProviderError("invalid_endpoint")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ProviderError("invalid_endpoint")
    # Accept a bare IPv6 address, never a URL, bracket/port string or zone id.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", p) for p in host.split(".")
        ):
            raise ProviderError("invalid_endpoint") from None
    return URL.build(scheme="https", host=host, port=port)


class Transport:
    def __init__(self, session, host, port, provider, headers=None, auth=None):
        self.session = session
        self.base = endpoint(host, port)
        self.provider = provider
        self.headers = headers or {}
        if any(
            not isinstance(v, str) or any(ord(c) < 32 or ord(c) == 127 for c in v)
            for v in self.headers.values()
        ):
            raise ProviderError("invalid_auth", provider)
        self.auth = auth

    async def request(self, method, path, **kwargs):
        try:
            async with asyncio.timeout(TIMEOUT):
                async with self.session.request(
                    method,
                    self.base.with_path(path.split("?", 1)[0]).with_query(
                        path.split("?", 1)[1] if "?" in path else None
                    ),
                    headers=self.headers,
                    auth=self.auth,
                    allow_redirects=False,
                    ssl=True,
                    **kwargs,
                ) as response:
                    status = response.status
                    if status == 401:
                        raise ProviderError("invalid_auth", self.provider)
                    if status == 403:
                        raise ProviderError("insufficient_permissions", self.provider)
                    if 300 <= status < 400:
                        raise ProviderError("redirect_blocked", self.provider)
                    if status in (404, 405):
                        raise ProviderError("unsupported_api", self.provider)
                    if status >= 400:
                        raise ProviderError("cannot_connect", self.provider)
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_RESPONSE:
                            raise ProviderError("unsupported_schema", self.provider)
                        chunks.append(chunk)
                    return b"".join(chunks)
        except aiohttp.ClientConnectorCertificateError, aiohttp.ClientSSLError, ssl.SSLError:
            raise ProviderError("tls_error", self.provider) from None
        except aiohttp.ClientError, TimeoutError, OSError:
            raise ProviderError("cannot_connect", self.provider) from None
