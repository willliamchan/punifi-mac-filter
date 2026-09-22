# Installation

[← Back to the overview](../README.md)

> **Release 0.1.0.** Start with controlled observation-only testing. Start with global and per-pair sync disabled. See [what has been verified](testing.md) before enabling a write.

## What you will need

- Home Assistant **2026.9.3 or newer**, with support for custom integrations.
- [HACS](https://www.hacs.xyz/docs/use/) installed and working. HACS is a separate community project; install it using its own guide first.
- A pfSense firewall and a UniFi Network controller that Home Assistant can reach directly over HTTPS.
- Credentials for both systems. See [connection setup](setup.md).
- At least one UniFi Wi-Fi SSID to map to a pfSense DHCP interface.
- A Home Assistant backup before installing a new custom integration.

Read-only provider compatibility was verified on pfSense **2.9.0-RELEASE** and UniFi OS Network **10.6.106**. Standalone Network Server is not supported by this release. Home Assistant Cloud is not a substitute for network access from HA to your firewall/controller.

## Install through HACS

[![Open HACS repository on your Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=willliamchan&repository=punifi-mac-filter&category=integration)

With HACS already installed, click the banner and follow the prompts to open/add this repository and download **0.1.0**. This does not configure credentials or enable sync. Alternatively, add it manually:

1. Open **HACS** in Home Assistant.
2. Open its menu and choose **Custom repositories**. Menu placement may vary by HACS version.
3. Paste this repository URL:

   ```text
   https://github.com/willliamchan/punifi-mac-filter
   ```

4. Choose **Integration** as the repository type and add it.
5. Find **pUniFi MAC Filter** in HACS. Select the normal release **0.1.0**; enabling beta/pre-release versions is not required.
6. Restart Home Assistant if prompted, so it can load the integration.
7. Go to **Settings → Devices & services → Add integration**.
8. Search for **pUniFi MAC Filter** and follow the [setup guide](setup.md).

Installing files through HACS and adding the integration in Home Assistant are separate steps. HACS handles the files; the HA setup popup connects your devices and configures mappings.

## Updating

Read the release notes, take an appropriate backup, then update through HACS. Restart Home Assistant if requested. After it reloads, check the connection and sync entities before relying on automatic management. Breaking changes and supported versions will be documented with each release.

## Removing

1. Pause sync in the integration settings.
2. Review the current UniFi filters. If you no longer want them, change them deliberately in UniFi after management has stopped.
3. Remove the integration entry from **Settings → Devices & services**.
4. Remove its downloaded files through HACS and restart if prompted.

**Removal does not restore old UniFi filter settings or delete provider credentials/accounts.** Revoke an API key or pfSense account separately if it is no longer needed. Old backups may still contain saved credentials.
