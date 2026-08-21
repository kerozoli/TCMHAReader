# Thomson Cable Modem Diagnostics

A custom integration for Home Assistant that polls the `Diagnostics.asp` page of a Thomson / Technicolor cable modem and exposes meaningful sensors.

## Supported sensors

The integration creates sensors automatically based on the tables found on the diagnostics page. Typical sensors include:

- **Downstream aggregates**
  - `Downstream channel count` — total channels found on the page
  - `Downstream active channels` — channels with a locked/online status, or all non-placeholder channels when the page has no explicit lock column
  - `Downstream locked channels` — only created when the modem reports a lock-status column
  - `Downstream average SNR` (only when the modem reports SNR)
  - `Downstream average power` (only when the modem reports power)
  - `Downstream average BER` (only when the modem reports BER)
  - `Downstream corrected codewords` (only when the modem reports them)
  - `Downstream uncorrected codewords` (only when the modem reports them)

- **Upstream aggregates**
  - `Upstream channel count` — total channels found on the page
  - `Upstream active channels` — channels with a locked/online status, or all non-placeholder channels when the page has no explicit lock column
  - `Upstream locked channels` — only created when the modem reports a lock-status column
  - `Upstream average power` (only when the modem reports power)

The parser understands both "Forward Path"/"Return Path" (Thomson style) and "Downstream"/"Upstream" naming.

> **Note:** Many Thomson pages (including the sample `Diagnostics.asp`) do **not** include a lock-status column. In that case `Downstream active channels` / `Upstream active channels` are the sensors to watch for restart alerts.

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations** → **Custom repositories**.
3. Add `https://github.com/kero/TCMHAReader` as type **Integration**.
4. Install the **Thomson Cable Modem Diagnostics** integration.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/thomson_modem` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** → **Devices & services** → **Add integration**.
2. Search for **Thomson Cable Modem Diagnostics**.
3. Enter the diagnostics page URL, e.g. `http://192.168.100.1/Diagnostics.asp`.
4. If your modem requires authentication, enter the username and password.
5. Adjust the update interval if desired.

## Troubleshooting

If the integration connects but reports **no usable data**, the HTML layout of your modem's `Diagnostics.asp` page may differ from what the generic parser expects. To fix this:

1. Save the HTML source of `http://192.168.100.1/Diagnostics.asp` to a file.
2. Open an issue in this repository and attach the file (redact any sensitive info).

The parser looks for HTML tables with headers such as `Channel ID`, `Frequency`, `Power`, `SNR`, `Modulation`, `Lock Status`, `Corrected`, and `Uncorrected`.

You can also test the parser locally without Home Assistant:

```bash
pip install beautifulsoup4
python test_parser.py Diagnostics.asp.html
```

## Sources

- [Thomson / RCA DCM425 User Manual](https://www.vmedia.ca/support/documents/Thomson_DCM425_User_Manual.pdf)
- [Technicolor TC4400 parser reference (itsDNNS/docsight)](https://github.com/itsDNNS/docsight/blob/main/app/drivers/tc4400.py)
