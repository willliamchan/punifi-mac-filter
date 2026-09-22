"""Single-owner read/compare/write loop; fresh reads and bounded mutations."""

import asyncio
import logging
import time
from datetime import datetime, timezone

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, POLL_INTERVAL
from .policy import ProviderError, desired, mapping_reason, matches

_LOGGER = logging.getLogger(__name__)


class Coordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, pfsense, unifi, session):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=POLL_INTERVAL)
        self.entry = entry
        self.pfsense, self.unifi, self.session = pfsense, unifi, session
        self.lock = asyncio.Lock()
        self.stopping = False
        self.auth_provider = None
        self.retry = {}
        self.blocked = {}
        self.success = {}

    async def drain(self):
        """Stop admission BEFORE waiting; no queued writer can survive a save."""
        self.stopping = True
        async with self.lock:
            pass

    async def close(self):
        await self.drain()
        await self.async_shutdown()
        self.session.detach()

    def enabled(self, mapping):
        return (
            not self.stopping
            and self.entry.options.get("sync_enabled", False)
            and mapping.get("sync_enabled", False)
        )

    async def observe(self):
        source = await self.pfsense.read()
        self.source_read_at = time.monotonic()
        target = await self.unifi.read(self.entry.data["unifi_site_id"])
        self.verify(source, target)
        if time.monotonic() - self.source_read_at > 30:
            raise ProviderError("stale_source", "pfsense")
        return source, target

    def verify(self, source, target):
        if (
            source["identity"] != self.entry.data["pfsense_id"]
            or target["identity"] != self.entry.data["unifi_id"]
            or target["site"]["id"] != self.entry.data["unifi_site_id"]
        ):
            raise ProviderError("identity_changed")

    async def _async_update_data(self):
        try:
            return await self.run()
        except ProviderError as exc:
            if exc.code == "invalid_auth":
                self.auth_provider = exc.provider
                raise ConfigEntryAuthFailed("invalid_auth") from None
            raise UpdateFailed(exc.code) from None

    async def manual(self, target):
        mapping = next(
            (m for m in self.entry.options.get("mappings", []) if m["unifi_wlan_id"] == target), None
        )
        if mapping is None or not self.enabled(mapping):
            return
        if self.lock.locked():
            # An active cycle already owns this target; no parallel/queued writer.
            return
        try:
            result = await self.run(target)
        except ProviderError as exc:
            self.async_set_update_error(UpdateFailed(exc.code))
            if exc.code == "invalid_auth":
                self.auth_provider = exc.provider
                self.entry.async_start_reauth(self.hass)
            return
        self.async_set_updated_data(result)

    async def run(self, only=None):
        async with self.lock:
            if self.stopping:
                return self.data or {"source": None, "target": None, "sync": {}}
            source, target = await self.observe()
            source_time = self.source_read_at
            result = {"source": source, "target": target, "sync": {}}
            for mapping in self.entry.options.get("mappings", []):
                key = mapping["unifi_wlan_id"]
                observed = target["wlans"].get(key)
                active = self.enabled(mapping)
                reason = mapping_reason(source, observed, mapping)
                state = {
                    "state": None,
                    "sync_enabled": bool(active),
                    "paused_reason": reason or (None if active else "sync_paused"),
                    "desired_mac_count": None,
                    "observed_mac_count": len(observed["macs"]) if observed else None,
                    "last_successful_sync": self.success.get(key),
                }
                result["sync"][key] = state
                if reason:
                    continue
                try:
                    intent = desired(source, mapping["pfsense_interface_id"])
                except ProviderError as exc:
                    state["paused_reason"] = exc.code
                    continue
                state["desired_mac_count"] = len(intent.get("mac_filter_list", []))
                state["state"] = "Synced" if matches(observed, intent) else "Out of sync"
                if state["state"] == "Synced":
                    self._success(key, state)
                    continue
                if not active or (only is not None and key != only):
                    continue
                if key in self.blocked:
                    state["paused_reason"] = self.blocked[key]
                    continue
                attempts, deadline = self.retry.get(key, (0, 0))
                if time.monotonic() < deadline:
                    state["paused_reason"] = "retry_backoff"
                    continue
                try:
                    # Recheck before each target; avoid authorizing with old data
                    # when an earlier request used the shared freshness budget.
                    if time.monotonic() - source_time > 30:
                        source, target = await self.observe()
                        source_time = self.source_read_at
                        result.update(source=source, target=target)
                        intent = desired(source, mapping["pfsense_interface_id"])
                    observed = await self.unifi.target(target, key)
                    # The exact-target read also consumes the source budget.
                    # Fail this cycle closed; the next poll starts with new reads.
                    if time.monotonic() - source_time > 30:
                        raise ProviderError("stale_source", "pfsense")
                    reason = mapping_reason(source, observed, mapping)
                    if reason:
                        raise ProviderError(reason)
                    if self.stopping:
                        state["paused_reason"] = "sync_paused"
                        continue
                    if matches(observed, intent):
                        target["wlans"][key] = observed
                        state["state"] = "Synced"
                        self._success(key, state)
                        continue
                    state["state"] = "Processing"
                    self.data = result
                    self.async_update_listeners()
                    await self.unifi.apply(target, key, intent)
                    observed = await self.unifi.target(target, key)
                    # A source edit during apply must invalidate old success.
                    fresh_source = await self.pfsense.read()
                    self.verify(fresh_source, target)
                    source = fresh_source
                    source_time = time.monotonic()
                    result["source"] = source
                    reason = mapping_reason(source, observed, mapping)
                    if reason:
                        raise ProviderError(reason)
                    intent = desired(source, mapping["pfsense_interface_id"])
                    target["wlans"][key] = observed
                    state["desired_mac_count"] = len(intent.get("mac_filter_list", []))
                    state["observed_mac_count"] = len(observed["macs"])
                    state["state"] = "Synced" if matches(observed, intent) else "Out of sync"
                    if state["state"] == "Synced":
                        self._success(key, state)
                    else:
                        self._retry(key, attempts)
                except ProviderError as exc:
                    state["state"] = None
                    state["paused_reason"] = exc.code
                    if exc.code in ("invalid_auth", "identity_changed") or exc.provider == "pfsense":
                        # A failed/refreshed source invalidates every pending
                        # target, not only the target that prompted the read.
                        raise
                    if exc.code in (
                        "insufficient_permissions",
                        "unsupported_api",
                        "unsupported_schema",
                        "identity_changed",
                    ):
                        self.blocked[key] = exc.code
                    else:
                        self._retry(key, attempts)
            # A later target may refresh the source: recompute every comparison
            # from the FINAL shared source, never retain a stale Synced label.
            for mapping in self.entry.options.get("mappings", []):
                key = mapping["unifi_wlan_id"]
                state = result["sync"][key]
                if state["state"] is None:
                    continue
                try:
                    row = result["target"]["wlans"].get(key)
                    reason = mapping_reason(result["source"], row, mapping)
                    if reason:
                        raise ProviderError(reason)
                    intent = desired(result["source"], mapping["pfsense_interface_id"])
                    state["state"] = "Synced" if matches(row, intent) else "Out of sync"
                    state["desired_mac_count"] = len(intent.get("mac_filter_list", []))
                    state["observed_mac_count"] = len(row["macs"])
                except ProviderError as exc:
                    state.update(state=None, paused_reason=exc.code)
            return result

    def _success(self, key, state):
        self.success[key] = datetime.now(timezone.utc).isoformat()
        state["last_successful_sync"] = self.success[key]
        self.retry.pop(key, None)

    def _retry(self, key, attempts):
        delay = (10, 30, 60)[min(attempts, 2)]
        self.retry[key] = (attempts + 1, time.monotonic() + delay)
