# Daily use

[← Back to the overview](../README.md)

> **Beta 0.1.0b2.** The entities and controls below are implemented. Test first with sync disabled; controller-write and AP behavior in your environment still require controlled verification.

## Where to make changes

Manage DHCP policy and static MAC mappings in **pfSense**, not in HA or UniFi. Home Assistant reads those settings and applies the resulting filter to the mapped UniFi SSIDs.

Automatic source polling targets a 10-second interval. This is not a promise of Wi-Fi enforcement within 10 seconds: network requests and UniFi provisioning can take longer.

With sync enabled, a manual change to a managed UniFi MAC filter will be treated as drift and replaced by the pfSense-derived policy. Pause that mapping first if you want to manage its filter directly.

## Entities you will see

| Entity | What it tells you |
|---|---|
| **pUniFi pfSense DHCP &lt;Interface&gt;** | The interface's DHCP policy. Its `mac_addresses` attribute lists only that interface's static MAC mappings. |
| **pUniFi UniFi MAC Filter &lt;SSID&gt;** | The filter actually read from UniFi: Disabled, Allow or Deny, with its observed enabled/mode/list attributes. |
| **pUniFi Sync &lt;SSID&gt;** | Whether this mapped target matches its current source policy. |
| **pUniFi Sync now &lt;SSID&gt;** | A button requesting an immediate guarded sync for this target. |

Only pfSense interfaces used by a saved pair get source sensors. Multiple pairs using the same interface share one source sensor. Removing the last pair using an interface retires that sensor; upgrading from 0.1.0b1 also removes previously created unpaired source sensors on successful integration setup. UniFi observed sensors remain unchanged. All interfaces remain available in the pairing dropdown.

Initial entity IDs follow these patterns:

```text
sensor.punifi_pfsense_dhcp_<interface_slug>
sensor.punifi_unifi_macfilter_<ssid_slug>
sensor.punifi_sync_<ssid_slug>
button.punifi_sync_<ssid_slug>
```

Home Assistant may add a suffix to avoid name collisions. Renaming a source or target should not create a new entity or lose its history. Use the actual ID shown by your HA entity registry in automations.

For **Allow known clients from any interface**, the applied allowlist includes static MAC mappings from every pfSense DHCP interface, including unmapped interfaces. A source sensor still shows only its own interface's list; it is not the combined applied list.

## Understanding sync status

| Status | Meaning | What to do |
|---|---|---|
| **Synced** | Fresh pfSense policy and observed UniFi filter agree. | Nothing needed. This confirms controller configuration, not every AP's enforcement. |
| **Processing** | A reconciliation is actually in progress. | Let it finish; repeatedly pressing Sync now does not create extra parallel writes. |
| **Out of sync** | Current valid observations differ and no reconciliation is running. | Check whether sync is paused or a safety/permission issue blocks updates. |
| **Unavailable** | The integration cannot make a trustworthy comparison. | Check connections, credentials and the reported issue. This is not proof of a policy mismatch. |

Sync enablement is separate from status. A paused target can still show **Synced** or **Out of sync** because read-only comparison continues. The sync entity's `sync_enabled` and `paused_reason` attributes will explain whether writes are allowed.

## Manual sync

Press **pUniFi Sync now &lt;SSID&gt;** to request fresh reads and immediate reconciliation for that pair. You can use the native Home Assistant button control or `button.press` in an automation.

- Already matched? It checks and makes no write.
- Paused? The button is unavailable by design. Both global and per-pair sync must be enabled. **Enabling both permits automatic writes immediately**; do not enable them merely to make the button available.
- Invalid data, identity change or permission failure? Manual sync does not bypass protection or retry backoff.
- Another sync running? Requests are coalesced rather than run concurrently.

The button only sends policy **from pfSense to UniFi**. It never imports a UniFi change into pfSense.

## Pause or resume

Open **Settings → Devices & services → pUniFi MAC Filter → Configure** (the options control). Use **Edit pair** for per-target enablement and **Review sync enablement and save** for global enablement. Host/credential changes use **Reconfigure** in the entry menu.

- **Global Enable sync:** pause or resume writes for the entire entry.
- **Per-pair Enable sync:** choose which confirmed mappings can write.

If a provider is offline, the options flow still allows global sync to be disabled; reconnect before adding/editing mappings or enabling sync.

Both must be on for a mapping to apply changes. Turning global sync back on does not enable pairs you individually disabled. Resuming requires fresh reads.

**Pause is not undo.** A write already in progress may finish before pausing completes. Pausing prevents further work but leaves the applied UniFi filter in place.

## Change addresses or credentials

Use **Reconfigure** on the integration entry. Edit host/port or replace credentials there, not in HA's storage files.

- Leave an unchanged secret blank to retain it.
- Replacement details must validate before saving.
- Failed validation or cancellation leaves the previous configuration intact.
- The same verified firewall/controller/site keeps its mappings and entities.
- A different appliance or site requires mapping review and renewed enablement; it cannot silently inherit write authority.

If a credential expires or is revoked, follow the integration's reauthentication prompt. It requests the affected provider's credentials rather than creating a duplicate integration entry. If the failure context is unavailable after restart, it first asks which provider needs reauthentication.

## Change or remove a mapping

Use the mapping editor to add, edit, disable or remove a pair. Review the desired policy and target before confirming a reassignment. Changes to a mapped target's VLAN/network association require review rather than automatic remapping.

Removing a pair stops management of that SSID and removes its mapping-specific sync/button entities. It does not reset the filter, delete the SSID or remove pfSense mappings. Newly discovered SSIDs remain unmanaged until explicitly selected.
