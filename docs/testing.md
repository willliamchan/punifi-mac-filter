# Testing the first beta

[← Back to the overview](../README.md)

## Scope of 0.1.0b2

This build implements native setup/reconfigure/reauth/options flows, explicit interface-to-SSID mappings, source/observed/sync sensors, a per-target manual button and a guarded one-way reconciliation loop. Defaults are observation-only. There is no pfSense mutation API in the integration.

### Verified during development

- **Home Assistant 2026.9.3 / Python 3.14:** the native test harness exercises actual config-entry setup, flows, entity registration, services, reload, unload and authentication recovery with synthetic provider fixtures.
- **104 focused tests:** explicit menu captions (including missing translations), selected-only source sensors, upgrade cleanup, shared-source retirement and complete all-interface policy union; source-age budgets across collection/exact-target reads; save-time ownership/baseline races and cancellation; policy normalization and all-interface union; empty/invalid data; mapping/identity changes; no-op/idempotence; drift and readback; source changes/failure during apply; bounded retry; pause/unload during an active write; duplicate ownership; credential retention/redaction; TLS/redirect/status handling; exact fixed pfSense XML-RPC payload; narrow UniFi filter-only mutation; and a synthetic 141-address allowlist.
- **Live read-only candidate clients:** TLS-verified collection and identity checks on pfSense 2.9.0-RELEASE and UniFi OS Network 10.6.106, including interface/site/network/WLAN discovery and exact-target reads. No live filters were changed by this integration during development.
- **HA hassfest:** the complete applicable validator set from HA 2026.9.3 passed for the integration, including manifest, flow and translations.
- **Ruff and repository checks:** source lint, formatting, documentation links, metadata and common accidental-secret patterns checked.

CI results, when available, are visible in the repository's [Actions tab](https://github.com/willliamchan/punifi-mac-filter/actions). A local pass is not a claim that a remote CI run completed.

### Still requires controlled user testing

- A complete HACS installation in your HA instance and visual acceptance of the native forms.
- Actual filter writes through this integration against a selected test SSID, followed by controller readback and client/AP observations.
- AP provisioning/enforcement and sustained operation across real outages/restarts.
- Provider versions beyond the read-tested versions, minimum UniFi write permissions, maximum MAC-list size, private-CA installations and encrypted-backup/Recorder retention behavior in your environment.

Synthetic provider responses test behavior without changing a network. They are not evidence that a particular live key can write, or that an AP has enforced the result. Empty restricted lists remain blocked rather than experimenting on your Wi-Fi.

## Suggested first test

1. Install the beta using the [HACS guide](installation.md), then add the integration.
2. Enter your connection details and select the correct UniFi site.
3. Add **one** source/SSID pair, check **Confirm pair**, and save with global sync **off** and the pair disabled.
4. Confirm that the source sensor shows the correct policy/own-interface MAC list and the observed sensor matches UniFi. Out of sync is expected if they currently differ; observation-only must not alter the filter.
5. Try reconfigure without changing a secret: leave it blank and confirm the connection still works. Verify the mapping stays in place.
6. Only when ready for a network change: preserve the test SSID's current filter settings, keep a separate management connection, enable that pair and global sync, and watch the result. **Enabling can write immediately**; the button is not an extra approval step.
7. Use **Sync now** to request fresh reconciliation. Once matched it should perform no further write. Synced confirms the controller configuration, not client connectivity.
8. Pause sync and confirm subsequent source changes are not applied. Restore the test SSID's earlier filter deliberately if needed; pause/uninstall does not undo it.

Do not use a management-critical SSID for the first write test. Report your versions, workflow and redacted result in an issue; never attach credentials or raw provider payloads.

## Reproduce the local tests

With Python 3.14 available, from the repository root:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests
.venv/bin/python -m ruff check custom_components tests
.venv/bin/python -m ruff format --check custom_components tests
.venv/bin/python scripts/check_repository.py
```

Use only synthetic fixtures in tests. Live credentials, HA storage, provider snapshots and internal operational records do not belong in this repository.
