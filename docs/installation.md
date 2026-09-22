# Installation

[← Back to the overview](../README.md)

> **Not available yet.** This repository currently contains documentation only. The steps below are the intended installation path once a tested integration release is published. Adding the repository to HACS now will not install pUniFi.

## What you will need

- A Home Assistant installation that supports custom integrations.
- [HACS](https://www.hacs.xyz/docs/use/) installed and working. HACS is a separate community project; install it using its own guide first.
- A pfSense firewall and a UniFi Network controller that Home Assistant can reach directly over HTTPS.
- Credentials for both systems. See [connection setup](setup.md).
- At least one UniFi Wi-Fi SSID to map to a pfSense DHCP interface.
- A Home Assistant backup before installing a new custom integration.

Home Assistant, pfSense and UniFi version requirements will be listed here after release testing. Home Assistant Cloud is not a substitute for network access from HA to your firewall/controller.

## Install through HACS — after release

1. Open **HACS** in Home Assistant.
2. Open its menu and choose **Custom repositories**. Menu placement may vary by HACS version.
3. Paste this repository URL:

   ```text
   https://github.com/willliamchan/punifi-mac-filter
   ```

4. Choose **Integration** as the repository type and add it.
5. Find **pUniFi MAC Filter** in HACS and download the published version.
6. Restart Home Assistant if prompted, so it can load the integration.
7. Go to **Settings → Devices & services → Add integration**.
8. Search for **pUniFi MAC Filter** and follow the [setup guide](setup.md).

Installing files through HACS and adding the integration in Home Assistant are separate steps. HACS handles the files; the HA setup popup connects your devices and configures mappings.

## Updating — after release

Read the release notes, take an appropriate backup, then update through HACS. Restart Home Assistant if requested. After it reloads, check the connection and sync entities before relying on automatic management. Breaking changes and supported versions will be documented with each release.

## Removing — after release

1. Pause sync in the integration settings.
2. Review the current UniFi filters. If you no longer want them, change them deliberately in UniFi after management has stopped.
3. Remove the integration entry from **Settings → Devices & services**.
4. Remove its downloaded files through HACS and restart if prompted.

**Removal does not restore old UniFi filter settings or delete provider credentials/accounts.** Revoke an API key or pfSense account separately if it is no longer needed. Old backups may still contain saved credentials.
