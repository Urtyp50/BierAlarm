"""Sensors: number of beer deals and the cheapest liter price."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BierAlarmConfigEntry
from .const import STORE_NAMES
from .coordinator import BierAlarmCoordinator
from .entity import BierAlarmEntity

MAX_DEALS_ATTR = 60


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [DealCountSensor(coordinator), BestPriceSensor(coordinator), BestCratePriceSensor(coordinator)]
    )


class _Base(BierAlarmEntity, SensorEntity):
    def __init__(self, coordinator: BierAlarmCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key


class DealCountSensor(_Base):
    _attr_icon = "mdi:beer"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Aktionen"
    # The full list is for dashboards only, keep it out of the database.
    _unrecorded_attributes = frozenset({"deals", "branches", "start_address"})

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
            "radius_km": self.coordinator.radius_km,
            "start_address": data.home_address,
            "nearby": {
                STORE_NAMES.get(s, s): branches[0] for s, branches in (data.nearby or {}).items() if branches
            },
            "out_of_range": [STORE_NAMES.get(s, s) for s in data.out_of_range],
            # every branch within the radius, for the map in the card
            "branches": [
                {**b, "store": STORE_NAMES.get(s, s)}
                for s, branches in (data.nearby or {}).items()
                for b in branches[:8]
            ],
            "deals": [
                {
                    "store": STORE_NAMES.get(d.store, d.store),
                    "brand": d.brand,
                    "title": d.title,
                    "package": d.package,
                    "price": d.price,
                    "price_per_liter": d.price_per_liter,
                    "price_per_crate": d.price_per_crate,
                    "alcohol": (info := d.as_dict())["alcohol"],
                    "alcohol_typical": info["alcohol_typical"],
                    "condition": d.condition,
                    "discount_percent": d.discount_percent,
                    "valid_to": d.valid_to,
                    "distance_km": self.coordinator.distance(d.store),
                    "match": d.id in matches,
                    "favorite": self.coordinator.is_favorite(d),
                }
                for d in sorted(
                    data.deals, key=lambda d: (d.price_per_crate is None, d.price_per_crate or 0)
                )[:MAX_DEALS_ATTR]
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
            "price_per_crate": best.price_per_crate,
            "condition": best.condition,
            "valid_to": best.valid_to,
            "url": best.url,
        }


class BestCratePriceSensor(BestPriceSensor):
    """Cheapest deal as price for a 20er-Kiste à 0,5 l (10 liters)."""

    _attr_icon = "mdi:beer-outline"
    _attr_native_unit_of_measurement = "€"

    def __init__(self, coordinator: BierAlarmCoordinator) -> None:
        _Base.__init__(self, coordinator, "best_crate_price")

    @property
    def native_value(self) -> float | None:
        best = self._best()
        return best.price_per_crate if best else None
