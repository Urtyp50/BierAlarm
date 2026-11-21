"""Radius around home as an editable number (km, 0 = all stores)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BierAlarmConfigEntry
from .const import CONF_MAX_PRICE_PER_LITER, CONF_RADIUS_KM
from .entity import BierAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RadiusNumber(coordinator, "radius"), CratePriceLimit(coordinator, "crate_limit")])


class RadiusNumber(BierAlarmEntity, NumberEntity):
    """Stored in the options, so the settings dialog shows the same value."""

    _attr_icon = "mdi:map-marker-radius"
    _attr_translation_key = "radius"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self.coordinator.radius_km or 0

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {"start_address": data.home_address if data else None}

    async def async_set_native_value(self, value: float) -> None:
        entry = self.coordinator.config_entry
        # Changing the radius reloads the entry: stores in range are looked up again.
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_RADIUS_KM: int(value)}
        )


class CratePriceLimit(BierAlarmEntity, NumberEntity):
    """Bell/alarm when a 20er-Kiste costs at most this much (stored as €/l, ×10)."""

    _attr_icon = "mdi:bell-ring-outline"
    _attr_translation_key = "crate_limit"
    _attr_native_min_value = 0
    _attr_native_max_value = 50
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "€"
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        per_liter = self.coordinator.max_price_per_liter
        return round(per_liter * 10, 2) if per_liter else 0

    async def async_set_native_value(self, value: float) -> None:
        entry = self.coordinator.config_entry
        # 0 = no price alarm, only favourite beers. No reload: matches are re-evaluated.
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_MAX_PRICE_PER_LITER: round(value / 10, 3)}
        )
        self.async_write_ha_state()
