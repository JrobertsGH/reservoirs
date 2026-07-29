"""NLCD-derived Manning's n (overland roughness).

Uses `pygeohydro`'s `nlcd_bygeom` + `overland_roughness` -- the latter
already implements a standard NLCD-land-cover-class-to-Manning's-n
crosswalk, so this module doesn't reinvent one.

Scope note: this module fetches NLCD, converts it to a roughness raster,
and can resample that raster onto the same grid as a terrain GeoTIFF from
`terrain.py`. It does **not** yet wire that roughness data into HEC-RAS's
own Base Manning's n table / land-cover raster mechanism
(`ras_commander.GeomLandCover.set_base_mannings_n` /
`set_mannings_region_polygons`) -- that wiring needs to be verified against
a real HEC-RAS geometry file's expected table schema before being
automated, which hasn't been done yet. Until then, `ras_project.py`'s
`configure_2d_flow_area` uses a single uniform Manning's n constant; this
module's output is a reference layer for that future wiring, and for
manual QA of the roughness assumption.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from reservoirs.config import DamConfig
from reservoirs.terrain import bounding_box_miles


def fetch_manning_n_grid(dam: DamConfig, buffer_mi: float = 1.0, year: int = 2021, resolution_m: int = 30):
    """Fetch NLCD land cover around a dam and convert to Manning's n.

    Requires network access -- not covered by unit tests (see
    tests/test_manning_lookup.py for what *is* tested: the pure
    resampling/reprojection logic, which needs no network).
    """
    import geopandas as gpd
    import pygeohydro as gh
    from shapely.geometry import box

    bbox = bounding_box_miles(dam.location.latitude, dam.location.longitude, buffer_mi)
    gdf = gpd.GeoDataFrame(geometry=[box(*bbox)], crs=4326)

    result = gh.nlcd_bygeom(gdf, resolution=resolution_m, years={"cover": year}, crs=4326)
    ds = result[next(iter(result))]
    cover_da = next(iter(ds.data_vars.values()))
    return gh.overland_roughness(cover_da)


def write_manning_n_geotiff(roughness_da, out_path: str | Path, crs: str = "EPSG:4326") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if roughness_da.rio.crs is None:
        roughness_da = roughness_da.rio.write_crs(crs)
    roughness_da.rio.to_raster(out_path)
    return out_path


def resample_manning_n_to_terrain(roughness_da, terrain_path: str | Path) -> np.ndarray:
    """Reproject/resample a Manning's n DataArray onto the same grid
    (CRS, transform, shape) as a terrain GeoTIFF, for direct cell-by-cell
    use alongside the terrain.
    """
    with rasterio.open(terrain_path) as src:
        dst_crs = src.crs
        dst_transform = src.transform
        dst_shape = (src.height, src.width)

    if roughness_da.rio.crs is None:
        roughness_da = roughness_da.rio.write_crs("EPSG:4326")

    reprojected = roughness_da.rio.reproject(dst_crs, shape=dst_shape, transform=dst_transform)
    return reprojected.values
