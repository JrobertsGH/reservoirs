"""Tests for the pure-Python parts of manning_lookup.py (using a synthetic
roughness DataArray instead of a live NLCD fetch). fetch_manning_n_grid
itself requires network access and is not covered here -- same approach as
terrain.py's fetch_public_dem.
"""

import numpy as np
import rasterio
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr
from rasterio.transform import from_origin

from reservoirs.manning_lookup import resample_manning_n_to_terrain, write_manning_n_geotiff


def make_roughness_da(value=0.035, size=10, crs="EPSG:4326", assign_crs=True):
    # Real-world extent around Fall River Reservoir, so it spatially overlaps
    # the synthetic terrain grid below (which uses real Colorado State Plane
    # coordinates near the same location) -- a raw (0, 0) origin in either
    # CRS would put the two rasters thousands of miles apart.
    data = np.full((size, size), value, dtype="float64")
    x = np.linspace(-105.70, -105.68, size)
    y = np.linspace(39.83, 39.81, size)
    da = xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"], name="roughness")
    return da.rio.write_crs(crs) if assign_crs else da


def make_terrain_geotiff(path, size=10, cell_size_ft=200.0, crs="EPSG:2232"):
    # Origin near the real Fall River Reservoir vicinity in Colorado Central
    # State Plane (ftUS), not (0, 0) -- see make_roughness_da's note.
    elevation = np.zeros((size, size), dtype="float32")
    transform = from_origin(2_941_000.0, 1_724_500.0, cell_size_ft, cell_size_ft)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs=crs, transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(elevation, 1)
    return path


class TestWriteManningNGeotiff:
    def test_writes_readable_geotiff(self, tmp_path):
        da = make_roughness_da(value=0.05)
        out_path = write_manning_n_geotiff(da, tmp_path / "sub" / "manning_n.tif")
        assert out_path.exists()
        with rasterio.open(out_path) as src:
            data = src.read(1)
            assert np.allclose(data, 0.05)

    def test_assigns_crs_when_missing(self, tmp_path):
        da = make_roughness_da(assign_crs=False)
        assert da.rio.crs is None  # sanity check on the test setup itself
        out_path = write_manning_n_geotiff(da, tmp_path / "manning_n.tif", crs="EPSG:4326")
        with rasterio.open(out_path) as src:
            assert src.crs is not None


class TestResampleManningNToTerrain:
    def test_output_shape_matches_terrain_grid(self, tmp_path):
        da = make_roughness_da(value=0.04, size=20)
        terrain_path = make_terrain_geotiff(tmp_path / "terrain.tif", size=15)

        resampled = resample_manning_n_to_terrain(da, terrain_path)

        with rasterio.open(terrain_path) as src:
            assert resampled.shape == (src.height, src.width)

    def test_constant_roughness_stays_constant_after_resample(self, tmp_path):
        da = make_roughness_da(value=0.06, size=20)
        terrain_path = make_terrain_geotiff(tmp_path / "terrain.tif", size=15)

        resampled = resample_manning_n_to_terrain(da, terrain_path)

        valid = resampled[~np.isnan(resampled)]
        assert valid.size > 0
        assert np.allclose(valid, 0.06, atol=1e-6)
