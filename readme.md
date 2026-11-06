# TRANSSKIN

A Rainmeter skin for Windows that pairs a compact system monitor with an
offline Hindu Panchang display.

![TRANSSKIN](preview.png)

Everything runs locally. The Panchang is calculated on this machine from a
bundled city catalog and a standard-library-only solar/lunar model, so there is
no API key, no geocoding service, and no network call.

## Requirements

- Rainmeter 4.5 or newer (built and tested against 4.5.28)
- Python 3.11 or newer - only needed to generate Panchang data
- The Open Sans fonts are bundled in `@Resources\fonts`, so nothing needs to be
  installed system-wide

## Install

1. Copy the `TRANSSKIN` folder into:

   ```text
   %USERPROFILE%\Documents\Rainmeter\Skins\TRANSSKIN
   ```

2. Load `Transperent.ini` (the dashboard) and `Panchang\Panchangtransperent.ini`
   (the Panchang panel).
3. Right-click either skin and choose **Open Panchang Settings** to generate the
   first day's data.

The folder must keep the name `TRANSSKIN`, because the config names used by the
settings panels are `TRANSSKIN` and `TRANSSKIN\Panchang`.

## What the skins show

**Dashboard** - `Transperent.ini`

- Upload / download rate, plus cumulative sent and received totals
- Upload and download histograms
- Four CPU cores with per-core bars and percentages, plus a CPU histogram
- RAM and SWAP usage as percentage, used/total, and a bar
- `C:\` and `D:\` usage with bars; click a drive label to open it in Explorer

Middle-clicking either skin refreshes Rainmeter.

**Panchang** - `Panchang\Panchangtransperent.ini`

- Time, date, and weekday
- Moon phase image for the current tithi
- Tithi with its end time, paksha, lunar month and ritu, samvatsara and samvat
- A red status line that appears only when the data is stale or unavailable

## Colour settings

Right-click either skin and choose **Open Color Settings**. The panel at
`ColorSettings\ColorSettings.ini` edits all three colours from one palette.

| Target row | Variable | What it recolours |
| --- | --- | --- |
| FONT COLOR | `FONT_COLOR` | Dashboard labels and readouts |
| BAR COLOR | `BAR_COLOR` | CPU core bars, RAM / SWAP / disk bars, histograms, underlines |
| PANCHANG TEXT COLOR | `PANCHANG_FONT_COLOR` | All text in the Panchang skin |

Usage:

1. Click a target row. The whole row is clickable - its label, value box, or
   colour preview.
2. Click any of the 60 swatches below. Only the highlighted target changes.

The accent highlight marks the active target, and the caption under the palette
confirms it, for example `Swatches apply to: BAR COLOR`.

To enter an exact colour, click the target's value box and type RGBA such as
`204,255,178,255`, then press Enter. Typing behaves the same as clicking a
swatch.

Every change is written to `@Settings\Variables.inc` and the skin that consumes
that variable is reloaded, so the new colour appears immediately and survives a
restart.

- **REFRESH ALL** reloads both skins. Use it after editing `Variables.inc` by
  hand.
- **CLOSE** hides the panel.

The panel is 430x378 pixels, which fits a 1280x720 screen.

## Panchang settings

Right-click either skin and choose **Open Panchang Settings**. The panel at
`PanchangSettings\PanchangSettings.ini` edits:

- Country and city
- IANA timezone, such as `Asia/Kolkata`
- Lunar month convention
- The Panchang text colour (the palette above is the nicer way to do this)

Coordinates are derived from the selected country and city in the bundled offline
catalog, so they are not editable fields.

After editing a field, press Enter to commit it, then click **SAVE & REFRESH**.
That runs the local calculator, regenerates the data files, reloads the skins,
and closes the panel.

The lunar convention buttons set both related values together:

- **AMAVASYA** -> `south-indian` + `amavasya`
- **PURNIMA** -> `north-indian` + `purnima`

## Panchang data

Generate a day's data from the skin folder:

```powershell
python tools\panchang\calculate_panchang.py
```

The default output is `@Resources\panchang.json`, with a matching Rainmeter
include at `@Resources\plugins\PanchangData.inc`. Both are written from the same
payload, so they never disagree.

With no flags the calculator reads the values already saved in
`@Settings\Variables.inc`. If a key is missing, the built-in fallback is India /
Mumbai, North Indian, Purnima-starting. Override any of it with `--country`,
`--city`, `--timezone`, `--calendar`, `--region`, `--month-start`,
`--show-shaka`, and `--show-vikram`. Unknown cities fail rather than falling back
to online geocoding.

The Panchang skin keeps itself current. On load it checks `PanchangIsStale` and
`PanchangDate`, and if the data is stale or was calculated for another day it
runs `tools\panchang\update-panchang.ps1` and reloads only itself. Retries are
capped at one per hour.

To update from the command line:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\panchang\update-panchang.ps1 -RefreshRainmeter
```

For a daily task, point Task Scheduler at:

```text
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\Gari Nikhil\Documents\Rainmeter\Skins\TRANSSKIN\tools\panchang\update-panchang.ps1" -RefreshRainmeter
```

See `tools\panchang\README.md` for the calculator's accuracy notes and the full
option list.

## Configuration

`@Settings\Variables.inc` holds the user-editable values. These are read by the
skins:

| Variable | Used for |
| --- | --- |
| `FONT_COLOR` | Dashboard text |
| `BAR_COLOR` | Bars, histograms, underlines |
| `PANCHANG_FONT_COLOR` | Panchang text |
| `BRIGHTRED` | Stale-data warning line |
| `PANCHANG_COUNTRY`, `PANCHANG_CITY`, `PANCHANG_TIMEZONE`, `PANCHANG_CALENDAR`, `PANCHANG_REGION`, `PANCHANG_MONTH_START` | Passed to the calculator |
| `PANCHANG_SHOW_SHAKA`, `PANCHANG_SHOW_VIKRAM` | Which samvat lines to emit |

Prefer the settings panels over editing the file by hand, then click **REFRESH
ALL**.

## Tests

The Panchang calculator and the skin files are covered by a pytest suite:

```powershell
python -m pytest -q
```

Run it from the skin folder. It currently covers the calculator, the generated
Rainmeter include, the colour palette wiring, and the Panchang settings panel.

## Folder layout

```text
TRANSSKIN\
  Transperent.ini                  Dashboard
  Panchang\Panchangtransperent.ini Panchang panel
  ColorSettings\ColorSettings.ini  Shared palette + target selector
  PanchangSettings\PanchangSettings.ini
  @Resources\
    fonts\                         Bundled Open Sans
    images\                        Moon phase images
    plugins\PanchangData.inc       Generated Rainmeter variables
    panchang.json                  Generated Panchang data
  @Settings\Variables.inc          User settings
  tools\panchang\                  Offline calculator, updater, tests
```

## Known limitations

- The location line under the moon is fixed text. Changing the city in Panchang
  Settings affects the calculation but not that label.
- `NetInSpeed` and `NetOutSpeed` in `Transperent.ini` still reference
  `#maxDownload#` and `#maxUpload#`, which are not defined. Define them in
  `Variables.inc` or point those options at `NetworkMaxDown` / `NetworkMaxUp` to
  scale the network histograms correctly.
- `DiskDriveC`, `DiskDriveD`, `ShowDiskD`, `ShowCpuCore1`-`ShowCpuCore4`,
  `NetworkMaxUp`, `NetworkMaxDown`, and `ProcessInterval` are not read by the
  current dashboard. Drive letters and core count are fixed in
  `Transperent.ini`.
- The tithi line prints the raw data value, so it reads like `27,Dwadashi`
  rather than `Dwadashi`.
- Lunar month labels follow the amanta/purnimanta convention you pick and can be
  one month off from a reference that uses the other.

## Credits

Skin by M.NIKHIL. Bundled Open Sans fonts are licensed under the Apache License
2.0. The Panchang calculator is standard-library Python and ships with its own
offline city catalog.
