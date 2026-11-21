"""One switch per beer brand: on = notify me when this brand is on offer."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from . import BierAlarmConfigEntry
from .coordinator import BierAlarmCoordinator
from .entity import BierAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(BrandSwitch(coordinator, brand) for brand in coordinator.brand_names)


class BrandSwitch(BierAlarmEntity, SwitchEntity):
    """Stored in the favourite brands option, so options flow and switch stay in sync."""

    _attr_icon = "mdi:bell-ring-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BierAlarmCoordinator, brand: str) -> None:
        super().__init__(coordinator, f"brand_{slugify(brand)}")
        self._brand = brand
        self._attr_translation_key = "brand"
        self._attr_translation_placeholders = {"brand": brand}

    @property
    def is_on(self) -> bool:
        return any(b.lower() == self._brand.lower() for b in self.coordinator.favorite_brands)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        brand = self._brand.lower()
        return {
            "brand": self._brand,
            "deals": sum(1 for d in data.deals if brand in f"{d.brand or ''} {d.name}".lower())
            if data
            else 0,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options=self.coordinator.favorite_options(self._brand, on),
        )
        self.async_write_ha_state()
