"""Downstream structures / population-at-risk (PAR) overlay.

Per methodology.md's "Downstream structures / population-at-risk (PAR)
overlay included" decision and DWR Rule 16.1.5.1 (inundation maps should
show "urban and rural impacts"): this module identifies which downstream
buildings fall inside a computed inundation extent and produces a rough,
explicitly preliminary PAR estimate from a structure count -- a planning-
level figure, not a substitute for a door-to-door PAR study.

`fetch_structures_osm` is the one network-dependent function (OpenStreetMap
building footprints via osmnx) and isn't covered by unit tests, same
approach as terrain.py's `fetch_public_dem` and manning_lookup.py's
`fetch_manning_n_grid`. Everything else here is pure geometry/arithmetic
and is unit tested against synthetic structures.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from reservoirs.config import DamConfig
from reservoirs.terrain import bounding_box_miles

DEFAULT_PERSONS_PER_STRUCTURE = 2.5


def fetch_structures_osm(dam: DamConfig, buffer_mi: float = 3.0) -> gpd.GeoDataFrame:
    """Fetch OpenStreetMap building footprints in a box around a dam.

    Requires network access -- not covered by unit tests (see
    tests/test_structures.py for what *is* tested: the pure spatial-filter,
    centroid, and PAR-estimate logic, which need no network). `buffer_mi`
    should cover the downstream routing corridor of interest, not just the
    dam vicinity -- callers analyzing a specific breach should size it to
    the actual inundation extent's bounding box.
    """
    import osmnx as ox

    bbox = bounding_box_miles(dam.location.latitude, dam.location.longitude, buffer_mi)
    west, south, east, north = bbox
    return ox.features_from_bbox((west, south, east, north), tags={"building": True})


def structures_within_inundation(
    structures_gdf: gpd.GeoDataFrame,
    inundation_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Filter structures to those whose footprint intersects the inundation extent.

    Reprojects `structures_gdf` to the inundation layer's CRS if they differ.
    Returns an empty GeoDataFrame (same schema, inundation's CRS) when either
    input is empty, rather than raising.
    """
    if len(structures_gdf) == 0 or len(inundation_gdf) == 0:
        return gpd.GeoDataFrame({"geometry": []}, crs=inundation_gdf.crs)

    if structures_gdf.crs != inundation_gdf.crs:
        structures_gdf = structures_gdf.to_crs(inundation_gdf.crs)

    extent = inundation_gdf.union_all()
    return structures_gdf[structures_gdf.intersects(extent)]


def structures_to_points(structures_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reduce structure footprints (polygons or points) to representative
    points, for map overlay -- `mapping.py`'s `structures_gdf` parameter
    plots point markers, not filled building outlines.
    """
    if len(structures_gdf) == 0:
        return structures_gdf.set_geometry(structures_gdf.geometry)

    points_gdf = structures_gdf.copy()
    points_gdf["geometry"] = structures_gdf.geometry.centroid
    return points_gdf


def estimate_population_at_risk(
    structures_gdf: gpd.GeoDataFrame,
    persons_per_structure: float = DEFAULT_PERSONS_PER_STRUCTURE,
) -> dict:
    """Rough planning-level PAR estimate from a structure count.

    `persons_per_structure` defaults to a generic average-household-size
    figure -- a coarse placeholder, not a census-block-group-level PAR
    study. Always report alongside the structure count itself (returned
    here) so a PE reviewer can see the assumption, not just the output.
    """
    structure_count = len(structures_gdf)
    return {
        "structure_count": structure_count,
        "persons_per_structure": persons_per_structure,
        "estimated_par": round(structure_count * persons_per_structure),
    }


def write_structures_shapefile(gdf: gpd.GeoDataFrame, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path)
    return out_path
