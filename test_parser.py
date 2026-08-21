"""Local helper to test the diagnostics page parser against saved HTML.

Usage:
    python test_parser.py Diagnostics.asp.html

Install beautifulsoup4 first:
    pip install beautifulsoup4
"""

import sys
from pathlib import Path

# Make the integration package importable.
sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "thomson_modem"))

from parser import parse_diagnostics_page  # noqa: E402


def main() -> int:
    """Run the parser on a saved HTML file."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path-to-Diagnostics.asp.html>")
        return 1

    html_path = Path(sys.argv[1])
    if not html_path.exists():
        print(f"File not found: {html_path}")
        return 1

    html = html_path.read_text(encoding="utf-8", errors="replace")
    data = parse_diagnostics_page(html)

    print(f"Downstream channels: {len(data.downstream)}")
    for ch in data.downstream:
        print(f"  DS {ch.channel_id}: {ch.lock_status}, {ch.frequency} MHz, {ch.power} dBmV, {ch.snr} dB, BER={ch.ber}%, {ch.modulation}, corrected={ch.corrected}, uncorrected={ch.uncorrected}")

    print(f"Upstream channels: {len(data.upstream)}")
    for ch in data.upstream:
        print(f"  US {ch.channel_id}: {ch.lock_status}, {ch.frequency} MHz, {ch.power} dBmV, {ch.modulation}")

    print("\nStatus items:")
    for key, value in data.status.items():
        print(f"  {key}: {value}")

    print(f"\nRaw tables found: {len(data.raw_tables)}")
    for idx, table in enumerate(data.raw_tables):
        print(f"  Table {idx}: headers={table['headers']}, rows={len(table['rows'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
