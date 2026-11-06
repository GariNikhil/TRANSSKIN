"""Offline Panchang calculator for the TRANSSKIN Rainmeter skin.

This module intentionally contains no network, API, database, or API-key logic.
It includes a self-contained low-precision astronomical model and writes the
JSON contract plus the generated Rainmeter variables consumed by the skin.
``--allow-pending`` remains available only for verifying the local file
pipeline without calculated values.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_LATITUDE = 14.6819
DEFAULT_LONGITUDE = 77.6006
DEFAULT_LOCATION = "Anantapur, Andhra Pradesh"
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_CALENDAR = "telugu-amanta"
DEFAULT_COUNTRY = "India"
DEFAULT_CITY = "Anantapur"
DEFAULT_REGION = "south-indian"
DEFAULT_MONTH_START = "amavasya"
REGION_MONTH_START = {
    "south-indian": "amavasya",
    "north-indian": "purnima",
}
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "@Resources" / "panchang.json"
DEFAULT_RAINMETER_OUTPUT = (
    Path(__file__).resolve().parents[2] / "@Resources" / "plugins" / "PanchangData.inc"
)
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "@Settings" / "Variables.inc"
STALE_AFTER_SECONDS = 172800
INDIA_STANDARD_TIME = timezone(timedelta(hours=5, minutes=30), name="IST")
TIMEZONE_ALIASES = {
    "Asia/Mumbai": DEFAULT_TIMEZONE,
}
MOON_IMAGE_DIRECTORY = "images\\moom phases"
MOON_IMAGE_FALLBACK = f"{MOON_IMAGE_DIRECTORY}\\realistic.jpg"

LOCATION_CATALOG: dict[tuple[str, str], tuple[float, float, str]] = {
    ("india", "anantapur"): (14.6819, 77.6006, "Asia/Kolkata"),
    ("india", "hyderabad"): (17.3850, 78.4867, "Asia/Kolkata"),
    ("india", "bengaluru"): (12.9716, 77.5946, "Asia/Kolkata"),
    ("india", "chennai"): (13.0827, 80.2707, "Asia/Kolkata"),
    ("india", "mumbai"): (19.0760, 72.8777, "Asia/Kolkata"),
    ("india", "kolkata"): (22.5726, 88.3639, "Asia/Kolkata"),
    ("india", "delhi"): (28.6139, 77.2090, "Asia/Kolkata"),
}


class ConfigurationError(ValueError):
    """Raised when calculator configuration is invalid."""


def location_key(country: str, city: str) -> tuple[str, str]:
    """Normalize a country/city pair for local catalog lookup."""

    return country.strip().casefold(), city.strip().casefold()


def resolve_location(country: str, city: str) -> tuple[float, float, str]:
    """Resolve a configured country/city from the bundled offline catalog."""

    try:
        return LOCATION_CATALOG[location_key(country, city)]
    except KeyError as error:
        supported = ", ".join(
            f"{country_name}/{city_name}"
            for country_name, city_name in LOCATION_CATALOG
        )
        raise ConfigurationError(
            f"location {country!r}/{city!r} is not in the offline catalog; "
            f"supported locations: {supported}"
        ) from error


def get_timezone(timezone_name: str) -> tzinfo:
    """Return the configured timezone, including Windows-safe IST support."""

    timezone_name = TIMEZONE_ALIASES.get(timezone_name.strip(), timezone_name.strip())
    if timezone_name == DEFAULT_TIMEZONE:
        return INDIA_STANDARD_TIME
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ConfigurationError(
            f"unknown IANA timezone: {timezone_name!r}"
        ) from error


@dataclass(frozen=True, slots=True)
class PanchangConfig:
    """Validated location and calendar configuration."""

    latitude: float = DEFAULT_LATITUDE
    longitude: float = DEFAULT_LONGITUDE
    location: str = DEFAULT_LOCATION
    timezone_name: str = DEFAULT_TIMEZONE
    calendar: str = DEFAULT_CALENDAR
    show_shaka: bool = True
    show_vikram: bool = True
    country: str = DEFAULT_COUNTRY
    city: str = DEFAULT_CITY
    region: str = DEFAULT_REGION
    month_start: str = ""

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90:
            raise ConfigurationError("latitude must be between -90 and 90")
        if not -180 <= self.longitude <= 180:
            raise ConfigurationError("longitude must be between -180 and 180")
        if not self.location.strip():
            raise ConfigurationError("location must not be empty")
        if not self.country.strip() or not self.city.strip():
            raise ConfigurationError("country and city must not be empty")
        if self.region not in {"north-indian", "south-indian"}:
            raise ConfigurationError("region must be 'north-indian' or 'south-indian'")
        if not self.month_start:
            object.__setattr__(self, "month_start", REGION_MONTH_START[self.region])
        if self.month_start not in {"amavasya", "purnima"}:
            raise ConfigurationError("month_start must be 'amavasya' or 'purnima'")
        if self.month_start != REGION_MONTH_START[self.region]:
            raise ConfigurationError(
                f"{self.region} requires {REGION_MONTH_START[self.region]} month start"
            )
        if self.calendar != DEFAULT_CALENDAR:
            raise ConfigurationError(
                f"unsupported calendar {self.calendar!r}; expected {DEFAULT_CALENDAR!r}"
            )
        get_timezone(self.timezone_name)


def parse_bool(value: str) -> bool:
    """Parse a human-friendly boolean command-line value."""

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


def build_config(args: argparse.Namespace) -> PanchangConfig:
    """Build validated configuration from parsed command-line arguments."""

    latitude, longitude, timezone_name = resolve_location(args.country, args.city)
    return PanchangConfig(
        latitude=latitude,
        longitude=longitude,
        location=f"{args.city}, {args.country}",
        timezone_name=args.timezone or timezone_name,
        calendar=args.calendar,
        show_shaka=True if args.show_shaka is None else args.show_shaka,
        show_vikram=True if args.show_vikram is None else args.show_vikram,
        country=args.country,
        city=args.city,
        region=args.region,
        month_start=args.month_start,
    )


def read_rainmeter_variables(path: Path) -> dict[str, str]:
    """Read simple ``key=value`` values from the canonical Rainmeter config."""

    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("[") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def config_from_file(path: Path) -> dict[str, Any]:
    """Return calculator arguments from the canonical Rainmeter variables file."""

    values = read_rainmeter_variables(path)
    return {
        "country": values.get("PANCHANG_COUNTRY", DEFAULT_COUNTRY),
        "city": values.get("PANCHANG_CITY", DEFAULT_CITY),
        "timezone": values.get("PANCHANG_TIMEZONE") or None,
        "calendar": values.get("PANCHANG_CALENDAR", DEFAULT_CALENDAR),
        "region": values.get("PANCHANG_REGION", DEFAULT_REGION),
        "month_start": values.get("PANCHANG_MONTH_START") or None,
        "show_shaka": parse_bool(values.get("PANCHANG_SHOW_SHAKA", "1")),
        "show_vikram": parse_bool(values.get("PANCHANG_SHOW_VIKRAM", "1")),
    }


TITHI_NAMES = (
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima",
)
LUNAR_MONTH_NAMES = (
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashvina", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna",
)
SAMVATSARA_NAMES = (
    "Prabhava", "Vibhava", "Shukla", "Pramodoota", "Prajotpatti", "Angirasa",
    "Shrimukha", "Bhava", "Yuva", "Dhata", "Ishvara", "Bahudhanya",
    "Pramathi", "Vikrama", "Vrisha", "Chitrabhanu", "Svabhanu", "Tarana",
    "Parthiva", "Vyaya", "Sarvajit", "Sarvadhari", "Virodhi", "Vikriti",
    "Khara", "Nandana", "Vijaya", "Jaya", "Manmatha", "Durmukhi",
    "Hevilambi", "Vilambi", "Vikari", "Sharvari", "Plava", "Shubhakrit",
    "Shobhakrit", "Krodhi", "Vishvavasu", "Parabhava", "Plavanga", "Kilaka",
    "Saumya", "Sadharana", "Virodhikrit", "Paridhavi", "Pramadi", "Ananda",
    "Rakshasa", "Nala", "Pingala", "Kalayukti", "Siddharthi", "Raudra",
    "Durmati", "Dundubhi", "Rudhirodgari", "Raktakshi", "Krodhana", "Akshaya",
)
SYNODIC_MONTH_DAYS = 29.530588


def julian_day(moment: datetime) -> float:
    """Convert an aware datetime to Julian Day."""

    utc_moment = moment.astimezone(timezone.utc)
    return utc_moment.timestamp() / 86400.0 + 2440587.5


def normalize_degrees(value: float) -> float:
    """Normalize an angle to the half-open range [0, 360)."""

    return value % 360.0


def sun_ecliptic_longitude(moment: datetime) -> float:
    """Estimate geocentric solar ecliptic longitude in degrees.

    This is a compact low-precision solar model suitable for a local desktop
    display. It is not intended for publishing legal or religious almanac
    tables without comparison against a higher-precision reference.
    """

    days = julian_day(moment) - 2451545.0
    mean_longitude = normalize_degrees(280.460 + 0.9856474 * days)
    mean_anomaly = math.radians(normalize_degrees(357.528 + 0.9856003 * days))
    correction = 1.915 * math.sin(mean_anomaly) + 0.020 * math.sin(2 * mean_anomaly)
    return normalize_degrees(mean_longitude + correction)


def moon_ecliptic_longitude(moment: datetime) -> float:
    """Estimate geocentric lunar ecliptic longitude in degrees."""

    days = julian_day(moment) - 2451543.5
    ascending_node = math.radians(normalize_degrees(125.1228 - 0.0529538083 * days))
    inclination = math.radians(5.1454)
    argument = math.radians(normalize_degrees(318.0634 + 0.1643573223 * days))
    eccentricity = 0.054900
    semi_major_axis = 60.2666
    mean_anomaly = math.radians(normalize_degrees(115.3654 + 13.0649929509 * days))

    eccentric_anomaly = mean_anomaly
    for _ in range(8):
        eccentric_anomaly -= (
            eccentric_anomaly - eccentricity * math.sin(eccentric_anomaly) - mean_anomaly
        ) / (1 - eccentricity * math.cos(eccentric_anomaly))

    x_orbital = semi_major_axis * (math.cos(eccentric_anomaly) - eccentricity)
    y_orbital = semi_major_axis * math.sqrt(1 - eccentricity**2) * math.sin(eccentric_anomaly)
    true_anomaly = math.atan2(y_orbital, x_orbital)
    radius = math.hypot(x_orbital, y_orbital)
    longitude = true_anomaly + argument

    x_ecliptic = radius * (
        math.cos(ascending_node) * math.cos(longitude)
        - math.sin(ascending_node) * math.sin(longitude) * math.cos(inclination)
    )
    y_ecliptic = radius * (
        math.sin(ascending_node) * math.cos(longitude)
        + math.cos(ascending_node) * math.sin(longitude) * math.cos(inclination)
    )
    return normalize_degrees(math.degrees(math.atan2(y_ecliptic, x_ecliptic)))


def lunar_phase(moment: datetime) -> float:
    """Return the Moon-minus-Sun elongation in degrees."""

    return normalize_degrees(moon_ecliptic_longitude(moment) - sun_ecliptic_longitude(moment))


def tithi_number(phase: float) -> int:
    """Return the 1-based tithi number for a lunar phase."""

    return min(30, int(normalize_degrees(phase) // 12.0) + 1)


def tithi_name(number: int) -> str:
    """Return a traditional English tithi name."""

    if number == 15 or number == 30:
        return "Purnima" if number == 15 else "Amavasya"
    return TITHI_NAMES[(number - 1) % 15]


def paksha(number: int) -> str:
    """Return the lunar half for a tithi number."""

    return "Shukla" if number <= 15 else "Krishna"


def moon_image_path(number: int) -> str:
    """Return the bundled moon image for a tithi, relative to ``@Resources``."""

    if number == 15:
        return f"{MOON_IMAGE_DIRECTORY}\\shukla\\purnima.jpg"
    if number == 30:
        return f"{MOON_IMAGE_DIRECTORY}\\krishna\\amavasya.jpg"
    if 1 <= number < 15:
        return f"{MOON_IMAGE_DIRECTORY}\\shukla\\{number}.jpg"
    if 15 < number < 30:
        return f"{MOON_IMAGE_DIRECTORY}\\krishna\\{number - 15}.jpg"
    return MOON_IMAGE_FALLBACK


def next_phase_transition(moment: datetime, target_degrees: float) -> datetime:
    """Find the next phase crossing using a coarse scan and bisection."""

    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    step = timedelta(minutes=30)
    start_phase = lunar_phase(moment)
    target_delta = (target_degrees - start_phase) % 360.0
    if target_delta < 1e-8:
        target_delta = 360.0

    previous = moment
    elapsed = timedelta(0)
    upper = moment
    while elapsed <= timedelta(days=35):
        upper = previous + step
        delta = (lunar_phase(upper) - start_phase) % 360.0
        if delta >= target_delta:
            break
        previous = upper
        elapsed += step
    else:
        raise RuntimeError("could not locate the next lunar phase transition")

    lower = previous
    for _ in range(40):
        midpoint = lower + (upper - lower) / 2
        delta = (lunar_phase(midpoint) - start_phase) % 360.0
        if delta >= target_delta:
            upper = midpoint
        else:
            lower = midpoint
    return upper


def surrounding_new_moons(moment: datetime) -> tuple[datetime, datetime]:
    """Return the new moons immediately before and after ``moment``."""

    def phase_distance(value: float) -> float:
        return min(value, 360.0 - value)

    samples: list[tuple[datetime, float]] = []
    start = moment - timedelta(days=35)
    for index in range(70 * 48 + 1):
        sample_time = start + timedelta(minutes=30 * index)
        samples.append((sample_time, phase_distance(lunar_phase(sample_time))))

    minima: list[datetime] = []
    for index in range(1, len(samples) - 1):
        before = samples[index - 1][1]
        current = samples[index][1]
        after = samples[index + 1][1]
        if current <= before and current <= after:
            minima.append(samples[index][0])

    if len(minima) < 2:
        raise RuntimeError("could not locate surrounding new moons")

    previous_candidates = [event for event in minima if event <= moment]
    next_candidates = [event for event in minima if event > moment]
    if not previous_candidates or not next_candidates:
        raise RuntimeError("could not locate surrounding new moons")
    return previous_candidates[-1], next_candidates[0]


def lunar_month_name(moment: datetime, month_start: str = DEFAULT_MONTH_START) -> str:
    """Determine a lunar month using Amavasya or Purnima boundaries."""

    previous_new_moon, _ = surrounding_new_moons(moment)
    if month_start == "amavasya":
        reference = previous_new_moon + timedelta(days=SYNODIC_MONTH_DAYS / 2)
    elif month_start == "purnima":
        reference = previous_new_moon
    else:
        raise ConfigurationError("month_start must be 'amavasya' or 'purnima'")
    solar_sign = int(sun_ecliptic_longitude(reference) // 30)
    return LUNAR_MONTH_NAMES[solar_sign]


def samvatsara_name(local_date: datetime) -> str:
    """Return the approximate Telugu 60-year cycle name for the calendar year."""

    cycle_year = local_date.year if local_date.month >= 3 else local_date.year - 1
    return SAMVATSARA_NAMES[(cycle_year - 1987) % 60]


def calendar_years(local_date: datetime) -> tuple[int, int]:
    """Return approximate Shalivahana Shaka and Vikram Samvat years."""

    after_solar_new_year = (local_date.month, local_date.day) >= (3, 22)
    offset = 0 if after_solar_new_year else -1
    return local_date.year - 78 + offset, local_date.year + 57 + offset


def weekday_name(local_date: datetime) -> str:
    """Return the traditional weekday name used by the display."""

    return (
        "Somawara",
        "Mangalawara",
        "Budhawara",
        "Guruwara",
        "Shukrawara",
        "Shanivara",
        "Ravivara",
    )[local_date.weekday()]


def ritu_name(local_date: datetime) -> str:
    """Return the traditional six-season name for the local date."""

    month_day = (local_date.month, local_date.day)
    if (3, 21) <= month_day < (5, 21):
        return "Vasanta"
    if (5, 21) <= month_day < (7, 23):
        return "Grishma"
    if (7, 23) <= month_day < (9, 23):
        return "Varsha"
    if (9, 23) <= month_day < (11, 22):
        return "Sharad"
    if (11, 22) <= month_day or month_day < (1, 21):
        return "Hemanta"
    return "Shishira"


def calculate_panchang(
    config: PanchangConfig, *, now: datetime | None = None
) -> dict[str, Any]:
    """Calculate the offline Panchang payload using the local astronomy model."""

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local_time = current.astimezone(get_timezone(config.timezone_name))
    phase = lunar_phase(current)
    number = tithi_number(phase)
    next_tithi = next_phase_transition(current, (number * 12.0) % 360.0)
    shaka, vikram = calendar_years(local_time)
    return {
        "schemaVersion": 1,
        "generatedAt": local_time.isoformat(),
        "date": local_time.date().isoformat(),
        "location": {
            "name": config.location,
            "latitude": config.latitude,
            "longitude": config.longitude,
            "timezone": config.timezone_name,
        },
        "calendar": config.calendar,
        "locationSelection": {
            "country": config.country,
            "city": config.city,
            "region": config.region,
            "monthStart": config.month_start,
        },
        "tithi": {
            "name": tithi_name(number),
            "number": number,
            "paksha": paksha(number),
            "endsAt": next_tithi.astimezone(get_timezone(config.timezone_name)).isoformat(),
        },
        "moonImage": moon_image_path(number),
        "weekday": weekday_name(local_time),
        "ritu": ritu_name(local_time),
        "lunarMonth": {
            "name": lunar_month_name(current, config.month_start),
            "amanta": lunar_month_name(current, config.month_start)
            if config.month_start == "amavasya"
            else "",
            "start": config.month_start,
        },
        "samvatsara": {
            "name": samvatsara_name(local_time),
            "shaka": shaka if config.show_shaka else None,
            "vikram": vikram if config.show_vikram else None,
        },
        "status": "ok",
        "error": "",
        "staleAfterSeconds": STALE_AFTER_SECONDS,
        "isStale": False,
    }


def pending_payload(config: PanchangConfig, *, now: datetime | None = None) -> dict[str, Any]:
    """Build a development-only payload for testing the local JSON pipeline."""

    current = now or datetime.now(timezone.utc)
    local_time = current.astimezone(get_timezone(config.timezone_name))
    return {
        "schemaVersion": 1,
        "generatedAt": local_time.isoformat(),
        "date": local_time.date().isoformat(),
        "location": {
            "name": config.location,
            "latitude": config.latitude,
            "longitude": config.longitude,
            "timezone": config.timezone_name,
        },
        "calendar": config.calendar,
        "locationSelection": {
            "country": config.country,
            "city": config.city,
            "region": config.region,
            "monthStart": config.month_start,
        },
        "tithi": {"name": "", "number": 0, "paksha": "", "endsAt": ""},
        "moonImage": MOON_IMAGE_FALLBACK,
        "weekday": "",
        "ritu": "",
        "lunarMonth": {"name": "", "amanta": "", "start": config.month_start},
        "samvatsara": {
            "name": "",
            "shaka": None if not config.show_shaka else 0,
            "vikram": None if not config.show_vikram else 0,
        },
        "status": "calculation_pending",
        "error": "Local calculation is pending; this file contains no Panchang values.",
        "staleAfterSeconds": STALE_AFTER_SECONDS,
        "isStale": True,
    }


def validate_payload(payload: dict[str, Any]) -> None:
    """Validate the required local JSON contract before writing it."""

    required = {"schemaVersion", "generatedAt", "date", "location", "calendar", "status"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"JSON payload missing fields: {', '.join(sorted(missing))}")
    if payload["schemaVersion"] != 1:
        raise ValueError("unsupported JSON schema version")
    if payload["status"] not in {"ok", "calculation_pending"}:
        raise ValueError("invalid JSON payload status")


def payload_is_stale(payload: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Return whether a payload is pending, explicitly stale, or too old."""

    if payload.get("status") != "ok" or payload.get("isStale"):
        return True
    try:
        generated_at = datetime.fromisoformat(str(payload["generatedAt"]))
        current = now or datetime.now(generated_at.tzinfo or timezone.utc)
        age = (current - generated_at).total_seconds()
    except (KeyError, TypeError, ValueError):
        return True
    return age < 0 or age > int(payload.get("staleAfterSeconds", STALE_AFTER_SECONDS))


def format_tithi_end(value: str) -> str:
    """Format an ISO timestamp for compact Rainmeter display."""

    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%b %d,%H:%M").lower()
    except ValueError:
        return value


def render_rainmeter_data(payload: dict[str, Any]) -> str:
    """Render the JSON payload as the generated Rainmeter variables include."""

    validate_payload(payload)
    stale = payload_is_stale(payload)
    status = "Panchang unavailable" if payload["status"] != "ok" else (
        "Panchang data stale" if stale else "ok"
    )
    tithi = payload.get("tithi", {})
    month = payload.get("lunarMonth", {})
    samvatsara = payload.get("samvatsara", {})
    weekday = payload.get("weekday", "")
    ritu = payload.get("ritu", "")
    tithi_display = (
        f"{tithi.get('number', '')},{tithi.get('name', '')}"
        if not stale
        else "Panchang unavailable"
    )
    moon_image = MOON_IMAGE_FALLBACK
    if not stale:
        moon_image = payload.get("moonImage") or MOON_IMAGE_FALLBACK
    lines = [
        "; Generated by tools\\panchang\\calculate_panchang.py. Do not edit.",
        "[Variables]",
        f"PanchangDate={payload['date']}",
        f"PanchangTithi={tithi_display}",
        f"PanchangTithiEnd={format_tithi_end(tithi.get('endsAt', '')) if not stale else ''}",
        f"PanchangPaksha={tithi.get('paksha', '') if not stale else ''}",
        f"PanchangMoonImage={moon_image}",
        f"PanchangMonth={month.get('name', '') if not stale else ''}",
        f"PanchangMonthStart={month.get('start', '') if not stale else ''}",
        f"PanchangWeekday={weekday if not stale else ''}",
        f"PanchangRitu={ritu if not stale else ''}",
        f"PanchangSamvatsara={samvatsara.get('name', '') if not stale else ''}",
        f"PanchangSamvat={samvatsara.get('vikram') if not stale and samvatsara.get('vikram') is not None else ''}",
        f"PanchangStatus={status}",
        f"PanchangIsStale={1 if stale else 0}",
        "",
    ]
    return "\n".join(lines)


def write_json_atomically(output_path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to ``output_path`` without exposing partial content."""

    validate_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(payload, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")

    temporary_path.replace(output_path)


def write_text_atomically(output_path: Path, content: str) -> None:
    """Write text to a file without exposing partial content."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(content)
    temporary_path.replace(output_path)


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rainmeter-output", type=Path, default=DEFAULT_RAINMETER_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--country", default=None)
    parser.add_argument("--city", default=None)
    parser.add_argument("--timezone", default=None)
    parser.add_argument("--calendar", default=None)
    parser.add_argument("--region", choices=("north-indian", "south-indian"), default=None)
    parser.add_argument("--month-start", choices=("amavasya", "purnima"), default=None)
    parser.add_argument("--show-shaka", type=parse_bool, default=None)
    parser.add_argument("--show-vikram", type=parse_bool, default=None)
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="write a pending-status file for local pipeline testing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the calculator command."""

    args = create_parser().parse_args(argv)
    try:
        configured = config_from_file(args.config) if args.config.exists() else {}
        defaults = {
            "country": DEFAULT_COUNTRY,
            "city": DEFAULT_CITY,
            "calendar": DEFAULT_CALENDAR,
            "region": DEFAULT_REGION,
        }
        for key, default in defaults.items():
            if getattr(args, key) is None:
                setattr(args, key, configured.get(key, default))
        for key, value in configured.items():
            if getattr(args, key, None) is None and value is not None:
                setattr(args, key, value)
        config = build_config(args)
        if args.allow_pending:
            payload = pending_payload(config)
        else:
            payload = calculate_panchang(config)
        write_json_atomically(args.output, payload)
        write_text_atomically(args.rainmeter_output, render_rainmeter_data(payload))
    except (ConfigurationError, OSError, RuntimeError, ValueError) as error:
        print(f"panchang calculator: {error}", file=sys.stderr)
        return 1

    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())