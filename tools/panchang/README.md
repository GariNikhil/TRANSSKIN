# Offline Panchang Calculator

This tool generates local Panchang data for TRANSSKIN. It uses no Panchang API,
network service, remote database, geocoding service, or API key.

## Generate local data

From `C:\Users\Gari Nikhil\Documents\Rainmeter\Skins\TRANSSKIN`:

```powershell
python tools\panchang\calculate_panchang.py
```

The default output is:

```text
C:\Users\Gari Nikhil\Documents\Rainmeter\Skins\TRANSSKIN\@Resources\panchang.json
```

The default selection is India / Mumbai, North Indian, and Purnima-starting.

## Select a location and regional convention

```powershell
python tools\panchang\calculate_panchang.py `
  --country India `
  --city Hyderabad `
  --region north-indian
```

Country/city values are resolved from the bundled offline catalog. Unknown
cities fail rather than invoking online geocoding. South Indian maps to an
Amavasya-starting month; North Indian maps to a Purnima-starting month.

## Accuracy and assumptions

The calculator uses a compact, standard-library-only solar/lunar model. It is
appropriate for a local desktop display but is lower precision than a complete
ephemeris package. Tithi boundaries, lunar-month labels, and regional calendar
rules should be compared with a trusted offline Panchang reference before
being treated as an authoritative almanac.

The output contains `staleAfterSeconds` and `isStale` metadata. A successful
calculation is intended to be regenerated at least once every two days.

## Rainmeter integration

The calculator writes two synchronized outputs atomically:

- `@Resources\panchang.json` — structured data and freshness metadata.
- `@Resources\plugins\PanchangData.inc` — the Rainmeter variables include generated from the same payload.

Rainmeter includes `PanchangData.inc`. Missing, pending, or stale data is
rendered as `Panchang unavailable` rather than silently showing old values.

For a normal update, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\panchang\update-panchang.ps1 -RefreshRainmeter
```

To automate it, create a Windows Task Scheduler task that runs daily with:

```text
powershell.exe -ExecutionPolicy Bypass -File "C:\Users\Gari Nikhil\Documents\Rainmeter\Skins\TRANSSKIN\tools\panchang\update-panchang.ps1" -RefreshRainmeter
```

The Panchang skin also checks for staleness when it loads and hourly after that,
so a scheduled task is optional. It regenerates the data and reloads itself when
`PanchangIsStale` is set or when the stored date is not today's.

The Panchang calculator never makes network requests.

Drive letters and the CPU core count are set directly in `Transperent.ini`. See
the skin's main `readme.md` for the full configuration list and for the colour
palette.

## Custom Panchang settings menu

Right-click the main `TRANSSKIN` skin and choose **Open Panchang Settings**.
The settings panel is located at:

```text
C:\Users\Gari Nikhil\Documents\Rainmeter\Skins\TRANSSKIN\PanchangSettings\PanchangSettings.ini
```

The panel lets you edit:

- Country and city
- IANA timezone, such as `Asia/Kolkata`
- Panchang text colour
- Lunar month convention

Coordinates are derived automatically from the selected country and city in the
bundled offline catalog. They are not editable fields.

For colour changes, prefer the shared palette in **Open Color Settings**; it
applies to the selected target and refreshes the right skin for you.

The lunar convention buttons set both related values together:

- **AMAVASYA** → `south-indian` + `amavasya`
- **PURNIMA** → `north-indian` + `purnima`

After editing a field, press Enter to commit it, then click **SAVE & REFRESH**.
The button runs the local calculator, regenerates the JSON and Rainmeter data,
refreshes the dashboard, and closes the settings panel.