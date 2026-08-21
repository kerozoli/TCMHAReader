"""Sensors for the Thomson Cable Modem integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ThomsonModemCoordinator
from .parser import ModemDiagnostics

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ThomsonSensorDescription(SensorEntityDescription):
    """Class describing Thomson modem sensor entities."""

    value_fn: callable


def _build_sensors(coordinator: ThomsonModemCoordinator) -> list[ThomsonModemSensor]:
    """Build only aggregate sensors useful for monitoring modem health."""
    diagnostics = coordinator.data
    if diagnostics is None:
        return []

    entities: list[ThomsonModemSensor] = []

    # Downstream aggregates.
    entities.append(
        ThomsonModemSensor(
            coordinator,
            ThomsonSensorDescription(
                key="downstream_channel_count",
                name="Downstream channel count",
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d: len(d.downstream),
            ),
        )
    )
    entities.append(
        ThomsonModemSensor(
            coordinator,
            ThomsonSensorDescription(
                key="downstream_locked_count",
                name="Downstream locked channels",
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d: sum(
                    1 for ch in d.downstream if _is_locked(ch.lock_status)
                ),
            ),
        )
    )
    if any(ch.corrected is not None for ch in diagnostics.downstream):
        entities.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key="downstream_total_corrected",
                    name="Downstream corrected codewords",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    value_fn=lambda d: sum(
                        (ch.corrected or 0)
                        for ch in d.downstream
                        if ch.corrected is not None
                    ),
                ),
            )
        )
    if any(ch.uncorrected is not None for ch in diagnostics.downstream):
        entities.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key="downstream_total_uncorrected",
                    name="Downstream uncorrected codewords",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    value_fn=lambda d: sum(
                        (ch.uncorrected or 0)
                        for ch in d.downstream
                        if ch.uncorrected is not None
                    ),
                ),
            )
        )
    if any(ch.snr is not None for ch in diagnostics.downstream):
        entities.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key="downstream_average_snr",
                    name="Downstream average SNR",
                    native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _average(
                        [ch.snr for ch in d.downstream if ch.snr is not None]
                    ),
                ),
            )
        )
    if any(ch.power is not None for ch in diagnostics.downstream):
        entities.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key="downstream_average_power",
                    name="Downstream average power",
                    native_unit_of_measurement="dBmV",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _average(
                        [ch.power for ch in d.downstream if ch.power is not None]
                    ),
                ),
            )
        )
    if any(ch.ber is not None for ch in diagnostics.downstream):
        entities.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key="downstream_average_ber",
                    name="Downstream average BER",
                    native_unit_of_measurement="%",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _average(
                        [ch.ber for ch in d.downstream if ch.ber is not None]
                    ),
                ),
            )
        )

    # Upstream aggregates.
    entities.append(
        ThomsonModemSensor(
            coordinator,
            ThomsonSensorDescription(
                key="upstream_channel_count",
                name="Upstream channel count",
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d: len(d.upstream),
            ),
        )
    )
    entities.append(
        ThomsonModemSensor(
            coordinator,
            ThomsonSensorDescription(
                key="upstream_locked_count",
                name="Upstream locked channels",
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d: sum(
                    1 for ch in d.upstream if _is_locked(ch.lock_status)
                ),
            ),
        )
    )
    if any(ch.power is not None for ch in diagnostics.upstream):
        entities.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key="upstream_average_power",
                    name="Upstream average power",
                    native_unit_of_measurement="dBmV",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d: _average(
                        [ch.power for ch in d.upstream if ch.power is not None]
                    ),
                ),
            )
        )

    return entities


def _is_locked(status: str | None) -> bool:
    """Interpret a lock status string as a boolean."""
    if not status:
        return False
    return "locked" in status.lower() or "yes" in status.lower() or "true" in status.lower()


def _average(values: list[float]) -> float | None:
    """Return the average of a list, or None if empty."""
    if not values:
        return None
    return sum(values) / len(values)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Thomson modem sensors from a config entry."""
    coordinator: ThomsonModemCoordinator = entry.runtime_data

    if not coordinator.data:
        _LOGGER.warning("No diagnostic data available yet; sensors will be created on next refresh")
        return

    async_add_entities(_build_sensors(coordinator), update_before_add=False)


class ThomsonModemSensor(CoordinatorEntity[ThomsonModemCoordinator], SensorEntity):
    """Representation of a Thomson cable modem sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    entity_description: ThomsonSensorDescription

    def __init__(
        self,
        coordinator: ThomsonModemCoordinator,
        description: ThomsonSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_{self._entry_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the modem."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Thomson Cable Modem",
            manufacturer="Thomson",
            model="Cable Modem",
        )

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
