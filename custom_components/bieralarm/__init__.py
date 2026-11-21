"""BierAlarm: Bieraktionen aus österreichischen Flugblättern in Home Assistant."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_FAVORITE_BRANDS,
    CONF_MAX_PRICE_PER_LITER,
    CONF_STORES,
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_STATIC_URL,
    PANEL_URL_PATH,
    SERVICE_REFRESH,
    STORE_NAMES,
)
from .coordinator import BierAlarmCoordinator

PLATFORMS = [Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TEXT]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type BierAlarmConfigEntry = ConfigEntry[BierAlarmCoordinator]

FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    websocket_api.async_register_command(hass, ws_deals)

    async def refresh(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            if call.data.get("reanalyse"):
                await entry.runtime_data.async_clear_leaflet_cache()
            await entry.runtime_data.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        refresh,
        schema=vol.Schema({vol.Optional("reanalyse", default=False): cv.boolean}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BierAlarmConfigEntry) -> bool:
    coordinator = BierAlarmCoordinator(hass, entry)
    hass.data[f"{DOMAIN}_options_{entry.entry_id}"] = _reload_relevant(coordinator)
    await coordinator.async_load_cache()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await _async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BierAlarmConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.pop(f"{DOMAIN}_options_{entry.entry_id}", None)
    if unloaded and not [
        e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        hass.data.pop(f"{DOMAIN}_panel", None)
    return unloaded


def _reload_relevant(coordinator: BierAlarmCoordinator) -> tuple:
    """Everything except the favourite brands needs a reload (new fetch)."""
    opts = {k: v for k, v in coordinator.opts.items() if k != CONF_FAVORITE_BRANDS}
    return (sorted(opts.items(), key=str), coordinator.brand_names)


async def _async_reload(hass: HomeAssistant, entry: BierAlarmConfigEntry) -> None:
    coordinator = entry.runtime_data
    key = f"{DOMAIN}_options_{entry.entry_id}"
    if hass.data.get(key) == _reload_relevant(coordinator):
        # Only a brand switch was flipped: no need to download everything again.
        await coordinator.async_rematch()
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_panel(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_panel"):
        return
    if not hass.data.get(f"{DOMAIN}_static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[f"{DOMAIN}_static"] = True
    stat = await hass.async_add_executor_job((FRONTEND_DIR / "bieralarm-panel.js").stat)
    version = stat.st_mtime_ns
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="BierAlarm",
        sidebar_icon="mdi:beer",
        module_url=f"{PANEL_STATIC_URL}/bieralarm-panel.js?v={version}",
        require_admin=False,
        config={},
    )
    hass.data[f"{DOMAIN}_panel"] = True


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/deals"})
@callback
def ws_deals(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    """Everything the sidebar panel needs in one call."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_result(msg["id"], {"configured": False})
        return
    coordinator: BierAlarmCoordinator = entries[0].runtime_data
    data = coordinator.data
    matches = set(data.matches) if data else set()
    connection.send_result(
        msg["id"],
        {
            "configured": True,
            "updated": data.updated.isoformat() if data and data.updated else None,
            "errors": data.errors if data else {},
            "stores": {s: STORE_NAMES.get(s, s) for s in coordinator.opts.get(CONF_STORES, [])},
            "store_names": {**STORE_NAMES, "custom": "Eigenes Flugblatt"},
            "favorite_brands": coordinator.opts.get(CONF_FAVORITE_BRANDS) or "",
            "max_price_per_liter": coordinator.opts.get(CONF_MAX_PRICE_PER_LITER),
            "radius_km": coordinator.radius_km,
            "nearby": (data.nearby if data else None) or {},
            "out_of_range": data.out_of_range if data else [],
            "deals": [
                {**d.as_dict(), "match": d.id in matches, "distance_km": coordinator.distance(d.store)}
                for d in (data.deals if data else [])
            ],
        },
    )
