"""HEC-RAS results post-processing: HDF max-water-surface results ->
depth grid -> inundation extent (GeoTIFF + polygon), plus plausibility
checks per docs/methodology.md's verification approach.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union


def load_max_ws_from_hdf(hdf_path: str | Path):
    """Read per-mesh-cell maximum water-surface elevation from a computed
    HEC-RAS plan's HDF results.

    Integration-level -- requires a real, computed HEC-RAS plan HDF (which
    in turn requires the manual embankment-structure step documented in
    ras_project.py/methodology.md), so this isn't covered by unit tests.
    The exact column name holding the WSE value should be confirmed
    against real output before relying on a hardcoded name; callers should
    inspect the returned GeoDataFrame's columns explicitly rather than
    assume one.
    """
    import ras_commander as rc

    return rc.HdfResultsMesh.get_mesh_max_ws(Path(hdf_path))


def rasterize_max_ws(
    max_ws_gdf: gpd.GeoDataFrame,
    wse_column: str,
    terrain_path: str | Path,
) -> np.ndarray:
    """Rasterize per-cell max water-surface elevations onto the same grid
    (CRS, transform, shape) as a terrain GeoTIFF. Cells with no mesh-cell
    coverage are NaN.
    """
    with rasterio.open(terrain_path) as src:
        transform = src.transform
        shape_ = (src.height, src.width)
        dst_crs = src.crs.to_string()  # pyproj/geopandas-friendly string, not a rasterio.crs.CRS object

    gdf = max_ws_gdf.to_crs(dst_crs) if max_ws_gdf.crs is not None and max_ws_gdf.crs != dst_crs else max_ws_gdf

    shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf[wse_column]))
    raster = features.rasterize(
        shapes, out_shape=shape_, transform=transform, fill=np.nan, dtype="float64"
    )
    return raster


def compute_depth_grid(max_ws: np.ndarray, terrain: np.ndarray) -> np.ndarray:
    """Depth = max_ws - terrain, floored at 0, NaN where either input is NaN."""
    depth = max_ws - terrain
    depth = np.where(np.isnan(max_ws) | np.isnan(terrain), np.nan, depth)
    return np.where(depth < 0, 0.0, depth)


def extract_inundation_polygon(
    depth: np.ndarray,
    transform: rasterio.Affine,
    crs,
    depth_threshold_ft: float = 0.1,
) -> gpd.GeoDataFrame:
    """Threshold a depth grid and dissolve the flooded cells into inundation
    extent polygon(s).
    """
    flooded = (depth > depth_threshold_ft) & ~np.isnan(depth)
    mask = flooded.astype("uint8")

    polygons = [
        shape(geom)
        for geom, value in features.shapes(mask, mask=flooded, transform=transform)
        if value == 1
    ]
    if not polygons:
        return gpd.GeoDataFrame({"geometry": []}, crs=crs)

    dissolved = unary_union(polygons).buffer(0)
    geoms = list(dissolved.geoms) if hasattr(dissolved, "geoms") else [dissolved]
    return gpd.GeoDataFrame({"geometry": geoms}, crs=crs)


def write_depth_geotiff(depth: np.ndarray, transform: rasterio.Affine, out_path: str | Path, crs) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, "w", driver="GTiff", height=depth.shape[0], width=depth.shape[1],
        count=1, dtype="float32", crs=crs, transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(depth.astype("float32"), 1)
    return out_path


def write_inundation_shapefile(gdf: gpd.GeoDataFrame, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path)
    return out_path


def check_downstream_connectivity(depth: np.ndarray, seed_rc: tuple[int, int]) -> list[str]:
    """Flag disconnected 'islands' of inundation away from the main flooded
    area seeded at the dam/breach location -- per methodology.md's
    plausibility checks, a real breach flood should be one connected body
    of water reaching downstream, not scattered disconnected puddles.
    """
    flooded = (depth > 0) & ~np.isnan(depth)
    if not flooded.any():
        return ["No inundation extent was produced at all -- depth grid is entirely dry/NaN."]

    labeled, n_features = ndimage.label(flooded)
    seed_label = labeled[seed_rc]
    if seed_label == 0:
        return [
            "The seed location (dam/breach) is not itself flooded in the depth grid -- "
            "check the seed coordinates and the HEC-RAS results."
        ]

    main_component_size = (labeled == seed_label).sum()
    total_flooded = flooded.sum()
    disconnected_fraction = 1 - (main_component_size / total_flooded)

    if disconnected_fraction > 0.05:
        return [
            f"{disconnected_fraction:.0%} of the flooded area is disconnected from the main "
            f"breach-fed inundation body ({n_features} total components) -- check for terrain "
            "artifacts, mesh gaps, or separate low spots being wrongly counted as inundated."
        ]
    return []


def check_max_depth_plausible(depth: np.ndarray, dam_height_ft: float, tolerance_factor: float = 1.5) -> list[str]:
    """Flag a max depth that implausibly exceeds the dam's own height --
    a real breach flood's depth near the dam shouldn't wildly exceed the
    height of water that could ever have been impounded.
    """
    valid = depth[~np.isnan(depth)]
    if valid.size == 0:
        return []
    max_depth = float(valid.max())
    limit = dam_height_ft * tolerance_factor
    if max_depth > limit:
        return [
            f"Maximum computed depth ({max_depth:.1f} ft) exceeds {tolerance_factor}x the dam "
            f"height ({dam_height_ft:.1f} ft, limit {limit:.1f} ft) -- check terrain data quality, "
            "mesh resolution, and boundary conditions before trusting this result."
        ]
    return []
