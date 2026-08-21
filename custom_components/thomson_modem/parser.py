"""Parse Thomson cable modem Diagnostics.asp pages."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag

_LOGGER = logging.getLogger(__name__)

# Normalized header aliases we look for in diagnostics tables.
DOWNSTREAM_HINTS = {"downstream", "ds", "down", "forward path", "forward"}
UPSTREAM_HINTS = {"upstream", "us", "up", "return path", "return"}

CHANNEL_ID_ALIASES = {"channel", "channel id", "chan id", "ch id", "id"}
FREQUENCY_ALIASES = {"frequency", "freq", "center frequency"}
POWER_ALIASES = {"power", "level", "rx power", "tx power", "signal power"}
SNR_ALIASES = {"snr", "mer", "snr/mer", "signal to noise", "noise ratio"}
BER_ALIASES = {"ber", "bit error rate"}
MODULATION_ALIASES = {"modulation", "mod"}
LOCK_STATUS_ALIASES = {"lock status", "locking", "status"}
CORRECTED_ALIASES = {"corrected", "codewords correctable"}
UNCORRECTED_ALIASES = {"uncorrected", "codewords uncorrectable"}


@dataclass
class DownstreamChannel:
    """A single downstream channel reading."""

    channel_id: str | None = None
    frequency: float | None = None  # MHz
    power: float | None = None  # dBmV
    snr: float | None = None  # dB
    ber: float | None = None  # %
    modulation: str | None = None
    lock_status: str | None = None
    corrected: int | None = None
    uncorrected: int | None = None


@dataclass
class UpstreamChannel:
    """A single upstream channel reading."""

    channel_id: str | None = None
    frequency: float | None = None  # MHz
    power: float | None = None  # dBmV
    modulation: str | None = None
    lock_status: str | None = None


@dataclass
class ModemDiagnostics:
    """Aggregated diagnostics data."""

    downstream: list[DownstreamChannel] = field(default_factory=list)
    upstream: list[UpstreamChannel] = field(default_factory=list)
    status: dict[str, Any] = field(default_factory=dict)
    raw_tables: list[dict[str, Any]] = field(default_factory=list)


def _normalize(text: str | None) -> str:
    """Normalize a string for matching."""
    if text is None:
        return ""
    return re.sub(r"[^a-z0-9/]+", " ", text.lower().strip())


def _find_column(headers: list[str], aliases: set[str]) -> int | None:
    """Return the index of a header matching one of the aliases."""
    for idx, header in enumerate(headers):
        normalized = _normalize(header)
        if any(alias in normalized or normalized in alias for alias in aliases):
            return idx
    return None


def _to_float(value: str | None) -> float | None:
    """Extract a float from a string, ignoring units."""
    if not value:
        return None
    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", value.replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _to_int(value: str | None) -> int | None:
    """Extract an integer from a string."""
    float_value = _to_float(value)
    if float_value is None:
        return None
    return int(float_value)


def _is_header_row(cells: list[Tag], row_text: list[str]) -> bool:
    """Detect whether a row should be treated as table headers."""
    if not cells:
        return False

    # Explicit th cells.
    if any(cell.name == "th" for cell in cells):
        return True

    # All cells contain bold/strong text.
    if all(cell.find(["b", "strong"]) is not None for cell in cells):
        return True

    # First row and text matches known diagnostic headers.
    combined = " ".join(_normalize(t) for t in row_text if t)
    header_keywords = {
        "channel",
        "frequency",
        "power",
        "snr",
        "ber",
        "modulation",
        "lock",
        "corrected",
        "uncorrected",
    }
    matches = [kw for kw in header_keywords if kw in combined]
    return len(matches) >= 2


def _is_plausible_data_table(headers: list[str], rows: list[list[str]]) -> bool:
    """Reject layout tables and other non-data tables."""
    if not headers or not rows:
        return False

    # Real diagnostic tables have a handful of columns.
    if not (2 <= len(headers) <= 12):
        return False

    # Header cells should be reasonably short labels.
    if any(len(h) > 80 for h in headers):
        return False

    # Data rows should match the header column count.
    header_count = len(headers)
    matching_rows = sum(1 for row in rows if len(row) == header_count)
    if matching_rows < len(rows) / 2:
        return False

    # Must contain at least one recognizable diagnostic column.
    known_cols = [
        _find_column(headers, CHANNEL_ID_ALIASES),
        _find_column(headers, FREQUENCY_ALIASES),
        _find_column(headers, POWER_ALIASES),
        _find_column(headers, MODULATION_ALIASES),
    ]
    return any(col is not None for col in known_cols)


def _classify_table(headers: list[str], preceding_text: str = "") -> str | None:
    """Classify a table as downstream, upstream, or unknown."""
    combined = " ".join(_normalize(h) for h in headers)
    context = _normalize(preceding_text)

    if any(hint in context for hint in DOWNSTREAM_HINTS):
        return "downstream"
    if any(hint in context for hint in UPSTREAM_HINTS):
        return "upstream"

    if any(hint in combined for hint in DOWNSTREAM_HINTS):
        return "downstream"
    if any(hint in combined for hint in UPSTREAM_HINTS):
        return "upstream"

    # Fallback: look for column mixes typical of each table type.
    has_power = _find_column(headers, POWER_ALIASES) is not None
    has_snr = _find_column(headers, SNR_ALIASES) is not None
    has_ber = _find_column(headers, BER_ALIASES) is not None
    has_freq = _find_column(headers, FREQUENCY_ALIASES) is not None
    if has_power and (has_snr or has_ber) and has_freq:
        return "downstream"
    if has_power and has_freq and has_snr is None and has_ber is None:
        return "upstream"
    return None


def _extract_table(table: Tag) -> dict[str, Any]:
    """Extract headers and rows from a BeautifulSoup table element."""
    rows: list[list[str]] = []
    headers: list[str] = []

    # Try to find headers in thead first.
    thead = table.find("thead")
    if thead:
        header_cells = thead.find_all(["th", "td"])
        headers = [cell.get_text(strip=True) for cell in header_cells]

    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue

        row_text = [cell.get_text(strip=True) for cell in cells]
        if not any(row_text):
            continue

        if not headers and _is_header_row(cells, row_text):
            headers = row_text
            continue

        rows.append(row_text)

    return {"headers": headers, "rows": rows}


def _preceding_text(table: Tag) -> str:
    """Collect nearby text before a table to help classify it."""
    texts: list[str] = []
    for prev in table.previous_siblings:
        if getattr(prev, "name", None) == "table":
            break
        if isinstance(prev, Tag):
            text = prev.get_text(strip=True)
        else:
            text = str(prev).strip()
        if text:
            texts.append(text)
            if len(texts) >= 3:
                break
    return " ".join(reversed(texts))


def _parse_downstream_table(headers: list[str], rows: list[list[str]]) -> list[DownstreamChannel]:
    """Parse rows into downstream channel objects."""
    channels = []

    col_channel = _find_column(headers, CHANNEL_ID_ALIASES)
    col_freq = _find_column(headers, FREQUENCY_ALIASES)
    col_power = _find_column(headers, POWER_ALIASES)
    col_snr = _find_column(headers, SNR_ALIASES)
    col_ber = _find_column(headers, BER_ALIASES)
    col_mod = _find_column(headers, MODULATION_ALIASES)
    col_lock = _find_column(headers, LOCK_STATUS_ALIASES)
    col_corrected = _find_column(headers, CORRECTED_ALIASES)
    col_uncorrected = _find_column(headers, UNCORRECTED_ALIASES)

    required_cols = [
        c
        for c in [col_channel, col_freq, col_power, col_snr, col_ber, col_mod, col_lock]
        if c is not None
    ]
    max_col = max(required_cols, default=-1) if required_cols else -1

    for row in rows:
        if len(row) < max_col + 1:
            continue

        def get(col: int | None) -> str | None:
            if col is None or col >= len(row):
                return None
            val = row[col]
            return val if val else None

        frequency = _to_float(get(col_freq))
        power = _to_float(get(col_power))

        # Skip placeholder rows where every numeric value is zero.
        if frequency == 0 and power == 0:
            continue

        channel = DownstreamChannel(
            channel_id=get(col_channel),
            frequency=frequency,
            power=power,
            snr=_to_float(get(col_snr)),
            ber=_to_float(get(col_ber)),
            modulation=get(col_mod),
            lock_status=get(col_lock),
            corrected=_to_int(get(col_corrected)),
            uncorrected=_to_int(get(col_uncorrected)),
        )
        channels.append(channel)

    return channels


def _parse_upstream_table(headers: list[str], rows: list[list[str]]) -> list[UpstreamChannel]:
    """Parse rows into upstream channel objects."""
    channels = []

    col_channel = _find_column(headers, CHANNEL_ID_ALIASES)
    col_freq = _find_column(headers, FREQUENCY_ALIASES)
    col_power = _find_column(headers, POWER_ALIASES)
    col_mod = _find_column(headers, MODULATION_ALIASES)
    col_lock = _find_column(headers, LOCK_STATUS_ALIASES)

    required_cols = [
        c for c in [col_channel, col_freq, col_power, col_mod, col_lock] if c is not None
    ]
    max_col = max(required_cols, default=-1) if required_cols else -1

    for row in rows:
        if len(row) < max_col + 1:
            continue

        def get(col: int | None) -> str | None:
            if col is None or col >= len(row):
                return None
            val = row[col]
            return val if val else None

        frequency = _to_float(get(col_freq))
        power = _to_float(get(col_power))

        # Skip placeholder / unconfigured channels.
        if frequency == 0 and power == 0:
            continue

        channel = UpstreamChannel(
            channel_id=get(col_channel),
            frequency=frequency,
            power=power,
            modulation=get(col_mod),
            lock_status=get(col_lock),
        )
        channels.append(channel)

    return channels


def _extract_status_items(soup: BeautifulSoup) -> dict[str, Any]:
    """Try to extract general status key/value pairs from the page."""
    status: dict[str, Any] = {}

    # Find rows that look like "Label: value" inside tables used for status.
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if ":" not in text:
            continue

        # Split only on the first colon.
        parts = text.split(":", 1)
        if len(parts) != 2:
            continue

        key = parts[0].strip()
        value = parts[1].strip()

        # Skip obvious table headers/rows and overly long blobs.
        normalized_key = _normalize(key)
        if normalized_key in {"channel", "frequency", "power", "snr", "ber", "modulation"}:
            continue
        if len(key) > 80 or len(value) > 200:
            continue

        # Avoid re-adding channel table content as status.
        unit_markers = ["MHz", "dBmV", "dB", "QAM", "%"]
        unit_count = sum(value.count(unit) for unit in unit_markers)
        if unit_count > 1:
            continue
        if unit_count == 1 and len(key) < 3:
            continue

        status[key] = value

    return status


def parse_diagnostics_page(html: str) -> ModemDiagnostics:
    """Parse the HTML of a Thomson Diagnostics.asp style page."""
    soup = BeautifulSoup(html, "html.parser")

    diagnostics = ModemDiagnostics()
    diagnostics.status = _extract_status_items(soup)

    for table in soup.find_all("table"):
        extracted = _extract_table(table)
        if not _is_plausible_data_table(extracted["headers"], extracted["rows"]):
            continue

        diagnostics.raw_tables.append(extracted)
        preceding = _preceding_text(table)
        table_type = _classify_table(extracted["headers"], preceding)

        if table_type == "downstream":
            diagnostics.downstream.extend(
                _parse_downstream_table(extracted["headers"], extracted["rows"])
            )
        elif table_type == "upstream":
            diagnostics.upstream.extend(
                _parse_upstream_table(extracted["headers"], extracted["rows"])
            )

    _LOGGER.debug(
        "Parsed %d downstream and %d upstream channels",
        len(diagnostics.downstream),
        len(diagnostics.upstream),
    )

    return diagnostics
