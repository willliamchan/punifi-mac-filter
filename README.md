# pUniFi MAC Filter

Keep selected UniFi Wi-Fi MAC filters aligned with your pfSense DHCP policies, from Home Assistant.

**pfSense → Home Assistant → UniFi. One way only.**

> **First test build: 0.1.0b2.** This is a beta, not a production-certified release. Start with sync disabled. Native HA tests and live read-only provider checks have been exercised; live filter changes and AP enforcement from this integration still need controlled user testing. See [test status](docs/testing.md).

## What does it do?

You manage your DHCP client policy and static MAC mappings in pfSense. pUniFi reads that configuration and updates the MAC filter on the UniFi Wi-Fi networks you explicitly choose.

For example, pair your pfSense **IoT** interface with your UniFi **Smart Home** SSID. When that interface allows only known clients, pUniFi will use its static DHCP MAC mappings as the SSID's allowlist. Their names do not need to match.

| Your pfSense policy | Result on the mapped UniFi SSID |
|---|---|
| Allow all clients | MAC filtering disabled |
| Allow known clients from only this interface | Allow only MAC addresses in this interface's static mappings |
| Allow known clients from any interface | Allow MAC addresses in static mappings across all pfSense DHCP interfaces |

**Only explicitly selected SSIDs are managed.** UniFi applies these filters to Wi-Fi SSIDs, not an entire wired network. The mapping selector will show the SSID alongside its network, VLAN and site so you can choose the right target.

## Features

- Install through HACS as a custom repository.
- Enter connection details in Home Assistant; no YAML or external scripts.
- Pick a pfSense interface and a UniFi target from two dropdowns, add the pair, and repeat.
- See the source policy, observed UniFi filter and sync status as HA entities.
- Sync automatically, or press a **Sync now** button for a particular target.
- Update credentials, change mappings or pause sync through the integration settings.
- Never write configuration back to pfSense.

## Get started

For the beta:

1. Follow the [installation guide](docs/installation.md).
2. Use the [setup guide](docs/setup.md) to connect both systems and add your mappings.
3. Read the [usage guide](docs/usage.md) for sync status, manual sync, pausing and reconfiguration.

If something does not work, start with [troubleshooting](docs/troubleshooting.md). Read [security and limitations](docs/security.md) before enabling writes.

## Before you enable sync

- **Start in observation-only mode.** Review the proposed filter before enabling sync.
- **pfSense is the source of truth.** While sync is enabled, manual changes to a mapped UniFi MAC filter will be replaced by the pfSense-derived policy.
- **DHCP policy and Wi-Fi admission are different.** A DHCP restriction controls address assignment; a Wi-Fi MAC filter can prevent a device from joining the SSID at all. Check your static mappings and keep a separate management connection available.
- **MAC filtering is not strong authentication.** MAC addresses can be spoofed. Keep appropriate Wi-Fi encryption and authentication enabled.
- **Pausing or uninstalling does not undo an applied filter.** It stops future management and leaves the current UniFi settings in place.

## Compatibility

This beta requires **Home Assistant 2026.9.3 or newer** (the tested baseline). Its live read-only clients were verified against **pfSense 2.9.0-RELEASE** and **UniFi OS Network 10.6.106**. Older versions and standalone Network Server installations are not claimed as supported. Connections use built-in pfSense XML-RPC with username/password and UniFi API-key access over verified HTTPS.

UniFi filter writes currently depend on a legacy controller API. An API key working with another UniFi integration does not guarantee it supports these operations. This beta targets the verified API layout rather than guessing alternative endpoints. See [known limitations](docs/security.md#known-limitations).

## Feedback

Use [GitHub Issues](https://github.com/willliamchan/punifi-mac-filter/issues) for documentation feedback and feature discussions. Include the beta version and redacted error details for test feedback. Never include credentials, full configuration exports or unredacted controller responses in an issue.

Licensed under the [MIT License](LICENSE).

This is an independent project, not an official pfSense, Netgate, Ubiquiti or Home Assistant product.
