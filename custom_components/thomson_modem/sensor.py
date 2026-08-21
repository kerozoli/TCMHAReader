"""Sensors for the Thomson Cable Modem integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfFrequency,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ThomsonModemCoordinator
from .parser import DownstreamChannel, ModemDiagnostics, UpstreamChannel

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ThomsonSensorDescription(SensorEntityDescription):
    """Class describing Thomson modem sensor entities."""

    value_fn: callable


def _find_downstream_channel(
    diagnostics: ModemDiagnostics, channel_id: str
) -> DownstreamChannel | None:
    """Return the downstream channel with the given ID, if present."""
    return next(
        (ch for ch in diagnostics.downstream if ch.channel_id == channel_id), None
    )


def _find_upstream_channel(
    diagnostics: ModemDiagnostics, channel_id: str
) -> UpstreamChannel | None:
    """Return the upstream channel with the given ID, if present."""
    return next(
        (ch for ch in diagnostics.upstream if ch.channel_id == channel_id), None
    )


def _ds_value_fn(channel_id: str, attr: str) -> callable:
    """Return a value function that reads an attribute from a downstream channel."""

    def value_fn(diagnostics: ModemDiagnostics) -> Any:
        channel = _find_downstream_channel(diagnostics, channel_id)
        if channel is None:
            return None
        return getattr(channel, attr)

    return value_fn


def _us_value_fn(channel_id: str, attr: str) -> callable:
    """Return a value function that reads an attribute from an upstream channel."""

    def value_fn(diagnostics: ModemDiagnostics) -> Any:
        channel = _find_upstream_channel(diagnostics, channel_id)
        if channel is None:
            return None
        return getattr(channel, attr)

    return value_fn


def _build_sensors(coordinator: ThomsonModemCoordinator) -> list[ThomsonModemSensor]:
    """Build the full list of sensors from parsed diagnostics."""
    diagnostics = coordinator.data
    if diagnostics is None:
        return []

    entities: list[ThomsonModemSensor] = []

    # Aggregates across downstream channels.
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

    # Downstream channel sensors.
    for idx, channel in enumerate(diagnostics.downstream):
        channel_id = channel.channel_id or str(idx)
        suffix = f"ds_{channel_id}"
        entities.extend(_downstream_channel_sensors(coordinator, channel, suffix))

    # Upstream channel sensors.
    for idx, channel in enumerate(diagnostics.upstream):
        channel_id = channel.channel_id or str(idx)
        suffix = f"us_{channel_id}"
        entities.extend(_upstream_channel_sensors(coordinator, channel, suffix))

    return entities


def _downstream_channel_sensors(
    coordinator: ThomsonModemCoordinator,
    channel: DownstreamChannel,
    suffix: str,
) -> list[ThomsonModemSensor]:
    """Create sensors for one downstream channel."""
    channel_id = channel.channel_id or suffix
    sensors: list[ThomsonModemSensor] = []

    if channel.power is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_power",
                    name=f"Downstream {channel_id} power",
                    native_unit_of_measurement="dBmV",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_ds_value_fn(channel_id, "power"),
                ),
            )
        )
    if channel.snr is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_snr",
                    name=f"Downstream {channel_id} SNR",
                    native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_ds_value_fn(channel_id, "snr"),
                ),
            )
        )
    if channel.ber is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_ber",
                    name=f"Downstream {channel_id} BER",
                    native_unit_of_measurement="%",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_ds_value_fn(channel_id, "ber"),
                ),
            )
        )
    if channel.frequency is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_frequency",
                    name=f"Downstream {channel_id} frequency",
                    native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
                    device_class=SensorDeviceClass.FREQUENCY,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_ds_value_fn(channel_id, "frequency"),
                ),
            )
        )
    if channel.corrected is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_corrected",
                    name=f"Downstream {channel_id} corrected",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    value_fn=_ds_value_fn(channel_id, "corrected"),
                ),
            )
        )
    if channel.uncorrected is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_uncorrected",
                    name=f"Downstream {channel_id} uncorrected",
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    value_fn=_ds_value_fn(channel_id, "uncorrected"),
                ),
            )
        )
    if channel.modulation is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_modulation",
                    name=f"Downstream {channel_id} modulation",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    value_fn=_ds_value_fn(channel_id, "modulation"),
                ),
            )
        )
    if channel.lock_status is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_lock_status",
                    name=f"Downstream {channel_id} lock status",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    value_fn=_ds_value_fn(channel_id, "lock_status"),
                ),
            )
        )

    return sensors


def _upstream_channel_sensors(
    coordinator: ThomsonModemCoordinator,
    channel: UpstreamChannel,
    suffix: str,
) -> list[ThomsonModemSensor]:
    """Create sensors for one upstream channel."""
    channel_id = channel.channel_id or suffix
    sensors: list[ThomsonModemSensor] = []

    if channel.power is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_power",
                    name=f"Upstream {channel_id} power",
                    native_unit_of_measurement="dBmV",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_us_value_fn(channel_id, "power"),
                ),
            )
        )
    if channel.frequency is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_frequency",
                    name=f"Upstream {channel_id} frequency",
                    native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
                    device_class=SensorDeviceClass.FREQUENCY,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_us_value_fn(channel_id, "frequency"),
                ),
            )
        )
    if channel.modulation is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_modulation",
                    name=f"Upstream {channel_id} modulation",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    value_fn=_us_value_fn(channel_id, "modulation"),
                ),
            )
        )
    if channel.lock_status is not None:
        sensors.append(
            ThomsonModemSensor(
                coordinator,
                ThomsonSensorDescription(
                    key=f"{suffix}_lock_status",
                    name=f"Upstream {channel_id} lock status",
                    entity_category=EntityCategory.DIAGNOSTIC,
                    value_fn=_us_value_fn(channel_id, "lock_status"),
                ),
            )
        )

    return sensors


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
