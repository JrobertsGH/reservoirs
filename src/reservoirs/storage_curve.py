"""Elevation-area-storage curve, derived directly from terrain.

No separately-digitized reservoir footprint polygon is required: the pool
at a given elevation is taken to be the connected region of terrain at or
below that elevation, reachable from the reservoir's deepest point (the
seed). This is the flood-fill / "bathtub" approach -- appropriate here
because it's feeding breach-parameter/HEC-RAS setup, not itself the
breach-routing hydraulics (that's `ras_project.py`'s job, using the same
terrain properly in 2D).

Cells whose flooded region touches the terrain raster's edge at a given
elevation are flagged: it means the survey extent may be too small to
capture the true pool boundary at that elevation, and the reported area/
storage for that elevation (and above) is a lower bound, not a fact.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage


def _seed_from_min_elevation(elevation: np.ndarray) -> tuple[int, int]:
    flat_index = np.nanargmin(elevation)
    return np.unravel_index(flat_index, elevation.shape)


def _seed_from_xy(elevation: np.ndarray, transform: rasterio.Affine, x: float, y: float) -> tuple[int, int]:
    col, row = ~transform * (x, y)
    row, col = int(round(row)), int(round(col))
    if not (0 <= row < elevation.shape[0] and 0 <= col < elevation.shape[1]):
        raise ValueError(f"Seed point ({x}, {y}) falls outside the terrain raster extent.")
    return row, col


def compute_elevation_area_storage_curve(
    terrain_path: str | Path,
    seed_xy: tuple[float, float] | None = None,
    elevation_step_ft: float = 1.0,
    max_elevation_ft: float | None = None,
) -> pd.DataFrame:
    """Compute an elevation-area-storage table from a terrain GeoTIFF.

    Returns a DataFrame with columns: elevation_ft, area_ac, storage_ac_ft,
    touches_boundary (bool -- True means the flooded extent at this
    elevation reaches the raster edge, so area/storage are a lower bound).
    """
    with rasterio.open(terrain_path) as src:
        elevation = src.read(1)
        cell_area_ft2 = abs(src.transform.a * src.transform.e)
        nodata = src.nodata
        transform = src.transform

    valid = ~np.isnan(elevation) if nodata is None or np.isnan(nodata) else elevation != nodata
    elevation = np.where(valid, elevation, np.nan)

    seed = (
        _seed_from_xy(elevation, transform, *seed_xy) if seed_xy is not None else _seed_from_min_elevation(elevation)
    )

    min_elev = float(np.nanmin(elevation))
    max_elev = max_elevation_ft if max_elevation_ft is not None else float(np.nanmax(elevation))

    elevations = np.arange(min_elev, max_elev + elevation_step_ft, elevation_step_ft)
    areas_ac = np.zeros_like(elevations)
    touches_boundary = np.zeros(len(elevations), dtype=bool)

    for i, e in enumerate(elevations):
        flooded_mask = valid & (elevation <= e)
        labeled, _ = ndimage.label(flooded_mask)
        basin_label = labeled[seed]
        if basin_label == 0:
            continue  # seed itself not yet flooded at this elevation (shouldn't happen above min_elev)
        basin = labeled == basin_label
        areas_ac[i] = basin.sum() * cell_area_ft2 / 43560.0
        touches_boundary[i] = bool(
            basin[0, :].any() or basin[-1, :].any() or basin[:, 0].any() or basin[:, -1].any()
        )

    storage_ac_ft = np.concatenate([[0.0], np.cumsum(
        (areas_ac[:-1] + areas_ac[1:]) / 2.0 * elevation_step_ft
    )])

    return pd.DataFrame(
        {
            "elevation_ft": elevations,
            "area_ac": areas_ac,
            "storage_ac_ft": storage_ac_ft,
            "touches_boundary": touches_boundary,
        }
    )


def storage_at_elevation(curve: pd.DataFrame, elevation_ft: float) -> float:
    return float(np.interp(elevation_ft, curve["elevation_ft"], curve["storage_ac_ft"]))


def elevation_at_storage(curve: pd.DataFrame, storage_ac_ft: float) -> float:
    """Inverse lookup -- assumes storage increases monotonically with elevation,
    which holds for any real basin (more water needs a higher pool)."""
    return float(np.interp(storage_ac_ft, curve["storage_ac_ft"], curve["elevation_ft"]))


def compare_to_reported_storage(
    curve: pd.DataFrame, elevation_ft: float, reported_storage_ac_ft: float, tolerance_pct: float = 20.0
) -> list[str]:
    """Cross-check the DEM-derived curve against a dam's published storage
    figure at a given pool elevation. Returns warnings rather than raising --
    a mismatch means the terrain survey and the published figure disagree,
    which is exactly the kind of thing a PE should look into, not something
    this function should paper over.
    """
    predicted = storage_at_elevation(curve, elevation_ft)
    if reported_storage_ac_ft == 0:
        return []
    pct_diff = abs(predicted - reported_storage_ac_ft) / reported_storage_ac_ft * 100
    if pct_diff > tolerance_pct:
        return [
            f"DEM-derived storage at {elevation_ft} ft ({predicted:.1f} ac-ft) differs from the "
            f"reported figure ({reported_storage_ac_ft:.1f} ac-ft) by {pct_diff:.0f}%, exceeding the "
            f"{tolerance_pct}% tolerance -- check the elevation used, the terrain source's coverage/"
            "accuracy, and the reported figure's source before trusting either."
        ]
    return []
