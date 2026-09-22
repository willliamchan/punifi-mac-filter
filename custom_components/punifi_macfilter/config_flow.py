"""Native connection and mapping flows; drafts never write to providers."""

from contextlib import asynccontextmanager
from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import DOMAIN, NAME, POLICIES
from .pfsense import PfSense
from .policy import ProviderError, desired, mapping_reason
from .transport import endpoint
from .unifi import UniFi

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def connection_schema(provider, data, optional=False):
    fields = {
        vol.Required(f"{provider}_host", default=data.get(f"{provider}_host", "")): str,
        vol.Required(f"{provider}_port", default=data.get(f"{provider}_port", 443)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
    if provider == "pfsense":
        fields[vol.Required("pfsense_username", default=data.get("pfsense_username", ""))] = str
    key = "pfsense_password" if provider == "pfsense" else "unifi_api_key"
    fields[vol.Optional(key) if optional else vol.Required(key)] = PASSWORD
    return vol.Schema(fields)


def update_connection(old, submitted, provider):
    new = dict(old)
    secret = "pfsense_password" if provider == "pfsense" else "unifi_api_key"
    keys = [f"{provider}_host", f"{provider}_port", secret]
    if provider == "pfsense":
        keys.append("pfsense_username")
    for key in keys:
        if key in submitted and (key != secret or submitted[key]):
            new[key] = submitted[key]
    endpoint(new[f"{provider}_host"], new[f"{provider}_port"])
    if not new.get(secret) or (provider == "pfsense" and not new.get("pfsense_username")):
        raise ProviderError("invalid_auth")
    return new


@asynccontextmanager
async def flow_session(hass):
    session = async_create_clientsession(hass, auto_cleanup=False)
    try:
        yield session
    finally:
        session.detach()


async def read_source(hass, data):
    async with flow_session(hass) as session:
        return await PfSense(session, data).read()


async def read_sites(hass, data):
    async with flow_session(hass) as session:
        return await UniFi(session, data).sites()


async def discover(hass, data):
    async with flow_session(hass) as session:
        source = await PfSense(session, data).read()
        target = await UniFi(session, data).read(data["unifi_site_id"])
        return source, target


def entry_identity(data):
    return f"{data['pfsense_id']}:{data['unifi_id']}:{data['unifi_site_id']}"


class MappingEditor:
    """One native pair editor reused for setup, reconfigure and options."""

    def init_editor(self, data, options, entry=None):
        self.draft = deepcopy(dict(data))
        self.options = deepcopy(dict(options))
        self.options.setdefault("sync_enabled", False)
        self.options.setdefault("mappings", [])
        self.edit_entry = entry
        self.baseline = (deepcopy(dict(entry.data)), deepcopy(dict(entry.options))) if entry else None
        self.pf_snapshot = self.target = None
        self.edit_target = None
        self.preview = None

    def conflict(self):
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if self.edit_entry and other.entry_id == self.edit_entry.entry_id:
                continue
            if other.data.get("unifi_id") == self.draft.get("unifi_id") and other.data.get(
                "unifi_site_id"
            ) == self.draft.get("unifi_site_id"):
                owned = {m["unifi_wlan_id"] for m in other.options.get("mappings", [])}
                if any(m["unifi_wlan_id"] in owned for m in self.options["mappings"]):
                    return True
        return False

    def validate_save(self):
        """Recheck ownership and the draft baseline after every save-time wait."""
        if self.edit_entry and self.baseline != (dict(self.edit_entry.data), dict(self.edit_entry.options)):
            raise ProviderError("configuration_changed")
        if self.conflict():
            raise ProviderError("duplicate_target")

    @asynccontextmanager
    async def save_guard(self):
        runtime = getattr(self.edit_entry, "runtime_data", None)
        if runtime:
            # Drain the active writer without changing admission until this
            # flow owns the lock. Cancellation while waiting changes nothing.
            await runtime.lock.acquire()
        stopped_here = committed = False
        try:
            self.validate_save()
            if runtime:
                if runtime.stopping or getattr(self.edit_entry, "runtime_data", None) is not runtime:
                    raise ProviderError("configuration_changed")
                runtime.stopping = stopped_here = True
            yield
            committed = True
        finally:
            if runtime:
                if stopped_here and not committed:
                    runtime.stopping = False
                runtime.lock.release()

    async def refresh(self):
        source, target = await discover(self.hass, self.draft)
        if source["identity"] != self.draft["pfsense_id"] or target["identity"] != self.draft["unifi_id"]:
            raise ProviderError("identity_changed")
        self.pf_snapshot, self.target = source, target

    async def async_step_mappings(self, user_input=None):
        summary = f"{len(self.options['mappings'])} pair(s). No changes are applied until Save."
        menu = (
            ["pair", "edit_pair", "remove_pair", "finish"] if self.pf_snapshot and self.target else ["finish"]
        )
        if self.pf_snapshot is None:
            summary += " Provider reads failed. You can still disable global sync; enablement requires fresh valid reads."
        return self.async_show_menu(
            step_id="mappings", menu_options=menu, description_placeholders={"summary": summary}
        )

    async def async_step_pair(self, user_input=None):
        errors = {}
        interfaces = self.pf_snapshot["interfaces"]
        wlans = self.target["wlans"]
        if not interfaces or not wlans:
            return self.async_abort(reason="no_targets")
        existing = next((m for m in self.options["mappings"] if m["unifi_wlan_id"] == self.edit_target), None)
        if user_input is not None:
            try:
                source_id = user_input["pfsense_interface_id"]
                target_id = user_input["unifi_wlan_id"]
                row, target = interfaces[source_id], wlans[target_id]
                if any(
                    m["unifi_wlan_id"] == target_id and m["unifi_wlan_id"] != self.edit_target
                    for m in self.options["mappings"]
                ):
                    raise ProviderError("duplicate_target")
                self.preview = {
                    "pfsense_interface_id": source_id,
                    "unifi_wlan_id": target_id,
                    "unifi_network_id": target["network_id"],
                    "pfsense_vlan_id": row["vlan"],
                    "unifi_vlan_id": target["vlan"],
                    "sync_enabled": user_input["sync_enabled"],
                }
                return await self.async_step_pair_preview()
            except ProviderError as exc:
                errors["base"] = exc.code
            except KeyError:
                errors["base"] = "missing_target"
        source_labels = {
            k: f"{r['name']} ({k}; {r['subnet']}; VLAN {r['vlan'] if r['vlan'] else 'untagged/unknown'})"
            for k, r in interfaces.items()
        }
        target_labels = {
            k: f"{r['name']} / {r['network_name']} / VLAN {r['vlan'] if r['vlan'] else 'untagged/unknown'} / {self.target['site']['name']}"
            for k, r in wlans.items()
        }
        target_default = (
            existing["unifi_wlan_id"]
            if existing and existing["unifi_wlan_id"] in wlans
            else next(iter(wlans))
        )
        tag = wlans[target_default]["vlan"]
        suggestions = [k for k, r in interfaces.items() if tag is not None and r["vlan"] == tag]
        source_default = (
            existing["pfsense_interface_id"]
            if existing and existing["pfsense_interface_id"] in interfaces
            else (suggestions[0] if len(suggestions) == 1 else vol.UNDEFINED)
        )
        schema = vol.Schema(
            {
                vol.Required("pfsense_interface_id", default=source_default): vol.In(source_labels),
                vol.Required("unifi_wlan_id", default=target_default): vol.In(target_labels),
                vol.Required(
                    "sync_enabled", default=existing.get("sync_enabled", False) if existing else False
                ): bool,
            }
        )
        return self.async_show_form(step_id="pair", data_schema=schema, errors=errors)

    async def async_step_pair_preview(self, user_input=None):
        m = self.preview
        if m is None:
            return await self.async_step_mappings()
        if user_input is not None:
            if user_input.get("confirm"):
                self.options["mappings"] = [
                    r for r in self.options["mappings"] if r["unifi_wlan_id"] != self.edit_target
                ]
                self.options["mappings"].append(m)
            self.edit_target = self.preview = None
            return await self.async_step_mappings()
        row = self.pf_snapshot["interfaces"][m["pfsense_interface_id"]]
        target = self.target["wlans"][m["unifi_wlan_id"]]
        try:
            intent = desired(self.pf_snapshot, row["id"])
            count = str(len(intent.get("mac_filter_list", [])))
        except ProviderError as exc:
            count = f"blocked: {exc.code}"
        summary = (
            f"{row['name']} → {target['name']}\n\n{POLICIES[row['policy']]}\n\n"
            f"Desired MAC count: {count}. Observed: {'enabled' if target['enabled'] else 'disabled'}, "
            f"{target['mode']}, {len(target['macs'])} MACs. Sync for this pair: {m['sync_enabled']}."
        )
        return self.async_show_form(
            step_id="pair_preview",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"preview": summary},
        )

    async def select_pair(self, step, user_input):
        pairs = self.options["mappings"]
        if not pairs:
            return await self.async_step_mappings()
        if user_input is not None:
            key = user_input["target"]
            if key not in {m["unifi_wlan_id"] for m in pairs}:
                return self.async_abort(reason="missing_target")
            if step == "remove_pair":
                self.options["mappings"] = [m for m in pairs if m["unifi_wlan_id"] != key]
                return await self.async_step_mappings()
            self.edit_target = key
            return await self.async_step_pair()
        labels = {
            m["unifi_wlan_id"]: self.target["wlans"].get(m["unifi_wlan_id"], {}).get("name", "Missing target")
            for m in pairs
        }
        return self.async_show_form(
            step_id=step, data_schema=vol.Schema({vol.Required("target"): vol.In(labels)})
        )

    async def async_step_edit_pair(self, user_input=None):
        return await self.select_pair("edit_pair", user_input)

    async def async_step_remove_pair(self, user_input=None):
        return await self.select_pair("remove_pair", user_input)

    async def async_step_finish(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                enabled = user_input["sync_enabled"]
                # A pure pause must remain possible when a provider is offline.
                # New connection entries/reconfigure still require validation.
                if enabled or not isinstance(self, OptionsFlow):
                    await self.refresh()
                if self.conflict():
                    raise ProviderError("duplicate_target")
                if self.edit_entry and self.baseline != (
                    dict(self.edit_entry.data),
                    dict(self.edit_entry.options),
                ):
                    raise ProviderError("configuration_changed")
                enabled = user_input["sync_enabled"]
                for m in self.options["mappings"]:
                    if enabled and m["sync_enabled"]:
                        reason = mapping_reason(
                            self.pf_snapshot, self.target["wlans"].get(m["unifi_wlan_id"]), m
                        )
                        if reason:
                            raise ProviderError(reason)
                        desired(self.pf_snapshot, m["pfsense_interface_id"])
                self.options["sync_enabled"] = enabled
                async with self.save_guard():
                    return await self.save()
            except ProviderError as exc:
                errors["base"] = exc.code
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema(
                {
                    vol.Required("sync_enabled", default=self.options["sync_enabled"]): bool,
                }
            ),
            errors=errors,
            description_placeholders={"count": str(len(self.options["mappings"]))},
        )


class ConfigFlow(MappingEditor, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()

    async def async_step_user(self, user_input=None):
        if not hasattr(self, "draft"):
            self.init_editor({}, {})
        errors = {}
        if user_input is not None:
            try:
                candidate = update_connection(self.draft, user_input, "pfsense")
                source = await read_source(self.hass, candidate)
                candidate["pfsense_id"] = source["identity"]
                self.draft = candidate
                return await self.async_step_unifi()
            except ProviderError as exc:
                errors["base"] = exc.code
        return self.async_show_form(
            step_id="user",
            data_schema=connection_schema("pfsense", self.draft, bool(self.edit_entry)),
            errors=errors,
            description_placeholders={
                "help_url": "https://github.com/willliamchan/punifi-mac-filter/blob/main/docs/setup.md"
            },
        )

    async def async_step_unifi(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                candidate = update_connection(self.draft, user_input, "unifi")
                self.sites = await read_sites(self.hass, candidate)
                if not self.sites:
                    raise ProviderError("no_targets")
                self.draft = candidate
                return await self.async_step_site()
            except ProviderError as exc:
                errors["base"] = exc.code
        return self.async_show_form(
            step_id="unifi",
            data_schema=connection_schema("unifi", self.draft, bool(self.edit_entry)),
            errors=errors,
            description_placeholders={
                "help_url": "https://github.com/willliamchan/punifi-mac-filter/blob/main/docs/setup.md"
            },
        )

    async def async_step_site(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                site = next((s for s in self.sites if s["id"] == user_input["site"]), None)
                if site is None:
                    raise ProviderError("missing_target")
                candidate = dict(self.draft, unifi_site_id=site["id"], unifi_site_reference=site["reference"])
                source, target = await discover(self.hass, candidate)
                candidate.update(pfsense_id=source["identity"], unifi_id=target["identity"])
                new_id = entry_identity(candidate)
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    if entry is not self.edit_entry and entry.unique_id == new_id:
                        return self.async_abort(reason="already_configured")
                if self.edit_entry and entry_identity(self.edit_entry.data) != new_id:
                    self.options = {"sync_enabled": False, "mappings": []}
                self.draft, self.pf_snapshot, self.target = candidate, source, target
                return await self.async_step_mappings()
            except ProviderError as exc:
                errors["base"] = exc.code
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema({vol.Required("site"): vol.In({s["id"]: s["name"] for s in self.sites})}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        if not hasattr(self, "draft"):
            entry = self._get_reconfigure_entry()
            self.init_editor(entry.data, entry.options, entry)
        return await self.async_step_user(user_input)

    async def save(self):
        uid = entry_identity(self.draft)
        if self.edit_entry:
            return self.async_update_reload_and_abort(
                self.edit_entry, data=self.draft, options=self.options, unique_id=uid
            )
        await self.async_set_unique_id(uid)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=NAME, data=self.draft, options=self.options)

    async def async_step_reauth(self, entry_data):
        entry = self._get_reauth_entry()
        self.init_editor(entry.data, entry.options, entry)
        self.reauth_provider = getattr(getattr(entry, "runtime_data", None), "auth_provider", None)
        if self.reauth_provider not in ("pfsense", "unifi"):
            return await self.async_step_reauth_provider()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_provider(self, user_input=None):
        if user_input is not None:
            self.reauth_provider = user_input["provider"]
            return await self.async_step_reauth_confirm()
        return self.async_show_form(
            step_id="reauth_provider",
            data_schema=vol.Schema({vol.Required("provider"): vol.In(["pfsense", "unifi"])}),
        )

    async def async_step_reauth_confirm(self, user_input=None):
        provider = self.reauth_provider
        secret = "pfsense_password" if provider == "pfsense" else "unifi_api_key"
        errors = {}
        if user_input is not None:
            try:
                candidate = update_connection(self.draft, user_input, provider)
                # Validate only the affected provider; no unrelated rotation.
                if provider == "pfsense":
                    result = await read_source(self.hass, candidate)
                    expected = self.draft["pfsense_id"]
                else:
                    async with flow_session(self.hass) as session:
                        result = await UniFi(session, candidate).read(candidate["unifi_site_id"])
                    expected = self.draft["unifi_id"]
                if result["identity"] != expected:
                    raise ProviderError("identity_changed")
                if self.baseline != (dict(self.edit_entry.data), dict(self.edit_entry.options)):
                    raise ProviderError("configuration_changed")
                async with self.save_guard():
                    return self.async_update_reload_and_abort(self.edit_entry, data=candidate)
            except ProviderError as exc:
                errors["base"] = exc.code
        fields = {vol.Required(secret): PASSWORD}
        if provider == "pfsense":
            fields[vol.Required("pfsense_username", default=self.draft["pfsense_username"])] = str
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema(fields), errors=errors)


class OptionsFlow(MappingEditor, config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if not hasattr(self, "draft"):
            self.init_editor(self.config_entry.data, self.config_entry.options, self.config_entry)
        try:
            await self.refresh()
        except ProviderError:
            self.pf_snapshot = self.target = None
        return await self.async_step_mappings()

    async def save(self):
        # Even unchanged options must resume a drained coordinator via reload.
        if self.options == dict(self.config_entry.options):
            runtime = getattr(self.config_entry, "runtime_data", None)
            if runtime:
                runtime.stopping = False
        return self.async_create_entry(title="", data=self.options)
