# pUniFi MAC Filter

Keep selected UniFi Wi-Fi MAC filters aligned with your pfSense DHCP policies, from Home Assistant.

**pfSense → Home Assistant → UniFi. One way only.**

> **Development status: documentation only.** The integration has not been built or released. This repository cannot currently be installed through HACS. The guides describe the planned first release; screenshots, tested versions and release instructions will be added after verification.

## What will it do?

You manage your DHCP client policy and static MAC mappings in pfSense. pUniFi reads that configuration and updates the MAC filter on the UniFi Wi-Fi networks you explicitly choose.

For example, pair your pfSense **IoT** interface with your UniFi **Smart Home** SSID. When that interface allows only known clients, pUniFi will use its static DHCP MAC mappings as the SSID's allowlist. Their names do not need to match.

| Your pfSense policy | Result on the mapped UniFi SSID |
|---|---|
| Allow all clients | MAC filtering disabled |
| Allow known clients from only this interface | Allow only MAC addresses in this interface's static mappings |
| Allow known clients from any interface | Allow MAC addresses in static mappings across all pfSense DHCP interfaces |

**Only explicitly selected SSIDs are managed.** UniFi applies these filters to Wi-Fi SSIDs, not an entire wired network. The mapping selector will show the SSID alongside its network, VLAN and site so you can choose the right target.

## Planned features

- Install through HACS as a custom repository.
- Enter connection details in Home Assistant; no YAML or external scripts.
- Pick a pfSense interface and a UniFi target from two dropdowns, add the pair, and repeat.
- See the source policy, observed UniFi filter and sync status as HA entities.
- Sync automatically, or press a **Sync now** button for a particular target.
- Update credentials, change mappings or pause sync through the integration settings.
- Never write configuration back to pfSense.

## Get started

When an installable release is available:

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

No supported-version matrix is available yet. The planned connection methods are pfSense's built-in XML-RPC with username/password and UniFi Network access with an API key, over certificate-verified HTTPS.

UniFi filter writes currently depend on a legacy controller API. An API key working with another UniFi integration does not guarantee it supports these operations. Supported pfSense, UniFi and Home Assistant versions will be published after testing. See [known limitations](docs/security.md#known-limitations).

## Feedback

Use [GitHub Issues](https://github.com/willliamchan/punifi-mac-filter/issues) for documentation feedback and feature discussions. There is no installable integration to troubleshoot yet. Never include credentials, full configuration exports or unredacted controller responses in an issue.

This is an independent project, not an official pfSense, Netgate, Ubiquiti or Home Assistant product.
