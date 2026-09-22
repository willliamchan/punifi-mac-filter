# Troubleshooting

[← Back to the overview](../README.md)

> **Beta 0.1.0b1 troubleshooting.** Include your build and HA/provider versions when reporting a problem.

## HACS cannot install this repository

Check that HA is at least 2026.9.3, and select the beta version (or main) rather than an older documentation-only commit. Refresh the HACS repository information if it was added before code was published. Do not create placeholder files in your HA configuration.

Check that you added the repository as an **Integration**, downloaded it, and restarted HA if required before searching under **Add integration**.

## Cannot connect

Check the address and port from Home Assistant's network, not only from your browser. Enter the host and port separately; do not put a full URL or cloud portal address in Host. Confirm you are connecting to the correct service and that HTTPS is available.

Do not expose your firewall or controller to the public internet just to make the integration connect. Resolve local reachability deliberately.

## Certificate error

Check the certificate's expiry, hostname coverage and trust chain. Use a hostname that matches the certificate. Configure a proper trusted certificate/private-CA trust path for your environment rather than disabling verification; pUniFi will not provide a TLS bypass.

## Authentication or permission error

These are different problems:

- **Authentication:** the username/password or key is invalid, expired or revoked. Replace it through reauthentication/reconfigure.
- **Permission:** the credential is recognized but cannot perform the required operation. Review the provider account's permissions.
- **Unsupported capability:** the provider version/route/schema is not supported. Extra privileges will not necessarily fix it.

For pfSense, review the XML-RPC privilege caveat in [setup](setup.md#pfsense-permissions). For UniFi, successful read access does not guarantee permission to update WLAN filters. Do not assume Owner access is required or broaden permissions blindly.

## My network is missing from the dropdown

The UniFi target is a **Wi-Fi SSID**, with its network shown for context. A wired-only network is not an eligible WLAN filter target. Check the selected controller/site and whether the key can read the intended SSID.

The pfSense dropdown uses discovered DHCP interfaces, not a fixed list of names. Unsupported/incomplete provider responses should produce an error rather than a misleading partial list.

## Out of sync, but nothing changes

Check global Enable sync and that pair's Enable sync. Both must be enabled. Then check the paused reason or reported issue: an empty restricted list, changed identity/VLAN association, missing target or insufficient permission can block a write.

**Sync now** does not override these safeguards. Paused read-only comparison may correctly report Out of sync.

## A restricted list has no MAC addresses

Review the applicable static mappings in pfSense. “Only this interface” uses that interface's mappings; “any interface” uses the combined set.

The integration blocks an empty restricted allowlist until safe behavior is established for the supported UniFi version. It will not interpret it as “disable filtering” or silently open access.

## Synced, but a client cannot connect

Synced means the controller's filter matches pfSense-derived policy; it does not prove AP provisioning or client connectivity. Check:

- The client MAC actually used on that SSID, including private/randomized addressing.
- The policy and static mapping on the source interface.
- AP provisioning and association events in UniFi.
- Wi-Fi authentication and other network policy unrelated to MAC filtering.

Keep a separate management connection available while investigating. Do not remove unrelated network security settings as a shortcut.

## I paused or removed the integration, but the filter is still there

This is intentional. Stopping management does not undo previously applied UniFi settings. Review and change the filter directly in UniFi after pUniFi management has stopped. See [removal](installation.md#removing).

## Reporting a problem

Use [GitHub Issues](https://github.com/willliamchan/punifi-mac-filter/issues). For a runtime issue, include integration, HA, pfSense and UniFi versions; the affected workflow; expected versus observed behavior; and redacted error text.

Never include passwords, API keys, request headers, complete configuration backups or raw XML-RPC/controller responses. Redact hostnames, IPs, SSIDs, MAC addresses and site/interface identifiers unless you deliberately intend to publish them. Check attachments and screenshots as well as text.
