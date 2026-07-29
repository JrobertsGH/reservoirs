"""Unit tests for the pure-Python parts of ras_project.py -- the mapping/
geometry helpers that don't require a live HEC-RAS project. The functions
that actually call ras-commander/HEC-RAS (create_dam_project, attach_terrain,
configure_2d_flow_area, generate_mesh, apply_breach_parameters,
configure_initial_and_boundary_conditions, run_plan) are integration-level
and are exercised via manual smoke test against a real HEC-RAS install, not
automated pytest -- consistent with docs/methodology.md's testing approach.
"""

import ras_commander as rc
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from reservoirs.breach_params import BreachEstimate
from reservoirs.config import DamConfig, FailureMode, HazardClass, Location
from reservoirs.ras_project import (
    breach_geom_kwargs,
    breach_structure_name,
    create_breach_structure,
    create_reservoir_storage_area,
    dam_crest_profile,
    flow_area_perimeter_from_terrain,
    ras_connection_name,
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


def make_geom_file(tmp_path):
    path = tmp_path / "test.g01"
    path.write_text("Geom Title=Test Geometry\nProgram Version=6.60\n\n", encoding="utf-8")
    return path


class TestCreateReservoirStorageArea:
    def test_creates_non_2d_storage_area(self, tmp_path):
        geom_file = make_geom_file(tmp_path)
        perimeter = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

        create_reservoir_storage_area(geom_file, "Fall River Pool", perimeter, create_backup=False)

        areas = rc.GeomStorage.get_storage_areas(geom_file, exclude_2d=False)
        assert "Fall River Pool" in areas["Name"].tolist()
        row = areas[areas["Name"] == "Fall River Pool"].iloc[0]
        assert row["Is2D"] == False  # noqa: E712 -- numpy/pandas bool, not is-comparable

    def test_raises_on_too_few_perimeter_points(self, tmp_path):
        geom_file = make_geom_file(tmp_path)

        with pytest.raises(ValueError):
            create_reservoir_storage_area(geom_file, "Bad Pool", [(0.0, 0.0), (1.0, 1.0)], create_backup=False)

    def test_raises_on_name_too_long_for_ras_fixed_width_field(self, tmp_path):
        geom_file = make_geom_file(tmp_path)
        perimeter = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]

        with pytest.raises(ValueError):
            create_reservoir_storage_area(geom_file, "Fall River Reservoir Pool", perimeter, create_backup=False)

    def test_elevation_volume_curve_attaches_after_creation(self, tmp_path):
        geom_file = make_geom_file(tmp_path)
        perimeter = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        create_reservoir_storage_area(geom_file, "Fall River Pool", perimeter, create_backup=False)

        rc.GeomStorage.set_elevation_volume(
            geom_file, "Fall River Pool",
            elevations=[10800.0, 10820.0, 10841.0],
            volumes=[0.0, 400.0, 890.0],
            create_backup=False,
        )

        curve = rc.GeomStorage.get_elevation_volume(geom_file, "Fall River Pool")
        assert list(curve["Elevation"]) == [10800.0, 10820.0, 10841.0]
        assert list(curve["Volume"]) == [0.0, 400.0, 890.0]


class TestDamCrestProfile:
    def test_flat_profile_spans_connection_length(self):
        dam = make_dam(crest_elevation_ft=10841.0)
        profile = dam_crest_profile(dam, connection_length_ft=840.0)

        assert list(profile["Station"]) == [0.0, 840.0]
        assert list(profile["Elevation"]) == [10841.0, 10841.0]


class TestRasConnectionName:
    def test_stays_within_ras_fixed_width_limit_even_for_long_dam_names(self):
        dam = make_dam(name="Fall River Reservoir", state_dam_id="070129")
        name = ras_connection_name(dam)
        assert len(name) <= 16
        assert name == "Dam 070129"

    def test_differs_from_human_readable_breach_structure_name(self):
        dam = make_dam(name="Fall River Reservoir")
        assert ras_connection_name(dam) != breach_structure_name(dam)


class TestCreateBreachStructure:
    def test_creates_connection_between_storage_area_and_2d_flow_area(self, tmp_path):
        geom_file = make_geom_file(tmp_path)
        dam = make_dam(crest_elevation_ft=10841.0, crest_length_ft=840.0, state_dam_id="070129")

        create_reservoir_storage_area(
            geom_file, "Fall River Pool",
            [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)],
            create_backup=False,
        )
        rc.GeomStorage.set_2d_flow_area_perimeter(
            geom_file, "Downstream 2D",
            coordinates=[(200.0, -500.0), (700.0, -500.0), (700.0, 0.0), (200.0, 0.0)],
            create_backup=False,
        )

        connection_coords = [(200.0, 50.0), (200.0, 150.0)]
        create_breach_structure(
            geom_file, dam, connection_coords,
            upstream_storage_area="Fall River Pool",
            downstream_flow_area="Downstream 2D",
            create_backup=False,
        )

        connections = rc.GeomLateral.get_connections(geom_file)
        row = connections[connections["Name"] == ras_connection_name(dam)]
        assert len(row) == 1
        assert row.iloc[0]["From"] == "Fall River Pool"
        assert row.iloc[0]["To"] == "Downstream 2D"

        profile = rc.GeomLateral.get_connection_profile(geom_file, ras_connection_name(dam))
        assert list(profile["Elevation"]) == [10841.0, 10841.0]
        assert profile["Station"].iloc[-1] == pytest.approx(100.0)

    def test_rejects_area_name_too_long_for_ras_fixed_width_field(self, tmp_path):
        geom_file = make_geom_file(tmp_path)
        dam = make_dam(crest_elevation_ft=10841.0, crest_length_ft=840.0)

        with pytest.raises(ValueError):
            create_breach_structure(
                geom_file, dam, [(200.0, 50.0), (200.0, 150.0)],
                upstream_storage_area="Fall River Reservoir Pool",
                downstream_flow_area="Downstream 2D",
                create_backup=False,
            )


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
