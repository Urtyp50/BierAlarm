"""Free-text filter for dashboards, e.g. 'Urtyp' or 'Zipfer'."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import BierAlarmConfigEntry
from .entity import BierAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BierAlarmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FilterText(entry.runtime_data, "filter")])


class FilterText(BierAlarmEntity, TextEntity, RestoreEntity):
    _attr_icon = "mdi:magnify"
    _attr_translation_key = "filter"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 60
    _attr_native_value = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            self._attr_native_value = last.state

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value.strip()
        self.async_write_ha_state()
