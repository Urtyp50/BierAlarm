"""Store filter for dashboards."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import BierAlarmConfigEntry
from .const import FILTER_ALL, STORE_NAMES
from .coordinator import BierAlarmCoordinator
from .entity import BierAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([StoreFilter(entry.runtime_data)])


class StoreFilter(BierAlarmEntity, SelectEntity, RestoreEntity):
    _attr_icon = "mdi:store-search"
    _attr_translation_key = "store_filter"

    def __init__(self, coordinator: BierAlarmCoordinator) -> None:
        super().__init__(coordinator, "store_filter")
        self._attr_options = [FILTER_ALL] + [
            STORE_NAMES[s] for s in coordinator.stores if s in STORE_NAMES
        ]
        self._attr_current_option = FILTER_ALL

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in self.options:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()
