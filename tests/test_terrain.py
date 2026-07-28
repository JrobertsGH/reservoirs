import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio

from reservoirs.config import DamConfig, HazardClass, Location
from reservoirs.terrain import (
    bounding_box_miles,
    build_terrain_from_lidar,
    dam_data_dir,
    load_lidar_points_csv,
    points_to_grid,
    write_terrain_geotiff,
)


def make_dam(terrain_sources=None, **overrides) -> DamConfig:
    defaults = dict(
        name="Test Dam",
        state_dam_id="000000",
        county="Test",
        owner="Test Owner",
        location=Location(latitude=39.82, longitude=-105.69),
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
        terrain_sources=terrain_sources or [],
    )
    defaults.update(overrides)
    return DamConfig(**defaults)


def write_points_csv(path, points):
    """points: list of (x, y, z) tuples."""
    rows = [{"P": i + 1, "X": x, "Y": y, "Z": z, "D": "PA_Point"} for i, (x, y, z) in enumerate(points)]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


class TestLoadLidarPointsCsv:
    def test_loads_expected_columns(self, tmp_path):
        path = write_points_csv(tmp_path / "points.csv", [(0, 0, 100), (10, 10, 105)])
        df = load_lidar_points_csv(path)
        assert list(df.columns) == ["P", "X", "Y", "Z", "D"]
        assert len(df) == 2

    def test_missing_column_raises(self, tmp_path):
        path = tmp_path / "bad.csv"
        pd.DataFrame({"P": [1], "X": [0], "Y": [0]}).to_csv(path, index=False)
        with pytest.raises(ValueError, match="missing expected columns"):
            load_lidar_points_csv(path)


class TestPointsToGrid:
    def test_flat_plane_interpolates_to_constant(self):
        # A flat surface (z=100 everywhere) should grid back to ~100 everywhere,
        # including nearest-neighbor-filled edges.
        points = [(x, y, 100.0) for x in range(0, 101, 10) for y in range(0, 101, 10)]
        df = pd.DataFrame(points, columns=["X", "Y", "Z"])
        elevation, transform = points_to_grid(df, cell_size_ft=5.0)
        assert not np.isnan(elevation).any()
        assert np.allclose(elevation, 100.0, atol=1e-6)

    def test_grid_shape_matches_extent_and_cell_size(self):
        df = pd.DataFrame(
            [(0, 0, 100), (100, 0, 100), (0, 100, 100), (100, 100, 100)],
            columns=["X", "Y", "Z"],
        )
        elevation, transform = points_to_grid(df, cell_size_ft=10.0)
        assert elevation.shape == (11, 11)  # 0..100 inclusive at 10ft spacing
        assert transform.a == 10.0  # pixel width
        assert transform.e == -10.0  # pixel height (negative = north-up)

    def test_sloped_surface_preserves_gradient_direction(self):
        # z increases with x; interpolated grid should too.
        points = [(x, y, float(x)) for x in range(0, 101, 10) for y in range(0, 101, 10)]
        df = pd.DataFrame(points, columns=["X", "Y", "Z"])
        elevation, _ = points_to_grid(df, cell_size_ft=10.0)
        assert elevation[:, 0].mean() < elevation[:, -1].mean()


class TestWriteTerrainGeotiff:
    def test_round_trips_through_rasterio(self, tmp_path):
        elevation = np.array([[100.0, 101.0], [102.0, 103.0]], dtype="float32")
        transform = rasterio.transform.from_origin(0, 10, 5, 5)
        out_path = write_terrain_geotiff(elevation, transform, tmp_path / "sub" / "terrain.tif")

        assert out_path.exists()
        with rasterio.open(out_path) as src:
            assert src.crs.to_string() == "EPSG:2232"
            data = src.read(1)
            assert np.array_equal(data, elevation)
            assert src.transform == transform


class TestBuildTerrainFromLidar:
    def test_raises_without_lidar_source(self):
        dam = make_dam(terrain_sources=[])
        with pytest.raises(ValueError, match="no 'lidar_points_csv'"):
            build_terrain_from_lidar(dam)

    def test_builds_geotiff_from_configured_source(self, tmp_path):
        csv_path = write_points_csv(
            tmp_path / "points.csv",
            [(x, y, 11400.0 + x * 0.1) for x in range(0, 101, 10) for y in range(0, 101, 10)],
        )
        dam = make_dam(
            terrain_sources=[{"path": str(csv_path), "kind": "lidar_points_csv", "description": "test"}]
        )
        out_path = build_terrain_from_lidar(dam, cell_size_ft=10.0, out_dir=tmp_path / "out")

        assert out_path.exists()
        with rasterio.open(out_path) as src:
            assert src.read(1).mean() > 11400.0

    def test_merges_multiple_lidar_sources(self, tmp_path):
        csv1 = write_points_csv(tmp_path / "p1.csv", [(x, y, 100.0) for x in range(0, 51, 10) for y in range(0, 101, 10)])
        csv2 = write_points_csv(tmp_path / "p2.csv", [(x, y, 100.0) for x in range(50, 101, 10) for y in range(0, 101, 10)])
        dam = make_dam(
            terrain_sources=[
                {"path": str(csv1), "kind": "lidar_points_csv"},
                {"path": str(csv2), "kind": "lidar_points_csv"},
            ]
        )
        out_path = build_terrain_from_lidar(dam, cell_size_ft=10.0, out_dir=tmp_path / "out")
        with rasterio.open(out_path) as src:
            assert src.width >= 10  # spans the merged 0..100 extent, not just one half


class TestBoundingBoxMiles:
    def test_box_is_centered_on_point(self):
        lat, lon = 39.82, -105.69
        xmin, ymin, xmax, ymax = bounding_box_miles(lat, lon, buffer_mi=3.0)
        assert xmin < lon < xmax
        assert ymin < lat < ymax
        assert math.isclose((xmin + xmax) / 2, lon, abs_tol=1e-9)
        assert math.isclose((ymin + ymax) / 2, lat, abs_tol=1e-9)

    def test_larger_buffer_gives_larger_box(self):
        small = bounding_box_miles(39.82, -105.69, buffer_mi=1.0)
        large = bounding_box_miles(39.82, -105.69, buffer_mi=5.0)
        small_width = small[2] - small[0]
        large_width = large[2] - large[0]
        assert large_width > small_width


class TestDamDataDir:
    def test_uses_lowercased_underscored_name(self):
        dam = make_dam(name="Fall River Reservoir")
        assert dam_data_dir(dam) == Path("dams/fall_river_reservoir/data")
