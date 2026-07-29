import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from reservoirs.config import DamConfig, HazardClass, Location
from reservoirs.terrain import (
    bounding_box_miles,
    build_terrain_from_lidar,
    build_terrain_from_lidar_and_bathymetry,
    dam_data_dir,
    estimate_downstream_channel_slope,
    extract_crest_alignment,
    load_bathymetry_points_csv,
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


def write_bathymetry_csv(path, points, swapped=True):
    """points: list of (x, y, z, description) tuples in true (Easting, Northing, Z).
    Writes with columns swapped if swapped=True, matching the real survey's
    quirk that load_bathymetry_points_csv(swap_xy=True) corrects for.
    """
    rows = []
    for i, (x, y, z, desc) in enumerate(points):
        row = {"id": i, "z": z, "description": desc}
        if swapped:
            row["x"], row["y"] = y, x
        else:
            row["x"], row["y"] = x, y
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


class TestLoadBathymetryPointsCsv:
    def test_keeps_only_bottom_points_by_default(self, tmp_path):
        path = write_bathymetry_csv(
            tmp_path / "bathy.csv",
            [(0.0, 0.0, 100.0, "BTM"), (1.0, 1.0, 105.0, ""), (2.0, 2.0, 98.0, "BTM")],
        )
        df = load_bathymetry_points_csv(path)
        assert len(df) == 2
        assert list(df.columns) == ["X", "Y", "Z"]

    def test_keeps_all_points_when_bottom_only_false(self, tmp_path):
        path = write_bathymetry_csv(
            tmp_path / "bathy.csv",
            [(0.0, 0.0, 100.0, "BTM"), (1.0, 1.0, 105.0, "")],
        )
        df = load_bathymetry_points_csv(path, bottom_only=False)
        assert len(df) == 2

    def test_swap_xy_corrects_columns(self, tmp_path):
        # true point is (Easting=5.0, Northing=9.0); written with columns swapped
        path = write_bathymetry_csv(tmp_path / "bathy.csv", [(5.0, 9.0, 100.0, "BTM")], swapped=True)
        df = load_bathymetry_points_csv(path, swap_xy=True)
        assert df.iloc[0]["X"] == 5.0
        assert df.iloc[0]["Y"] == 9.0

    def test_swap_xy_false_takes_columns_as_written(self, tmp_path):
        path = write_bathymetry_csv(tmp_path / "bathy.csv", [(5.0, 9.0, 100.0, "BTM")], swapped=False)
        df = load_bathymetry_points_csv(path, swap_xy=False)
        assert df.iloc[0]["X"] == 5.0
        assert df.iloc[0]["Y"] == 9.0

    def test_missing_column_raises(self, tmp_path):
        path = tmp_path / "bad.csv"
        pd.DataFrame({"x": [0], "y": [0]}).to_csv(path, index=False)
        with pytest.raises(ValueError, match="missing expected columns"):
            load_bathymetry_points_csv(path)


class TestBuildTerrainFromLidarAndBathymetry:
    def test_raises_without_bathymetry_source(self, tmp_path):
        csv_path = write_points_csv(tmp_path / "points.csv", [(0, 0, 11400.0), (10, 10, 11400.0)])
        dam = make_dam(terrain_sources=[{"path": str(csv_path), "kind": "lidar_points_csv"}])
        with pytest.raises(ValueError, match="no 'bathymetry_points_csv'"):
            build_terrain_from_lidar_and_bathymetry(dam)

    def test_raises_without_lidar_source(self, tmp_path):
        bathy_path = write_bathymetry_csv(tmp_path / "bathy.csv", [(0.0, 0.0, 11100.0, "BTM")])
        dam = make_dam(terrain_sources=[{"path": str(bathy_path), "kind": "bathymetry_points_csv"}])
        with pytest.raises(ValueError, match="no 'lidar_points_csv'"):
            build_terrain_from_lidar_and_bathymetry(dam)

    def test_merges_lidar_and_bathymetry_into_one_terrain(self, tmp_path):
        # LiDAR covers the dry rim (a ring around a "lake"); bathymetry fills the
        # submerged low center that LiDAR alone would leave as a hole.
        lidar_points = [(x, y, 11200.0) for x in range(0, 101, 10) for y in (0, 100)]
        lidar_points += [(x, y, 11200.0) for x in (0, 100) for y in range(0, 101, 10)]
        csv_path = write_points_csv(tmp_path / "lidar.csv", lidar_points)

        bathy_points = [(50.0, 50.0, 11150.0, "BTM"), (40.0, 60.0, 11155.0, "BTM")]
        bathy_path = write_bathymetry_csv(tmp_path / "bathy.csv", bathy_points, swapped=False)

        dam = make_dam(
            terrain_sources=[
                {"path": str(csv_path), "kind": "lidar_points_csv"},
                {"path": str(bathy_path), "kind": "bathymetry_points_csv"},
            ]
        )
        out_path = build_terrain_from_lidar_and_bathymetry(
            dam, cell_size_ft=10.0, out_dir=tmp_path / "out", swap_bathymetry_xy=False
        )

        assert out_path.exists()
        with rasterio.open(out_path) as src:
            data = src.read(1)
            # the center, informed by the bathymetric low points, should be
            # lower than the LiDAR-only rim elevation
            assert data.min() < 11200.0


class TestExtractCrestAlignment:
    def _dam_and_ridge_terrain(self, tmp_path, crest_elevation_ft=10841.0):
        from pyproj import Transformer

        lat, lon = 39.82, -105.69
        dam = make_dam(location=Location(latitude=lat, longitude=lon), crest_elevation_ft=crest_elevation_ft)

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:2232", always_xy=True)
        dam_x, dam_y = transformer.transform(lon, lat)

        size = 200
        cell_size_ft = 5.0
        origin_x = dam_x - (size / 2) * cell_size_ft
        origin_y = dam_y + (size / 2) * cell_size_ft
        transform = from_origin(origin_x, origin_y, cell_size_ft, cell_size_ft)

        # background valley below crest, with a diagonal ridge (>= crest) through the center
        elevation = np.full((size, size), crest_elevation_ft - 20.0, dtype="float32")
        for i in range(size):
            for offset in range(-2, 3):
                col = i + offset
                if 0 <= col < size:
                    elevation[i, col] = crest_elevation_ft + 5.0

        path = tmp_path / "ridge_terrain.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=size, width=size, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(elevation, 1)
        return dam, path

    def test_extracts_two_endpoints_spanning_the_ridge(self, tmp_path):
        dam, path = self._dam_and_ridge_terrain(tmp_path)

        endpoints = extract_crest_alignment(path, dam, search_radius_ft=400.0)

        assert len(endpoints) == 2
        length = math.dist(endpoints[0], endpoints[1])
        assert length > 300  # ridge should span a substantial fraction of the search window

    def test_raises_when_no_crest_height_cells_nearby(self, tmp_path):
        # ridge tops out at crest_elevation_ft + 5; ask for a crest far above that
        dam, path = self._dam_and_ridge_terrain(tmp_path, crest_elevation_ft=10841.0)
        dam = dam.model_copy(update={"crest_elevation_ft": 99999.0})

        with pytest.raises(ValueError, match="No terrain cells at or above crest"):
            extract_crest_alignment(path, dam, search_radius_ft=100.0)


class TestEstimateDownstreamChannelSlope:
    def test_recovers_known_slope_downhill_from_crest(self, tmp_path):
        size = 60
        cell_size_ft = 10.0
        known_slope = 0.02  # ft/ft
        # elevation decreases as row increases (south, i.e. -Y in world coords)
        elevation = np.fromfunction(lambda r, c: 1000.0 - r * cell_size_ft * known_slope, (size, size)).astype(
            "float32"
        )
        transform = from_origin(0, size * cell_size_ft, cell_size_ft, cell_size_ft)
        path = tmp_path / "slope.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=size, width=size, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(elevation, 1)

        # crest alignment: a horizontal line at the raster's center row, so its
        # perpendicular direction runs along the (Y-direction) slope gradient
        mid_y = transform * (size / 2, size / 2)
        crest_alignment = [
            (mid_y[0] - 100.0, mid_y[1]),
            (mid_y[0] + 100.0, mid_y[1]),
        ]

        slope = estimate_downstream_channel_slope(path, crest_alignment, sample_distance_ft=200.0, n_samples=50)

        assert slope == pytest.approx(known_slope, rel=0.05)

    def test_raises_when_alignment_runs_off_raster(self, tmp_path):
        size = 10
        cell_size_ft = 10.0
        elevation = np.full((size, size), 100.0, dtype="float32")
        transform = from_origin(0, size * cell_size_ft, cell_size_ft, cell_size_ft)
        path = tmp_path / "flat.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=size, width=size, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(elevation, 1)

        # crest alignment far outside the raster entirely
        crest_alignment = [(100_000.0, 100_000.0), (100_100.0, 100_000.0)]

        with pytest.raises(ValueError, match="Not enough valid terrain samples"):
            estimate_downstream_channel_slope(path, crest_alignment, sample_distance_ft=200.0, n_samples=50)


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
