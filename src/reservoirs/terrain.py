"""Terrain ingestion.

Primary source: the 2021 LiDAR point-cloud CSVs referenced in each dam's
`terrain_sources` (kind="lidar_points_csv") -- professional-grade elevation
survey data of the reservoir/dam vicinity, confirmed (via the survey's own
LandXML metadata) to be in NAD83(2011) / Colorado Central (ftUS). The much
larger companion contour DXFs (~80 MB) are the same surface re-expressed as
contour lines and are not re-parsed here; the raw points are the more direct
and lighter-weight source for building a terrain raster.

Fallback: for downstream reach beyond the LiDAR survey's extent,
`fetch_public_dem` pulls USGS 3DEP data via py3dep.

CRS note: LiDAR deliverables are treated here as EPSG:2232 (NAD83 /
Colorado Central, US Survey Feet) -- matching the existing FallRiver_
ClearCreek.shp on file. The survey's own metadata specifies the NAD83(2011)
realization (no direct EPSG code distinct from 2232 in the pyproj registry
lookup used here); the NAD83-vs-NAD83(2011) difference is sub-foot at this
latitude and immaterial for breach/inundation analysis, but should be
revisited if this data is ever combined with cm-level survey control.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from scipy.interpolate import griddata

from reservoirs.config import DamConfig

LIDAR_CRS = "EPSG:2232"  # NAD83 / Colorado Central (ftUS)
MILES_PER_DEGREE_LAT = 69.0


def load_lidar_points_csv(path: str | Path) -> pd.DataFrame:
    """Load a Virtual-Surveyor-style point CSV: columns P, X, Y, Z, D."""
    df = pd.read_csv(path)
    expected = {"P", "X", "Y", "Z", "D"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing expected columns {sorted(missing)}")
    return df


def load_bathymetry_points_csv(
    path: str | Path,
    swap_xy: bool = True,
    bottom_only: bool = True,
    bottom_description: str = "BTM",
) -> pd.DataFrame:
    """Load a bathymetric (submerged lakebed) survey CSV: columns id, x, y,
    z, description, with bottom-sounding points marked `description="BTM"`.

    Aerial LiDAR can't see through standing water, so it only captures a
    reservoir's dry margin above the survey-date water line -- this is the
    complementary data source for the submerged floor (see
    docs/audit_trail.md's storage-curve-gap entry). Returns columns X, Y, Z
    (uppercase, matching `load_lidar_points_csv`'s convention) for the
    bottom points only by default; pass `bottom_only=False` to keep
    non-bottom (e.g. water-surface reference) points too.

    `swap_xy=True` by default: the one bathymetric survey checked so far
    has its x/y columns swapped relative to (Easting, Northing) convention
    -- confirmed by cross-checking against the dam's known lat/lon and its
    LiDAR survey's real extent, both of which only line up after swapping
    (see docs/audit_trail.md). Verify against a specific survey's own
    metadata before assuming this holds for a different one.
    """
    df = pd.read_csv(path)
    expected = {"x", "y", "z"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing expected columns {sorted(missing)}")

    if bottom_only and "description" in df.columns:
        df = df[df["description"] == bottom_description]

    x_col, y_col = ("y", "x") if swap_xy else ("x", "y")
    return df.rename(columns={x_col: "X", y_col: "Y", "z": "Z"})[["X", "Y", "Z"]].reset_index(drop=True)


def points_to_grid(
    df: pd.DataFrame,
    cell_size_ft: float = 2.0,
    method: str = "linear",
) -> tuple[np.ndarray, rasterio.Affine]:
    """Interpolate scattered XYZ survey points onto a regular north-up grid.

    Returns (elevation_array, affine_transform) in the points' native CRS/units.
    Gaps outside the points' convex hull (where `method` interpolation is
    undefined) are filled via nearest-neighbor rather than left as NaN holes.
    """
    x, y, z = df["X"].to_numpy(), df["Y"].to_numpy(), df["Z"].to_numpy()

    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()

    n_cols = int(np.ceil((x_max - x_min) / cell_size_ft)) + 1
    n_rows = int(np.ceil((y_max - y_min) / cell_size_ft)) + 1

    grid_x, grid_y = np.meshgrid(
        x_min + np.arange(n_cols) * cell_size_ft,
        y_max - np.arange(n_rows) * cell_size_ft,  # row 0 = north = y_max
    )

    grid_z = griddata((x, y), z, (grid_x, grid_y), method=method)
    if np.isnan(grid_z).any():
        nearest = griddata((x, y), z, (grid_x, grid_y), method="nearest")
        grid_z = np.where(np.isnan(grid_z), nearest, grid_z)

    transform = from_origin(x_min, y_max, cell_size_ft, cell_size_ft)
    return grid_z.astype("float32"), transform


def write_terrain_geotiff(
    elevation: np.ndarray,
    transform: rasterio.Affine,
    out_path: str | Path,
    crs: str = LIDAR_CRS,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=elevation.shape[0],
        width=elevation.shape[1],
        count=1,
        dtype=elevation.dtype,
        crs=crs,
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(elevation, 1)
    return out_path


def dam_data_dir(dam: DamConfig) -> Path:
    return Path("dams") / dam.name.lower().replace(" ", "_") / "data"


def build_terrain_from_lidar(
    dam: DamConfig,
    cell_size_ft: float = 2.0,
    out_dir: str | Path | None = None,
) -> Path:
    """Build a terrain GeoTIFF from a dam's referenced LiDAR point-cloud CSV(s).

    Raises if the dam's config doesn't reference a `lidar_points_csv` source
    -- this is meant to be the primary path when survey data exists, not a
    silent fallback; use `fetch_public_dem` explicitly for the public-data path.
    """
    point_sources = [s for s in dam.terrain_sources if s.kind == "lidar_points_csv"]
    if not point_sources:
        raise ValueError(
            f"{dam.name}: no 'lidar_points_csv' terrain_sources configured -- "
            "use fetch_public_dem() instead, or add a source."
        )

    frames = [load_lidar_points_csv(s.path) for s in point_sources]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    elevation, transform = points_to_grid(df, cell_size_ft=cell_size_ft)

    out_dir = Path(out_dir) if out_dir is not None else dam_data_dir(dam)
    return write_terrain_geotiff(elevation, transform, out_dir / "terrain_lidar.tif")


def build_terrain_from_lidar_and_bathymetry(
    dam: DamConfig,
    cell_size_ft: float = 2.0,
    out_dir: str | Path | None = None,
    swap_bathymetry_xy: bool = True,
) -> Path:
    """Like `build_terrain_from_lidar`, but also merges in the dam's
    `bathymetry_points_csv` terrain_sources (submerged lakebed soundings)
    before gridding -- closes the gap where aerial LiDAR alone can't
    resolve a reservoir's true rim because it can't see through standing
    water (see docs/audit_trail.md).

    Raises if the dam's config has no `bathymetry_points_csv` source; use
    `build_terrain_from_lidar` directly if there isn't one.
    """
    point_sources = [s for s in dam.terrain_sources if s.kind == "lidar_points_csv"]
    if not point_sources:
        raise ValueError(
            f"{dam.name}: no 'lidar_points_csv' terrain_sources configured -- "
            "use fetch_public_dem() instead, or add a source."
        )
    bathy_sources = [s for s in dam.terrain_sources if s.kind == "bathymetry_points_csv"]
    if not bathy_sources:
        raise ValueError(
            f"{dam.name}: no 'bathymetry_points_csv' terrain_sources configured -- "
            "use build_terrain_from_lidar() if there's no bathymetric survey on file."
        )

    lidar_frames = [load_lidar_points_csv(s.path) for s in point_sources]
    lidar_df = pd.concat(lidar_frames, ignore_index=True) if len(lidar_frames) > 1 else lidar_frames[0]
    lidar_df = lidar_df[["X", "Y", "Z"]]

    bathy_frames = [load_bathymetry_points_csv(s.path, swap_xy=swap_bathymetry_xy) for s in bathy_sources]
    bathy_df = pd.concat(bathy_frames, ignore_index=True) if len(bathy_frames) > 1 else bathy_frames[0]

    combined = pd.concat([lidar_df, bathy_df], ignore_index=True)
    elevation, transform = points_to_grid(combined, cell_size_ft=cell_size_ft)

    out_dir = Path(out_dir) if out_dir is not None else dam_data_dir(dam)
    return write_terrain_geotiff(elevation, transform, out_dir / "terrain_lidar_bathy.tif")


def bounding_box_miles(latitude: float, longitude: float, buffer_mi: float) -> tuple[float, float, float, float]:
    """A rough (xmin, ymin, xmax, ymax) lon/lat box centered on a point.

    Not survey-grade -- just an area-of-interest box for DEM download, using
    a simple degrees-per-mile approximation (good to a few percent at these
    latitudes, which is more than sufficient for bounding a download extent).
    """
    dlat = buffer_mi / MILES_PER_DEGREE_LAT
    miles_per_degree_lon = MILES_PER_DEGREE_LAT * math.cos(math.radians(latitude))
    dlon = buffer_mi / miles_per_degree_lon
    return (longitude - dlon, latitude - dlat, longitude + dlon, latitude + dlat)


def fetch_public_dem(
    dam: DamConfig,
    buffer_mi: float = 3.0,
    resolution_m: int = 10,
    out_dir: str | Path | None = None,
):
    """Fetch a public USGS 3DEP DEM for the area around a dam via py3dep.

    Fallback for downstream reach not covered by an existing LiDAR survey.
    Requires network access -- not covered by unit tests (see
    tests/test_terrain.py for what *is* tested: the pure-Python bbox math
    and the LiDAR grid-interpolation path, which need no network).
    """
    import py3dep  # deferred: heavy optional dependency, only needed here

    bbox = bounding_box_miles(dam.location.latitude, dam.location.longitude, buffer_mi)
    dem = py3dep.get_dem(bbox, resolution=resolution_m, crs=4326)

    out_dir = Path(out_dir) if out_dir is not None else dam_data_dir(dam)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"terrain_3dep_{resolution_m}m.tif"
    dem.rio.to_raster(out_path)
    return out_path


def extract_crest_alignment(
    terrain_path: str | Path,
    dam: DamConfig,
    search_radius_ft: float = 600.0,
) -> list[tuple[float, float]]:
    """Extract a candidate dam-crest alignment polyline from terrain, for
    `ras_project.create_breach_structure`'s `connection_coords`.

    An intact (unbreached) embankment's own top surface should sit at or
    above its design crest elevation, distinguishing it from the
    surrounding valley -- so this finds the connected component of cells
    with `elevation >= dam.crest_elevation_ft` nearest the dam's `dam.yaml`
    location, then fits a line through it via PCA and returns that line's
    two endpoints. Confirmed visually against Fall River Reservoir's real
    terrain (a distinct ~30-40 ft wide linear ridge, not just an incidental
    contour crossing) before being written as a general-purpose function --
    see docs/audit_trail.md.

    This is a heuristic over survey terrain, not a substitute for as-built
    drawings -- review the result (e.g. plot it over the terrain) before
    using it in `create_breach_structure`. Raises if no cell at/above crest
    elevation exists within `search_radius_ft` of the dam's location.
    """
    from pyproj import Transformer
    from scipy import ndimage

    with rasterio.open(terrain_path) as src:
        elevation = src.read(1)
        transform = src.transform
        crs = src.crs

    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    dam_x, dam_y = transformer.transform(dam.location.longitude, dam.location.latitude)
    dam_col, dam_row = ~transform * (dam_x, dam_y)
    dam_row, dam_col = int(round(dam_row)), int(round(dam_col))

    cell_size_ft = abs(transform.a)
    half_cells = int(search_radius_ft / cell_size_ft)
    r0, r1 = max(0, dam_row - half_cells), min(elevation.shape[0], dam_row + half_cells)
    c0, c1 = max(0, dam_col - half_cells), min(elevation.shape[1], dam_col + half_cells)

    mask = elevation[r0:r1, c0:c1] >= dam.crest_elevation_ft
    labeled, n_components = ndimage.label(mask)
    if n_components == 0:
        raise ValueError(
            f"No terrain cells at or above crest elevation ({dam.crest_elevation_ft} ft) within "
            f"{search_radius_ft} ft of {dam.name}'s dam.yaml location -- widen search_radius_ft, "
            "or check the location/crest elevation."
        )

    local_row, local_col = dam_row - r0, dam_col - c0
    component_label = labeled[local_row, local_col] if mask[local_row, local_col] else 0
    if component_label == 0:
        ys, xs = np.where(labeled > 0)
        nearest = ((ys - local_row) ** 2 + (xs - local_col) ** 2).argmin()
        component_label = labeled[ys[nearest], xs[nearest]]

    ys, xs = np.where(labeled == component_label)
    coords = np.column_stack([xs, ys]).astype(float)
    centroid = coords.mean(axis=0)
    centered = coords - centroid

    eigvals, eigvecs = np.linalg.eigh(np.cov(centered.T))
    principal_axis = eigvecs[:, np.argmax(eigvals)]
    projections = centered @ principal_axis

    endpoints_local = [centroid + principal_axis * projections.min(), centroid + principal_axis * projections.max()]
    return [transform * (c0 + x, r0 + y) for x, y in endpoints_local]


def estimate_downstream_channel_slope(
    terrain_path: str | Path,
    crest_alignment: list[tuple[float, float]],
    sample_distance_ft: float = 2000.0,
    n_samples: int = 100,
) -> float:
    """First-pass estimate of the downstream channel's bed slope (ft/ft),
    for `ras_project.configure_initial_and_boundary_conditions`'s
    `downstream_friction_slope` -- HEC-RAS's normal-depth boundary
    approximates the friction slope with the channel bed slope.

    Samples terrain elevation along a line perpendicular to
    `crest_alignment` (a dam-crest polyline, e.g. from
    `extract_crest_alignment`), extending in whichever perpendicular
    direction has lower average elevation (downstream), and fits a linear
    trend to elevation vs. distance. This is a coarse, terrain-only
    starting point -- review against actual channel/valley conditions
    (tailwater effects, channel roughness, downstream constrictions) before
    trusting it; it does not know about any of those.
    """
    with rasterio.open(terrain_path) as src:
        elevation = src.read(1)
        transform = src.transform

    (x1, y1), (x2, y2) = crest_alignment[0], crest_alignment[-1]
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    perp = (-dy / length, dx / length)

    def sample_line(direction_sign: float) -> np.ndarray:
        distances = np.linspace(0, sample_distance_ft, n_samples)
        xs = mid_x + perp[0] * direction_sign * distances
        ys = mid_y + perp[1] * direction_sign * distances
        cols, rows = ~transform * (xs, ys)
        rows, cols = np.round(rows).astype(int), np.round(cols).astype(int)
        valid = (rows >= 0) & (rows < elevation.shape[0]) & (cols >= 0) & (cols < elevation.shape[1])
        return distances[valid], elevation[rows[valid], cols[valid]]

    dist_pos, elev_pos = sample_line(1.0)
    dist_neg, elev_neg = sample_line(-1.0)

    if len(elev_pos) < 2 and len(elev_neg) < 2:
        raise ValueError("Not enough valid terrain samples along the downstream direction to estimate a slope.")

    mean_pos = np.mean(elev_pos) if len(elev_pos) > 0 else np.inf
    mean_neg = np.mean(elev_neg) if len(elev_neg) > 0 else np.inf
    distances, elevations = (dist_pos, elev_pos) if mean_pos < mean_neg else (dist_neg, elev_neg)

    valid = ~np.isnan(elevations)
    if valid.sum() < 2:
        raise ValueError("Not enough valid terrain samples along the downstream direction to estimate a slope.")

    slope, _ = np.polyfit(distances[valid], elevations[valid], 1)
    return abs(float(slope))
