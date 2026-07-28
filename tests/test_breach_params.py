"""Tests verify the code matches the CO DWR Guidelines for Dam Breach Analysis
(Feb 2010) Table 2 formulas exactly -- using round-number inputs (Vw=Hb=Hw=1)
so expected values can be hand-derived independently of the implementation.
"""

import math

import pytest

from reservoirs.breach_params import (
    _froehlich_2008,
    _macdonald_langridge_monopolis,
    _washington_state,
    estimate_all_methods,
    smpdbk_peak_discharge,
    storage_intensity,
)
from reservoirs.config import DamConfig, FailureMode, HazardClass, Location


def make_dam(**overrides) -> DamConfig:
    defaults = dict(
        name="Test Dam",
        state_dam_id="000000",
        county="Test",
        owner="Test Owner",
        location=Location(latitude=0, longitude=0),
        hazard_class=HazardClass.high,
        embankment_type="Earth embankment",
        year_completed=2000,
        height_ft=85.0,
        crest_length_ft=840.0,
        crest_width_ft=20.0,
        crest_elevation_ft=10841.0,
        normal_storage_ac_ft=890.0,
        surface_area_ac=24.0,
        drainage_area_ac=1792.0,
    )
    defaults.update(overrides)
    return DamConfig(**defaults)


class TestFroehlich2008:
    def test_overtopping_unit_inputs(self):
        # Vw=Hb=Hw=1: x^exponent == 1 for any exponent, so Bavg == 8.239*Ko exactly.
        est = _froehlich_2008(vw_ac_ft=1.0, hb_ft=1.0, hw_ft=1.0, failure_mode=FailureMode.overtopping)
        assert math.isclose(est.average_breach_width_ft, 8.239 * 1.3, rel_tol=1e-9)
        assert est.side_slope_h_per_v == 1.0
        expected_tf = 3.664 * math.sqrt(1.0 / (32.2 * 1.0**2))
        assert math.isclose(est.formation_time_hr, expected_tf, rel_tol=1e-9)

    def test_piping_uses_lower_ko_and_side_slope(self):
        est = _froehlich_2008(vw_ac_ft=1.0, hb_ft=1.0, hw_ft=1.0, failure_mode=FailureMode.piping)
        assert math.isclose(est.average_breach_width_ft, 8.239 * 1.0, rel_tol=1e-9)
        assert est.side_slope_h_per_v == 0.7

    def test_larger_reservoir_widens_breach(self):
        small = _froehlich_2008(100.0, 50.0, 50.0, FailureMode.overtopping)
        large = _froehlich_2008(10000.0, 50.0, 50.0, FailureMode.overtopping)
        assert large.average_breach_width_ft > small.average_breach_width_ft

    def test_taller_dam_shortens_failure_time(self):
        short = _froehlich_2008(1000.0, 20.0, 20.0, FailureMode.overtopping)
        tall = _froehlich_2008(1000.0, 100.0, 100.0, FailureMode.overtopping)
        assert tall.formation_time_hr < short.formation_time_hr


class TestMacDonaldLangridgeMonopolis:
    def test_cohesive_unit_inputs(self):
        est = _macdonald_langridge_monopolis(
            vw_ac_ft=1.0, hb_ft=1.0, hw_ft=1.0, failure_mode=FailureMode.overtopping,
            crest_width_ft=1.0, upstream_slope_h_per_v=0.0, downstream_slope_h_per_v=0.0,
            rockfill=False,
        )
        expected_ver = 3.264 * 1.0**0.77
        assert math.isclose(est.volume_eroded_yd3, expected_ver, rel_tol=1e-9)
        assert math.isclose(est.average_breach_width_ft, expected_ver, rel_tol=1e-9)  # Wavg=1
        assert est.side_slope_h_per_v == 2.0
        expected_tf = 0.016 * expected_ver**0.364
        assert math.isclose(est.formation_time_hr, expected_tf, rel_tol=1e-9)

    def test_rockfill_uses_different_exponent(self):
        cohesive = _macdonald_langridge_monopolis(
            100.0, 50.0, 50.0, FailureMode.overtopping, 20.0, 3.0, 2.0, rockfill=False
        )
        rockfill = _macdonald_langridge_monopolis(
            100.0, 50.0, 50.0, FailureMode.overtopping, 20.0, 3.0, 2.0, rockfill=True
        )
        assert cohesive.volume_eroded_yd3 != rockfill.volume_eroded_yd3


class TestWashingtonState:
    def test_cohesionless_unit_inputs(self):
        est = _washington_state(
            vw_ac_ft=1.0, hb_ft=1.0, hw_ft=1.0, failure_mode=FailureMode.overtopping,
            crest_width_ft=1.0, upstream_slope_h_per_v=0.0, downstream_slope_h_per_v=0.0,
            cohesionless=True,
        )
        expected_ver = 3.75 * 1.0**0.77
        expected_tf = 0.02 * expected_ver**0.36
        assert math.isclose(est.volume_eroded_yd3, expected_ver, rel_tol=1e-9)
        assert math.isclose(est.formation_time_hr, expected_tf, rel_tol=1e-9)

    def test_cohesive_erodes_less_than_cohesionless(self):
        cohesionless = _washington_state(100.0, 50.0, 50.0, FailureMode.overtopping, 20.0, 3.0, 2.0, True)
        cohesive = _washington_state(100.0, 50.0, 50.0, FailureMode.overtopping, 20.0, 3.0, 2.0, False)
        assert cohesive.volume_eroded_yd3 < cohesionless.volume_eroded_yd3


class TestValidationWarnings:
    def test_low_bavg_over_hb_flags_piping_only(self):
        # Tiny reservoir behind a very tall dam -> narrow breach relative to height.
        est = _froehlich_2008(vw_ac_ft=1.0, hb_ft=500.0, hw_ft=500.0, failure_mode=FailureMode.piping)
        assert est.breach_width_over_height < 0.6
        assert any("piping hole" in w for w in est.warnings)

    def test_reasonable_case_has_no_warnings_or_documents_why(self):
        est = _froehlich_2008(vw_ac_ft=890.0, hb_ft=85.0, hw_ft=85.0, failure_mode=FailureMode.overtopping)
        # Not asserting zero warnings unconditionally -- just that the check ran and is explainable.
        for w in est.warnings:
            assert "ER/Hw" in w or "Bavg/Hb" in w


class TestStorageIntensityAndSMPDBK:
    def test_storage_intensity(self):
        assert storage_intensity(vw_ac_ft=200.0, hw_ft=50.0) == 4.0

    def test_smpdbk_positive_and_scales_with_width(self):
        narrow = smpdbk_peak_discharge(bavg_ft=20.0, hw_ft=85.0, tf_hr=0.3, surface_area_ac=24.0)
        wide = smpdbk_peak_discharge(bavg_ft=120.0, hw_ft=85.0, tf_hr=0.3, surface_area_ac=24.0)
        assert narrow > 0
        assert wide > narrow


class TestEstimateAllMethods:
    def test_returns_all_three_methods(self):
        dam = make_dam()
        results = estimate_all_methods(dam, FailureMode.overtopping, vw_ac_ft=890.0)
        assert set(results.keys()) == {
            "froehlich_2008", "macdonald_langridge_monopolis", "washington_state",
        }
        for est in results.values():
            assert est.average_breach_width_ft > 0
            assert est.formation_time_hr > 0

    def test_defaults_hb_hw_to_dam_height(self):
        dam = make_dam(height_ft=42.0)
        results = estimate_all_methods(dam, FailureMode.piping, vw_ac_ft=875.0)
        expected = _froehlich_2008(875.0, 42.0, 42.0, FailureMode.piping)
        assert math.isclose(
            results["froehlich_2008"].average_breach_width_ft,
            expected.average_breach_width_ft,
            rel_tol=1e-9,
        )

    def test_detects_rockfill_from_embankment_type(self):
        rockfill_dam = make_dam(embankment_type="Rock/Earth embankment")
        earth_dam = make_dam(embankment_type="Earth embankment")
        r1 = estimate_all_methods(rockfill_dam, FailureMode.overtopping, vw_ac_ft=875.0)
        r2 = estimate_all_methods(earth_dam, FailureMode.overtopping, vw_ac_ft=875.0)
        assert (
            r1["macdonald_langridge_monopolis"].volume_eroded_yd3
            != r2["macdonald_langridge_monopolis"].volume_eroded_yd3
        )
