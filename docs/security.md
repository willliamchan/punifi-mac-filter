# Security and limitations

[← Back to the overview](../README.md)

> **Beta 0.1.0b2.** The safeguards below are implemented and covered by focused tests, not a comprehensive security certification. Live deployment and AP enforcement remain separate tests. See [test status](testing.md).

## Strictly one-way

pfSense is authoritative. The integration reads DHCP policies and static MAC mappings and writes only the MAC-filter fields on explicitly mapped UniFi WLANs.

It does not write to pfSense, synchronize UniFi changes back to the firewall, edit SSIDs/VLANs/Wi-Fi passwords, manage wired switch ports, or enroll new targets automatically. A sync button uses the same guarded path as automatic sync.

## Credentials and connection security

- Use certificate-verified HTTPS. There is no HTTP fallback, redirect following or TLS-verification bypass.
- pfSense's **System - HA node sync** privilege gives broad effective XML-RPC authority. The integration's fixed read-only behavior does not make a stolen credential read-only.
- UniFi needs authority to read and change the selected WLAN filters. The minimum supported role is not yet established; do not assume a console Owner account is necessary.
- Setup, reconfigure and reauthentication will not make trial UniFi writes to check permissions.
- Credentials use Home Assistant's normal config-entry storage, not a separate vault. Masked UI fields are not at-rest encryption. Someone with sufficient access to HA's configuration or backups may recover them.
- Protect backups according to your HA version and destination. Do not assume every downloaded/decrypted historical backup is encrypted.
- Passwords, keys and raw provider responses must not appear in logs, entities, diagnostics or issue reports.

## Functional data is visible in Home Assistant

The requested sensors expose selected DHCP/filter information, including MAC lists. Authorized HA users can see that information, and Recorder, backups, exports and downstream consumers may retain it. Stable interface/site/WLAN identifiers are also needed for mappings and entity identity.

Deleting an integration entry does not erase historical backups or revoke provider credentials. Revoke unused credentials separately and follow your normal retention policy.

## Safety when applying filters

A pfSense DHCP policy controls address assignment. A UniFi Wi-Fi MAC filter controls association and may disconnect or prevent clients joining. These are related but not equivalent controls. Keep working Wi-Fi authentication and a separate management path.

The first-run default is observation-only. Writes require explicit global and per-mapping enablement, fresh valid source/target observations, a confirmed mapping and supported policy semantics.

Invalid, stale or incomplete data must not be converted into an empty policy or “allow all.” Restricted empty lists are blocked until safe semantics are established. Controller success requires readback, not just an accepted HTTP response.

Pausing, removing a mapping or uninstalling stops management; it does not restore old filters. Restore settings deliberately, checking for intervening changes. There is no automatic rollback claim.

## Known limitations

- An installable beta package and HA-native tests are available. A full browser-driven HACS installation and live end-to-end filter enforcement remain unverified.
- The intended UniFi filter writer uses a legacy API whose behavior may vary by version.
- Minimum UniFi write role, maximum supported MAC-list size, empty restricted-list semantics and cross-version compatibility remain unverified.
- A Synced sensor will confirm controller configuration equality, not AP enforcement or client reachability.
- The 10-second polling target is not a guaranteed end-to-end convergence time.
- MAC addresses can be spoofed; allowlists do not replace secure Wi-Fi authentication.
- HA 2026.9.3 is the tested baseline. Read-only clients were verified on pfSense 2.9.0-RELEASE and UniFi OS Network 10.6.106. Cross-version support is not implied.

## Private security reports

Do not post credentials or exploitable sensitive details in a public issue. A private vulnerability-reporting route has not been established yet. Until one is published, use a non-sensitive contact request rather than disclosing details publicly. A documented private reporting route is part of release preparation.
