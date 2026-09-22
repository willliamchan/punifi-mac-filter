"""Counts/status only: no entry data, identifiers, MACs or raw payloads."""


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = getattr(entry, "runtime_data", None)
    data = runtime.data if runtime and runtime.data else {}
    return {
        "entry_version": entry.version,
        "available": bool(runtime and runtime.last_update_success),
        "sync_enabled": bool(entry.options.get("sync_enabled", False)),
        "mapping_count": len(entry.options.get("mappings", [])),
        "source_count": len((data.get("source") or {}).get("interfaces", {})),
        "target_count": len((data.get("target") or {}).get("wlans", {})),
        "statuses": [s["state"] for s in data.get("sync", {}).values()],
    }
