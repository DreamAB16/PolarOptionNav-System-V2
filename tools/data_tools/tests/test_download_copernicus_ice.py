from datetime import date
from pathlib import Path

import pytest

from core.config.environment_config import get_dataset_path
import tools.data_tools.download.download_copernicus_ice as module


def test_date_modes_and_output_path() -> None:
    assert module.build_dates(date(2025, 2, 15), None, None) == [date(2025, 2, 15)]
    assert module.build_dates(None, date(2025, 2, 15), date(2025, 2, 17)) == [
        date(2025, 2, 15),
        date(2025, 2, 16),
        date(2025, 2, 17),
    ]
    assert module.output_path(date(2025, 2, 15)) == (
        get_dataset_path("ice") / "raw" / "copernicus" / "arctic_ice_20250215.nc"
    )
    with pytest.raises(ValueError, match="not both"):
        module.build_dates(date(2025, 2, 15), date(2025, 2, 15), date(2025, 2, 15))


def test_dry_run_does_not_require_credentials_or_network(capsys: pytest.CaptureFixture[str]) -> None:
    assert module.main(["--date", "2025-02-15", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert module.PRODUCT_ID in output
    assert module.DATASET_ID in output
    assert "siconc,sithick" in output
    assert "arctic_ice_20250215.nc" in output


def test_download_scene_delegates_to_toolbox_and_validates_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def fake_subset(**kwargs: object) -> None:
        calls.append(kwargs)
        target = Path(kwargs["output_directory"]) / str(kwargs["output_filename"])
        target.write_bytes(b"mock-netcdf")

    expected_mapping = {"concentration": "siconc", "thickness": "sithick"}
    monkeypatch.setattr(module, "inspect_download", lambda _: expected_mapping)

    result = module.download_scene(
        date(2025, 2, 15),
        output_directory=tmp_path,
        subset_function=fake_subset,
        retries=0,
    )

    assert result.status == "downloaded"
    assert result.variable_map == expected_mapping
    assert calls[0]["dataset_id"] == module.DATASET_ID
    assert calls[0]["variables"] == list(module.VARIABLES)
    assert "username" not in calls[0]
    assert "password" not in calls[0]


def test_cf_metadata_builds_semantic_variable_mapping() -> None:
    def variable(standard_name: str, long_name: str = "") -> dict[str, str]:
        return {"standard_name": standard_name, "long_name": long_name}

    mapping = module._variable_map({
        "variables": {
            "a": variable("sea_ice_area_fraction"),
            "b": variable("sea_ice_thickness"),
            "c": variable("sea_ice_classification", "Multi-year Ice"),
            "d": variable("sea_ice_classification", "Young Ice"),
            "e": variable("eastward_sea_ice_velocity"),
            "f": variable("northward_sea_ice_velocity"),
            "g": variable("surface_snow_thickness"),
        }
    })

    assert mapping == {
        "concentration": "a",
        "thickness": "b",
        "snow_thickness": "g",
        "ice_type_multi_year": "c",
        "ice_type_young": "d",
        "drift_u": "e",
        "drift_v": "f",
    }
