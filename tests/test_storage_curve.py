import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from reservoirs.storage_curve import (
    compare_to_reported_storage,
    compute_elevation_area_storage_curve,
    elevation_at_storage,
    storage_at_elevation,
)


def write_bathtub_raster(path, floor_elev=100.0, wall_elev=200.0, floor_size=10, border=5, cell_size_ft=10.0):
    """A flat-bottomed basin: a floor_size x floor_size square of `floor_elev`
    surrounded by a `border`-cell-wide ring of `wall_elev`, so the flooded
    area is exactly constant (floor_size**2 cells) for any elevation between
    floor_elev and wall_elev -- giving an exact, hand-computable volume.
    """
    n = floor_size + 2 * border
    elevation = np.full((n, n), wall_elev, dtype="float32")
    elevation[border : border + floor_size, border : border + floor_size] = floor_elev
    transform = from_origin(0, n * cell_size_ft, cell_size_ft, cell_size_ft)
    with rasterio.open(
        path, "w", driver="GTiff", height=n, width=n, count=1,
        dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(elevation, 1)
    return path, transform, cell_size_ft


def write_edge_touching_raster(path, floor_elev=100.0, size=10, cell_size_ft=10.0):
    """A floor that extends all the way to the raster edge -- flooding
    touches the boundary immediately, even at the minimum elevation."""
    elevation = np.full((size, size), floor_elev, dtype="float32")
    transform = from_origin(0, size * cell_size_ft, cell_size_ft, cell_size_ft)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(elevation, 1)
    return path


class TestComputeElevationAreaStorageCurve:
    def test_constant_area_bathtub_gives_exact_linear_storage(self, tmp_path):
        path, _, cell_size_ft = write_bathtub_raster(tmp_path / "bathtub.tif")
        cell_area_ac = (cell_size_ft**2) / 43560.0
        expected_area_ac = 10 * 10 * cell_area_ac  # floor_size=10

        curve = compute_elevation_area_storage_curve(path, elevation_step_ft=1.0, max_elevation_ft=150.0)

        # Area should be constant (== the floor footprint) across the whole
        # flooded range, since walls are far above the tested elevations.
        nonzero_area = curve[curve["elevation_ft"] > curve["elevation_ft"].min()]
        assert np.allclose(nonzero_area["area_ac"], expected_area_ac, rtol=1e-6)

        # storage(150) should equal area * height exactly (trapezoid of a
        # constant function is exact).
        expected_storage = expected_area_ac * (150.0 - 100.0)
        final_storage = curve.iloc[-1]["storage_ac_ft"]
        assert np.isclose(final_storage, expected_storage, rtol=1e-6)

    def test_storage_starts_at_zero(self, tmp_path):
        path, _, _ = write_bathtub_raster(tmp_path / "bathtub.tif")
        curve = compute_elevation_area_storage_curve(path, elevation_step_ft=1.0, max_elevation_ft=150.0)
        assert curve.iloc[0]["storage_ac_ft"] == 0.0

    def test_storage_is_monotonically_nondecreasing(self, tmp_path):
        path, _, _ = write_bathtub_raster(tmp_path / "bathtub.tif")
        curve = compute_elevation_area_storage_curve(path, elevation_step_ft=1.0, max_elevation_ft=150.0)
        assert (curve["storage_ac_ft"].diff().dropna() >= 0).all()

    def test_walled_basin_never_touches_boundary_below_wall_height(self, tmp_path):
        path, _, _ = write_bathtub_raster(tmp_path / "bathtub.tif", wall_elev=200.0)
        curve = compute_elevation_area_storage_curve(path, elevation_step_ft=1.0, max_elevation_ft=150.0)
        assert not curve["touches_boundary"].any()

    def test_edge_touching_basin_flags_boundary_immediately(self, tmp_path):
        path = write_edge_touching_raster(tmp_path / "edge.tif")
        curve = compute_elevation_area_storage_curve(path, elevation_step_ft=1.0, max_elevation_ft=110.0)
        assert curve["touches_boundary"].all()

    def test_seed_xy_selects_correct_basin(self, tmp_path):
        # Two separate flat-bottom basins in one raster at different elevations;
        # seeding at one should only flood that basin, not both.
        n = 30
        cell_size_ft = 10.0
        elevation = np.full((n, n), 300.0, dtype="float32")
        elevation[2:8, 2:8] = 100.0   # basin A, top-left
        elevation[20:26, 20:26] = 150.0  # basin B, bottom-right, higher floor
        transform = from_origin(0, n * cell_size_ft, cell_size_ft, cell_size_ft)
        path = tmp_path / "two_basins.tif"
        with rasterio.open(
            path, "w", driver="GTiff", height=n, width=n, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(elevation, 1)

        # Seed in basin A's footprint (map coords: col*cell_size, row from top)
        seed_x = 4 * cell_size_ft + cell_size_ft / 2
        seed_y = n * cell_size_ft - (4 * cell_size_ft + cell_size_ft / 2)
        curve = compute_elevation_area_storage_curve(
            path, seed_xy=(seed_x, seed_y), elevation_step_ft=1.0, max_elevation_ft=140.0
        )
        # Only basin A (36 cells) should ever be counted -- basin B's floor (150) is
        # above max_elevation_ft, so it should never appear in this curve at all.
        expected_area_ac = 36 * (cell_size_ft**2) / 43560.0
        nonzero = curve[curve["area_ac"] > 0]
        assert np.allclose(nonzero["area_ac"], expected_area_ac, rtol=1e-6)


class TestLookups:
    def test_storage_at_elevation_interpolates(self):
        curve = pd.DataFrame(
            {"elevation_ft": [100, 110, 120], "area_ac": [1, 1, 1], "storage_ac_ft": [0, 10, 20]}
        )
        assert storage_at_elevation(curve, 115) == pytest.approx(15.0)

    def test_elevation_at_storage_is_inverse(self):
        curve = pd.DataFrame(
            {"elevation_ft": [100, 110, 120], "area_ac": [1, 1, 1], "storage_ac_ft": [0, 10, 20]}
        )
        assert elevation_at_storage(curve, 15) == pytest.approx(115.0)


class TestCompareToReportedStorage:
    def test_no_warning_within_tolerance(self):
        curve = pd.DataFrame(
            {"elevation_ft": [100, 110], "area_ac": [10, 10], "storage_ac_ft": [0, 100]}
        )
        warnings = compare_to_reported_storage(curve, elevation_ft=110, reported_storage_ac_ft=105, tolerance_pct=20)
        assert warnings == []

    def test_warns_when_outside_tolerance(self):
        curve = pd.DataFrame(
            {"elevation_ft": [100, 110], "area_ac": [10, 10], "storage_ac_ft": [0, 100]}
        )
        warnings = compare_to_reported_storage(curve, elevation_ft=110, reported_storage_ac_ft=500, tolerance_pct=20)
        assert len(warnings) == 1
        assert "differs from the reported figure" in warnings[0]
