"""Shared base for all BierAlarm entities (one service device)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BierAlarmCoordinator


class BierAlarmEntity(CoordinatorEntity[BierAlarmCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: BierAlarmCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="BierAlarm",
            manufacturer="BierAlarm",
            entry_type=DeviceEntryType.SERVICE,
        )
