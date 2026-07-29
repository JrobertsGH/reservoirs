"""Unit tests for the pure-Python parts of ras_project.py -- the mapping/
geometry helpers that don't require a live HEC-RAS project. The functions
that actually call ras-commander/HEC-RAS (create_dam_project, attach_terrain,
configure_2d_flow_area, generate_mesh, apply_breach_parameters,
configure_initial_and_boundary_conditions, run_plan) are integration-level
and are exercised via manual smoke test against a real HEC-RAS install, not
automated pytest -- consistent with docs/methodology.md's testing approach.
"""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from reservoirs.breach_params import BreachEstimate
from reservoirs.config import DamConfig, FailureMode, HazardClass, Location
from reservoirs.ras_project import (
    breach_geom_kwargs,
    breach_structure_name,
    flow_area_perimeter_from_terrain,
)


def make_dam(**overrides) -> DamConfig:
    defaults = dict(
        name="Fall River Reservoir",
        state_dam_id="070129",
        county="Clear Creek",
        owner="Agricultural Ditch & Reservoir Company",
        location=Location(latitude=39.82, longitude=-105.69),
        hazard_class=HazardClass.high,
        embankment_type="Earth embankment",
        year_completed=1974,
        height_ft=85.0,
        crest_length_ft=840.0,
        crest_elevation_ft=10841.0,
        normal_storage_ac_ft=890.0,
        surface_area_ac=24.0,
        drainage_area_ac=1792.0,
    )
    defaults.update(overrides)
    return DamConfig(**defaults)


class TestBreachStructureName:
    def test_appends_dam_suffix(self):
        dam = make_dam(name="Fall River Reservoir")
        assert breach_structure_name(dam) == "Fall River Reservoir Dam"

    def test_uses_dam_specific_name(self):
        dam = make_dam(name="Loch Lomond")
        assert breach_structure_name(dam) == "Loch Lomond Dam"


class TestFlowAreaPerimeterFromTerrain:
    def test_returns_closed_rectangle_matching_raster_bounds(self, tmp_path):
        elevation = np.zeros((10, 10), dtype="float32")
        transform = from_origin(100.0, 200.0, 5.0, 5.0)  # left=100, top=200, 5ft cells
        path = tmp_path / "terrain.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=10, width=10, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(elevation, 1)

        perimeter = flow_area_perimeter_from_terrain(path)

        assert perimeter[0] == perimeter[-1]  # closed ring
        xs = [p[0] for p in perimeter]
        ys = [p[1] for p in perimeter]
        assert min(xs) == 100.0
        assert max(xs) == 100.0 + 10 * 5.0
        assert min(ys) == 200.0 - 10 * 5.0
        assert max(ys) == 200.0

    def test_perimeter_has_four_distinct_corners(self, tmp_path):
        elevation = np.zeros((4, 4), dtype="float32")
        transform = from_origin(0, 40, 10, 10)
        path = tmp_path / "terrain.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=4, width=4, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(elevation, 1)

        perimeter = flow_area_perimeter_from_terrain(path)
        assert len(set(perimeter[:-1])) == 4


class TestBreachGeomKwargs:
    def _sample_estimate(self):
        return BreachEstimate(
            method="Froehlich (2008)",
            failure_mode=FailureMode.piping,
            breach_formation_factor_ac_ft2=None,
            volume_eroded_yd3=None,
            average_breach_width_ft=112.4,
            side_slope_h_per_v=0.7,
            formation_time_hr=0.23,
            erosion_rate_ft_per_hr=488.7,
            erosion_rate_over_hw=5.75,
            breach_width_over_height=1.32,
            warnings=[],
        )

    def test_maps_estimate_fields_to_ras_breach_kwargs(self):
        estimate = self._sample_estimate()
        kwargs = breach_geom_kwargs(estimate, breach_bottom_elev_ft=10756.0, weir_top_elev_ft=10841.0)

        assert kwargs["initial_width"] == estimate.average_breach_width_ft
        assert kwargs["left_slope"] == estimate.side_slope_h_per_v
        assert kwargs["right_slope"] == estimate.side_slope_h_per_v
        assert kwargs["formation_time"] == estimate.formation_time_hr
        assert kwargs["final_bottom_elev"] == 10756.0
        assert kwargs["top_elev"] == 10841.0
        assert kwargs["active"] is True

    def test_symmetric_side_slopes(self):
        # HEC-RAS wants left/right slopes separately; breach_params only
        # produces one symmetric Zb, so both should match exactly.
        estimate = self._sample_estimate()
        kwargs = breach_geom_kwargs(estimate, breach_bottom_elev_ft=0.0, weir_top_elev_ft=1.0)
        assert kwargs["left_slope"] == kwargs["right_slope"]
