"""Sensors: number of beer deals and the cheapest liter price."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BierAlarmConfigEntry
from .const import DOMAIN, STORE_NAMES
from .coordinator import BierAlarmCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([DealCountSensor(coordinator), BestPriceSensor(coordinator)])


class _Base(CoordinatorEntity[BierAlarmCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: BierAlarmCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="BierAlarm",
            manufacturer="BierAlarm",
            entry_type=DeviceEntryType.SERVICE,
        )


class DealCountSensor(_Base):
    _attr_icon = "mdi:beer"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Aktionen"

    def __init__(self, coordinator: BierAlarmCoordinator) -> None:
        super().__init__(coordinator, "deals")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.deals)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        matches = set(data.matches)
        return {
            "matches": len(matches),
            "errors": data.errors,
            "deals": [
                {
                    "store": STORE_NAMES.get(d.store, d.store),
                    "title": d.title,
                    "package": d.package,
                    "price": d.price,
                    "price_per_liter": d.price_per_liter,
                    "valid_to": d.valid_to,
                    "match": d.id in matches,
                }
                for d in data.deals[:15]
            ],
        }


class BestPriceSensor(_Base):
    _attr_icon = "mdi:cash-check"
    _attr_native_unit_of_measurement = "€/l"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: BierAlarmCoordinator) -> None:
        super().__init__(coordinator, "best_price")

    def _best(self):
        return next((d for d in self.coordinator.data.deals if d.price_per_liter), None)

    @property
    def native_value(self) -> float | None:
        best = self._best()
        return best.price_per_liter if best else None

    @property
    def extra_state_attributes(self) -> dict:
        best = self._best()
        if not best:
            return {}
        return {
            "store": STORE_NAMES.get(best.store, best.store),
            "title": best.title,
            "package": best.package,
            "price": best.price,
            "condition": best.condition,
            "valid_to": best.valid_to,
            "url": best.url,
        }
