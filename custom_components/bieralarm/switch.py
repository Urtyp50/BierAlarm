"""One switch per beer ('Zipfer Urtyp'): on = notify me when it is on offer."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from . import BierAlarmConfigEntry
from .coordinator import BierAlarmCoordinator
from .entity import BierAlarmEntity
from .models import matches_brand


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    switches = [BrandSwitch(coordinator, beer) for beer in coordinator.brand_names]
    # Drop switches of beers that are no longer offered (e.g. the old per-brand ones).
    registry = er.async_get(hass)
    wanted = {s.unique_id for s in switches}
    prefix = f"{entry.entry_id}_brand_"
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.domain == "switch" and reg.unique_id.startswith(prefix) and reg.unique_id not in wanted:
            registry.async_remove(reg.entity_id)
    async_add_entities(switches)


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
    def entity_picture(self) -> str | None:
        return self.coordinator.beer_image(self._brand)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        brand, _, sort = self._brand.partition(" ")
        return {
            "beer": self._brand,
            "brand": brand,
            "sort": sort or "alle Sorten",
            "deals": sum(1 for d in data.deals if matches_brand(d, [self._brand])) if data else 0,
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
