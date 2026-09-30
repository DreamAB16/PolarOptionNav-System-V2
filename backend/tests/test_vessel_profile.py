import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from core.vessel import VesselProfile
from services.vessel_service import VesselService


PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "vessel" / "xuelong2.json"
client = TestClient(app)


def test_xuelong2_json_is_readable_and_validates_as_profile():
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile = VesselProfile.model_validate(payload)
    assert profile.identity.id == "xuelong2"
    assert profile.identity.name == "雪龙2号"


def test_current_vessel_api_returns_complete_profile():
    response = client.get("/api/vessel/current")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"identity", "geometry", "mass", "propulsion", "speed", "ice_capability", "safety_constraints"}
    assert body["identity"]["name"] == "雪龙2号"
    assert body["geometry"]["design_draft_m"] == 7.85


def test_xuelong2_key_published_parameters():
    profile = VesselService().get_current_profile()
    assert profile.geometry.length_m == 122.5
    assert profile.geometry.beam_m == 22.32
    assert profile.mass.design_displacement_t == 13996
    assert profile.speed.service_speed_min_kn == 12
    assert profile.speed.service_speed_max_kn == 15
    assert profile.speed.maximum_speed_kn == 18
    assert profile.speed.endurance_nmi == 20000
    assert profile.speed.endurance_days == 60
    assert profile.ice_capability.ice_class == "PC3"
    assert profile.ice_capability.continuous_ice_thickness_m == 1.5
    assert profile.ice_capability.continuous_snow_thickness_m == 0.2
    assert profile.propulsion.azipod_count == 2
    assert profile.propulsion.azipod_power_mw_each == 7.5
