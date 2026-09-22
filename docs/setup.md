# Connect your systems and add mappings

[← Back to the overview](../README.md)

> **Planned workflow, not a released feature.** The integration is not installable yet. This guide describes the intended setup; final screen labels and screenshots will follow implementation testing.

## 1. Connect pfSense

In the pUniFi setup popup, enter:

| Field | What to enter |
|---|---|
| Host | The firewall's hostname or IP address, without `https://` or a path |
| Port | Its HTTPS port; normally `443`, or your configured custom port |
| Username | Your chosen pfSense integration account |
| Password | That account's password |

For example, use `firewall.example.com` in Host and `443` in Port, not `https://firewall.example.com:443/xmlrpc.php` in Host.

pUniFi will use the built-in XML-RPC endpoint. No SSH access or pfSense REST API package is planned.

### pfSense permissions

A dedicated account is preferable to reusing a personal administrator login. In pfSense, user management is under **System → User Manager**. The required privilege for this XML-RPC route is **System - HA node sync** (`system-xmlrpc-ha-sync`). Account creation/privilege controls vary with pfSense version; check your version's documentation before changing permissions.

**Important:** this privilege is not server-enforced read-only access. It grants broad effective XML-RPC authority. pUniFi will run only its fixed read-only collector, but you must protect the account as a powerful credential. Do not remove privileges from an existing account used by other integrations merely to configure this one.

Reference: the existing [hass-pfsense integration's XML-RPC documentation](https://github.com/travisghansen/hass-pfsense) explains this privilege and its implications. pUniFi is a separate integration, not an extension of that project.

## 2. Connect UniFi

Enter:

| Field | What to enter |
|---|---|
| Host | Your UniFi console/controller hostname or IP, without scheme or path |
| Port | Its HTTPS port; use the actual port for your installation |
| API key | A UniFi API key able to read the selected site and manage its WLAN MAC filters |

Then select the intended site from the discovered sites. Do not paste a username/password into the API key field or use a cloud portal URL in place of the local controller address.

### Obtaining a UniFi API key

Use the API-key management screen provided by your UniFi installation. Its location and permission model depend on the console and software version; a version-specific, tested menu path will be added before release. Do not guess privileges or assume that a key for the official Integration API can also update WLAN filters through the legacy API.

Use a dedicated, appropriately scoped identity where supported. The minimum working role is still being verified; this project does not claim that console Owner access is required.

Setup will validate readable access without making a test change to UniFi. If read checks cannot establish write permission, the UI will say so. A successful connection check is not proof that filter updates are permitted.

### HTTPS for both connections

Certificates must be valid, trusted by Home Assistant and match the entered host. If the certificate is issued to a hostname, use that hostname rather than an IP unless the IP is also covered. A self-signed or private-CA certificate needs a correctly established trust path; there will be no “ignore certificate errors” switch or HTTP fallback.

## 3. Add an interface-to-SSID pair

Choose **Add pair**, then select:

1. The **pfSense DHCP interface** supplying the policy and static MAC mappings.
2. The **UniFi Wi-Fi target** receiving the MAC filter.

The target label will include its SSID, linked network, VLAN where known, and site. Review these details even when the names look familiar.

Add the pair, then repeat for other targets. A single pfSense interface can feed several SSIDs, but each SSID can have only one source. Selecting one SSID does not automatically manage other SSIDs sharing its network.

A matching explicit VLAN may suggest a source interface. Suggestions are only a convenience: names do not have to match, different VLANs are allowed when deliberately selected, and ambiguous/missing VLAN information will not create a mapping. Unselected targets remain **Not managed**.

### Example

| pfSense source | UniFi target | Effect |
|---|---|---|
| IoT interface | Smart Home SSID | That SSID follows the IoT interface's policy |
| Guest interface | Visitors SSID | That SSID follows the Guest interface's policy |
| No mapping | Main Wi-Fi SSID | pUniFi leaves it untouched |

These are illustrative names, not required interface names or automatic mappings.

## 4. Preview before enabling

Review each source policy, the resulting MAC count and the filter currently observed in UniFi.

Initial setup defaults to **observation-only**. To allow writes, explicitly enable sync globally and for each pair you want managed. Both controls must be enabled.

Before enabling a restricted allowlist:

- Make sure required clients have appropriate static mappings in pfSense.
- Check whether clients use a private/randomized Wi-Fi MAC; map the address they actually use on that SSID.
- Keep a separate management connection available in case a client loses access.
- Remember that an empty restricted list will be blocked, not converted to unrestricted access.

After saving, the integration will refresh both systems before applying changes. See [daily use and sync status](usage.md).
