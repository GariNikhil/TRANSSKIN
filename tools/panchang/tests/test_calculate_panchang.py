"""Tests for the offline Panchang calculator."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

import calculate_panchang as calculator  # noqa: E402


def test_default_configuration_uses_anantapur_ist() -> None:
    config = calculator.PanchangConfig()

    assert config.latitude == 14.6819
    assert config.longitude == 77.6006
    assert config.timezone_name == "Asia/Kolkata"
    assert calculator.get_timezone(config.timezone_name).utcoffset(None).total_seconds() == 19800
    assert config.country == "India"
    assert config.city == "Anantapur"
    assert config.region == "south-indian"
    assert config.month_start == "amavasya"


def test_region_selects_month_start_convention() -> None:
    assert calculator.PanchangConfig(region="south-indian").month_start == "amavasya"
    assert calculator.PanchangConfig(region="north-indian").month_start == "purnima"


def test_region_and_month_start_must_agree() -> None:
    with pytest.raises(calculator.ConfigurationError):
        calculator.PanchangConfig(region="north-indian", month_start="amavasya")


def test_country_and_city_resolve_from_offline_catalog() -> None:
    latitude, longitude, timezone_name = calculator.resolve_location("India", "Hyderabad")

    assert latitude == 17.385
    assert longitude == 78.4867
    assert timezone_name == "Asia/Kolkata"


def test_common_india_timezone_alias_is_normalized() -> None:
    assert calculator.get_timezone("Asia/Mumbai").utcoffset(None).total_seconds() == 19800


def test_canonical_variables_match_catalog_location() -> None:
    values = calculator.config_from_file(calculator.DEFAULT_CONFIG)

    assert (values["country"].casefold(), values["city"].casefold()) in calculator.LOCATION_CATALOG

    args = calculator.create_parser().parse_args([])
    for key, value in values.items():
        if getattr(args, key, None) is None and value is not None:
            setattr(args, key, value)
    config = calculator.build_config(args)

    latitude, longitude, _ = calculator.resolve_location(values["country"], values["city"])
    assert config.latitude == latitude
    assert config.longitude == longitude
    assert config.location == f"{values['city']}, {values['country']}"


def test_lunar_month_update_arguments_override_saved_configuration() -> None:
    args = calculator.create_parser().parse_args(
        ["--region", "south-indian", "--month-start", "amavasya"]
    )
    configured = calculator.config_from_file(calculator.DEFAULT_CONFIG)
    defaults = {
        "country": calculator.DEFAULT_COUNTRY,
        "city": calculator.DEFAULT_CITY,
        "calendar": calculator.DEFAULT_CALENDAR,
    }
    for key, default in defaults.items():
        if getattr(args, key) is None:
            setattr(args, key, configured.get(key, default))
    for key, value in configured.items():
        if getattr(args, key, None) is None and value is not None:
            setattr(args, key, value)

    config = calculator.build_config(args)

    assert config.region == "south-indian"
    assert config.month_start == "amavasya"


def test_unknown_city_does_not_use_network_geocoding() -> None:
    with pytest.raises(calculator.ConfigurationError, match="not in the offline catalog"):
        calculator.resolve_location("India", "Unknown City")


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91.0, 77.6), (14.6, 181.0), (-91.0, 77.6), (14.6, -181.0)],
)
def test_invalid_coordinates_are_rejected(latitude: float, longitude: float) -> None:
    with pytest.raises(calculator.ConfigurationError):
        calculator.PanchangConfig(latitude=latitude, longitude=longitude)


def test_tithi_and_paksha_are_in_valid_ranges() -> None:
    moment = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    phase = calculator.lunar_phase(moment)
    number = calculator.tithi_number(phase)

    assert 1 <= number <= 30
    assert calculator.paksha(number) in {"Shukla", "Krishna"}


def test_calculation_is_deterministic_for_fixed_time() -> None:
    config = calculator.PanchangConfig()
    moment = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)

    first = calculator.calculate_panchang(config, now=moment)
    second = calculator.calculate_panchang(config, now=moment)

    assert first == second
    assert first["status"] == "ok"
    assert first["tithi"]["number"] in range(1, 31)
    assert first["tithi"]["paksha"] in {"Shukla", "Krishna"}
    assert first["lunarMonth"]["amanta"]
    assert first["samvatsara"]["name"]


def test_atomic_output_is_valid_json(tmp_path: Path) -> None:
    output = tmp_path / "panchang.json"
    payload = calculator.pending_payload(calculator.PanchangConfig())

    calculator.write_json_atomically(output, payload)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["schemaVersion"] == 1
    assert loaded["status"] == "calculation_pending"
    assert loaded["isStale"] is True


def test_payload_validation_rejects_missing_contract_fields() -> None:
    with pytest.raises(ValueError, match="missing fields"):
        calculator.validate_payload({"schemaVersion": 1})


def test_payload_validation_accepts_calculated_payload() -> None:
    payload = calculator.calculate_panchang(
        calculator.PanchangConfig(),
        now=datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
    )

    calculator.validate_payload(payload)
    assert payload["isStale"] is False
    assert payload["staleAfterSeconds"] == 172800


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "images\\moom phases\\shukla\\1.jpg"),
        (14, "images\\moom phases\\shukla\\14.jpg"),
        (15, "images\\moom phases\\shukla\\purnima.jpg"),
        (16, "images\\moom phases\\krishna\\1.jpg"),
        (26, "images\\moom phases\\krishna\\11.jpg"),
        (29, "images\\moom phases\\krishna\\14.jpg"),
        (30, "images\\moom phases\\krishna\\amavasya.jpg"),
    ],
)
def test_moon_image_path_maps_tithi_to_bundled_image(number: int, expected: str) -> None:
    assert calculator.moon_image_path(number) == expected


def test_moon_image_path_falls_back_for_unknown_tithi() -> None:
    assert calculator.moon_image_path(0) == calculator.MOON_IMAGE_FALLBACK
    assert calculator.moon_image_path(31) == calculator.MOON_IMAGE_FALLBACK


def test_every_moon_image_path_exists_in_resources() -> None:
    resources = Path(__file__).parents[3] / "@Resources"

    for number in range(1, 31):
        assert (resources / calculator.moon_image_path(number)).is_file()
    assert (resources / calculator.MOON_IMAGE_FALLBACK).is_file()


def test_config_file_is_read_from_canonical_rainmeter_variables(tmp_path: Path) -> None:
    config_file = tmp_path / "Variables.inc"
    config_file.write_text(
        "[Variables]\n"
        "PANCHANG_COUNTRY=India\n"
        "PANCHANG_CITY=Hyderabad\n"
        "PANCHANG_TIMEZONE=Asia/Kolkata\n"
        "PANCHANG_CALENDAR=telugu-amanta\n"
        "PANCHANG_REGION=north-indian\n"
        "PANCHANG_MONTH_START=purnima\n"
        "PANCHANG_SHOW_SHAKA=0\n"
        "PANCHANG_SHOW_VIKRAM=1\n",
        encoding="utf-8",
    )

    values = calculator.config_from_file(config_file)

    assert values["city"] == "Hyderabad"
    assert values["region"] == "north-indian"
    assert values["month_start"] == "purnima"
    assert values["show_shaka"] is False


def test_location_is_derived_from_city_instead_of_legacy_coordinates(tmp_path: Path) -> None:
    config_file = tmp_path / "Variables.inc"
    config_file.write_text(
        "[Variables]\n"
        "PANCHANG_COUNTRY=India\n"
        "PANCHANG_CITY=Hyderabad\n"
        "PANCHANG_LAT=0\n"
        "PANCHANG_LON=0\n"
        "PANCHANG_LOCATION=Wrong address\n"
        "PANCHANG_TIMEZONE=Asia/Kolkata\n"
        "PANCHANG_CALENDAR=telugu-amanta\n"
        "PANCHANG_REGION=north-indian\n"
        "PANCHANG_MONTH_START=purnima\n",
        encoding="utf-8",
    )

    values = calculator.config_from_file(config_file)
    args = calculator.create_parser().parse_args([])
    for key, value in values.items():
        if getattr(args, key, None) is None and value is not None:
            setattr(args, key, value)
    config = calculator.build_config(args)

    assert config.latitude == 17.385
    assert config.longitude == 78.4867
    assert config.location == "Hyderabad, India"


def test_rainmeter_include_is_generated_from_payload() -> None:
    payload = calculator.calculate_panchang(
        calculator.PanchangConfig(),
        now=datetime.now(timezone.utc),
    )

    rendered = calculator.render_rainmeter_data(payload)

    assert "[Variables]" in rendered
    assert (
        f"PanchangTithi={payload['tithi']['number']},{payload['tithi']['name']}"
        in rendered
    )
    assert f"PanchangMonth={payload['lunarMonth']['name']}" in rendered
    assert "PanchangStatus=ok" in rendered
    assert "PanchangIsStale=0" in rendered
    assert "PanchangTithiEnd=" in rendered
    assert f"PanchangMonthStart={payload['lunarMonth']['start']}" in rendered
    assert f"PanchangMoonImage={payload['moonImage']}" in rendered
    assert f"PanchangWeekday={payload['weekday']}" in rendered
    assert f"PanchangRitu={payload['ritu']}" in rendered
    assert f"PanchangDate={payload['date']}" in rendered
    # Only the plain date may leak through; full timestamps stay out of the include.
    assert payload["generatedAt"] not in rendered


def test_rainmeter_include_uses_compact_display_format() -> None:
    moment = datetime.now(timezone.utc)
    payload = {
        "schemaVersion": 1,
        "generatedAt": moment.isoformat(),
        "date": moment.date().isoformat(),
        "location": {"name": "Anantapur, India", "latitude": 14.6819, "longitude": 77.6006, "timezone": "Asia/Kolkata"},
        "calendar": "telugu-amanta",
        "tithi": {"number": 11, "name": "Ekadashi", "paksha": "Shukla", "endsAt": "2026-10-22T14:46:00+05:30"},
        "weekday": "Guruwara",
        "ritu": "Sharad",
        "lunarMonth": {"name": "Kartika", "start": "amavasya"},
        "samvatsara": {"name": "Parabhava", "vikram": 2083},
        "status": "ok",
        "error": "",
        "staleAfterSeconds": calculator.STALE_AFTER_SECONDS,
        "isStale": False,
    }

    rendered = calculator.render_rainmeter_data(payload)

    assert "PanchangTithi=11,Ekadashi" in rendered
    assert "PanchangTithiEnd=oct 22,14:46" in rendered


def test_stale_payload_renders_safe_fallback() -> None:
    payload = calculator.calculate_panchang(
        calculator.PanchangConfig(),
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    rendered = calculator.render_rainmeter_data(payload)

    assert "PanchangTithi=Panchang unavailable" in rendered
    assert "PanchangStatus=Panchang data stale" in rendered
    assert "PanchangIsStale=1" in rendered
    assert "PanchangMoonImage=images\\moom phases\\realistic.jpg" in rendered


def test_settings_input_fields_use_executable_rainmeter_actions() -> None:
    settings_path = Path(__file__).parents[3] / "PanchangSettings" / "PanchangSettings.ini"
    settings_text = settings_path.read_text(encoding="utf-8")

    for key in ("PANCHANG_COUNTRY", "PANCHANG_CITY", "PANCHANG_TIMEZONE"):
        assert (
            f'Command1=[!WriteKeyValue Variables {key} "$UserInput$" '
            '"#ROOTCONFIGPATH#\\@Settings\\Variables.inc"]'
        ) in settings_text

    assert settings_text.count('Command2=[!Refresh "#CURRENTCONFIG#"]') == 4
    assert settings_text.count('ExecuteBatch 1-2') == 4
    assert settings_text.count('[!CommandMeasure "MeasureInput') == 4
    assert settings_text.count('LeftMouseUpAction=[!CommandMeasure "MeasureInput') == 4
    assert (
        'LeftMouseUpAction=[!CommandMeasure "MeasureUpdatePanchang" "Run"]'
    ) in settings_text
    assert 'ExecuteBatch 1-1' not in settings_text
    assert '[!CommandMeasure "MeasureUpdateAmavasya" "Run"]' in settings_text
    assert '[!CommandMeasure "MeasureUpdatePurnima" "Run"]' in settings_text
    assert 'WriteKeyValue Variables PANCHANG_REGION' not in settings_text
    assert 'PANCHANG_LAT' not in settings_text
    assert 'PANCHANG_LON' not in settings_text
    assert 'PANCHANG_LOCATION' not in settings_text
    assert '[!ZPos 0]' in settings_text
    assert settings_text.count('TopMost=0') == 4
    assert settings_text.count('FocusDismiss=0') == 4
    assert 'Text=#PANCHANG_MONTH_START# (#PANCHANG_REGION#)' in settings_text
    assert 'DynamicVariables=1' in settings_text


def test_settings_refresh_moves_current_skin_with_correct_bang_argument_order() -> None:
    settings_path = Path(__file__).parents[3] / "PanchangSettings" / "PanchangSettings.ini"
    settings_text = settings_path.read_text(encoding="utf-8")

    assert '[!Move 100 100 "#CURRENTCONFIG#"]' in settings_text
    assert '[!Move "#CURRENTCONFIG#" 100 100]' not in settings_text


def test_panchang_skin_surfaces_staleness_and_refreshes_itself() -> None:
    skin_path = Path(__file__).parents[3] / "Panchang" / "Panchangtransperent.ini"
    skin_text = skin_path.read_text(encoding="utf-8")

    assert "Text=#PanchangStatus#" in skin_text
    # The label must be hidden while healthy, so it cannot bind the stale flag directly.
    assert "Hidden=[MeasureStatusHidden]" in skin_text
    assert "Hidden=#PanchangIsStale#" not in skin_text
    assert "Formula=1 - #PanchangIsStale#" in skin_text

    # A new day is what makes the data out of date, so the stored date drives the refresh.
    assert "IfMatch=^#PanchangDate#$" in skin_text
    assert 'IfNotMatchAction=[!CommandMeasure "MeasurePanchangUpdate" "Run"]' in skin_text

    assert 'OnRefreshAction=[!UpdateMeasure "MeasureStaleCheck"]' in skin_text
    assert 'IfCondition=MeasureStaleCheck = 1' in skin_text
    assert 'IfTrueAction=[!CommandMeasure "MeasurePanchangUpdate" "Run"]' in skin_text
    assert "-RefreshRainmeter -RefreshConfig TRANSSKIN\\Panchang" in skin_text


def test_generated_include_records_the_date_it_was_calculated_for() -> None:
    moment = datetime.now(timezone.utc)
    payload = {
        "schemaVersion": 1,
        "generatedAt": moment.isoformat(),
        "date": "2026-11-01",
        "location": {"name": "Anantapur, India", "latitude": 14.6819, "longitude": 77.6006, "timezone": "Asia/Kolkata"},
        "calendar": "telugu-amanta",
        "tithi": {"number": 22, "name": "Saptami", "paksha": "Krishna", "endsAt": "2026-11-01T17:28:00+05:30"},
        "weekday": "Ravivara",
        "ritu": "Sharad",
        "lunarMonth": {"name": "Kartika", "start": "amavasya"},
        "samvatsara": {"name": "Parabhava", "vikram": 2083},
        "status": "ok",
        "error": "",
        "staleAfterSeconds": calculator.STALE_AFTER_SECONDS,
        "isStale": False,
    }

    rendered = calculator.render_rainmeter_data(payload)

    assert "PanchangDate=2026-11-01" in rendered
    assert "PanchangIsStale=0" in rendered


def test_skin_files_have_no_markdown_fences() -> None:
    skin_root = Path(__file__).parents[3]

    for path in skin_root.rglob("*.ini"):
        assert "```" not in path.read_text(encoding="utf-8"), path.name


def test_colour_variables_are_valid_rgb_values() -> None:
    variables_path = Path(__file__).parents[3] / "@Settings" / "Variables.inc"
    text = variables_path.read_text(encoding="utf-8")

    checked = 0
    for line in text.splitlines():
        stripped = line.strip()
        if "=" not in stripped or stripped.startswith(";"):
            continue
        name, value = stripped.split("=", 1)
        if "COLOR" not in name.upper() and name.upper() not in {"WHITE", "BRIGHTRED"}:
            continue

        parts = [part.strip() for part in value.split(",")]
        assert len(parts) in (3, 4), f"{name} needs 3 or 4 components, got {value!r}"
        for part in parts:
            assert part.isdigit(), f"{name} has a non-numeric component: {part!r}"
            assert 0 <= int(part) <= 255, f"{name} has a component above 255: {part}"
        checked += 1

    assert checked >= 4


COLOUR_TARGETS = [
    ("FONT_COLOR", "#ROOTCONFIG#", "FONT COLOR"),
    ("BAR_COLOR", "#ROOTCONFIG#", "BAR COLOR"),
    ("PANCHANG_FONT_COLOR", "TRANSSKIN\\Panchang", "PANCHANG TEXT COLOR"),
]


def _colour_settings_blocks() -> list[str]:
    settings_path = Path(__file__).parents[3] / "ColorSettings" / "ColorSettings.ini"
    text = settings_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return [f"[{block}" for block in text.split("\n[") if block.startswith("Swatch")]


def test_colour_settings_offer_a_clickable_palette() -> None:
    """One shared palette, 60 swatches, each applying to the selected target."""
    settings_path = Path(__file__).parents[3] / "ColorSettings" / "ColorSettings.ini"
    text = settings_path.read_text(encoding="utf-8")

    blocks = _colour_settings_blocks()
    assert len(blocks) == 60

    values = []
    for block in blocks:
        match = re.search(
            r'LeftMouseUpAction=\[!WriteKeyValue Variables #SelectedVar# "([^"]+)"',
            block,
        )
        assert match, block[:80]
        value = match.group(1)
        values.append(value)

        parts = [part.strip() for part in value.split(",")]
        assert len(parts) in (3, 4), value
        for part in parts:
            assert part.isdigit() and 0 <= int(part) <= 255, value

        # The swatch must re-read the selector, apply live, and reload the
        # skin that consumes the variable.
        assert "DynamicVariables=1" in block, block[:80]
        assert '[!SetVariable #SelectedVar# "' in block
        assert block.rstrip().endswith('[!Refresh "#SelectedRefresh#"]'), block[-70:]

    # 60 distinct colours, and only one palette (no per-target copies).
    assert len(set(values)) == 60
    for leftover in ("FontSwatch", "BarSwatch", "PanchangSwatch"):
        assert leftover not in text, leftover


def test_every_colour_swatch_refreshes_the_skin_that_uses_it() -> None:
    """Regression: writing the variable alone is not enough.

    The dashboard reads FONT_COLOR and BAR_COLOR when it loads, so a swatch that
    only refreshes the settings panel leaves Transperent.ini showing the old
    colour until Rainmeter restarts. The palette therefore refreshes whichever
    config the selected target belongs to.
    """
    settings_path = Path(__file__).parents[3] / "ColorSettings" / "ColorSettings.ini"
    text = settings_path.read_text(encoding="utf-8")

    for name, config, label in COLOUR_TARGETS:
        assert f'[!SetVariable SelectedVar "{name}"]' in text, name
        assert f'[!SetVariable SelectedRefresh "{config}"]' in text, name
        assert f'[!SetVariable SelectedLabel "{label}"]' in text, name
        assert f"Text=#{name}#" in text, name
        assert f"Fill Color #{name}#" in text, name

        # Typing a value has to behave the same way as clicking a swatch.
        assert (
            f'[!SetVariable {name} "$UserInput$"][!UpdateMeter *][!Redraw]'
            f'[!Refresh "{config}"]'
        ) in text, name

    # The whole row is selectable: hit area, label, value box and preview.
    assert text.count('[!SetVariable SelectedIndex "') == 4 * len(COLOUR_TARGETS)
    assert text.count('[!Refresh "#SelectedRefresh#"]') == 60