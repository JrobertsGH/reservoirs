"""HEC-RAS 2D unsteady project automation via ras-commander.

**Fully automatable, including the dam embankment itself.** An earlier
version of this module assumed the breachable structure representing the
dam embankment had to be created by hand in the HEC-RAS GUI, based on
`GeomInlineWeir` being read-only in the installed ras-commander 0.99.1
(`get_profile`/`get_weirs`/`get_gates` only, no create/set methods -- that
part is still true). That assumption was wrong: `GeomInlineWeir` is the
1D river-station inline-structure class, not the one this project needs.
The actual class for a Storage-Area-to-2D-Area breach connection is
`GeomLateral`, and in the installed version it has full read/write support
(`set_connection`, `set_connection_profile`, `set_connection_gates`,
`delete_connection`, verified against production 2D models per its own
docstrings) -- confirmed by inspecting the installed package directly, not
assumed. `create_reservoir_storage_area` and `create_breach_structure`
below use it, so the whole chain from `dam.yaml` to a computed HEC-RAS plan
is scriptable with no GUI step.

Pipeline once a terrain GeoTIFF and a computed `BreachEstimate` exist:
`create_dam_project` -> `attach_terrain` -> `configure_2d_flow_area` (the
downstream 2D flow area) -> `create_reservoir_storage_area` (the reservoir
pool, with its `storage_curve.py`-derived elevation-volume curve) ->
`create_breach_structure` (the dam embankment itself, as a Connection
between the two) -> `apply_breach_parameters` (wires the computed
`BreachEstimate` into that Connection's breach block) ->
`configure_initial_and_boundary_conditions` -> `generate_mesh` ->
`run_plan`.

This mirrors (and resolves) the reservoir-footprint-digitization concern
already flagged in docs/methodology.md: `storage_curve.py`'s flood-fill
approach made that one unnecessary too, by finding a real write API instead
of assuming a manual step. There's no lower-level ras-commander method for
creating a plain (non-2D) storage area, so `create_reservoir_storage_area`
writes that block's HEC-RAS text format directly -- deliberately not
reusing `GeomStorage`'s own underscore-prefixed helpers, since those aren't
a stable public API to depend on.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import rasterio
import ras_commander as rc
from ras_commander.geom.GeomParser import GeomParser

from reservoirs.breach_params import BreachEstimate
from reservoirs.config import DamConfig


def breach_structure_name(dam: DamConfig) -> str:
    return f"{dam.name} Dam"


MAX_RAS_NAME_LENGTH = 16


def ras_connection_name(dam: DamConfig) -> str:
    """A HEC-RAS-safe (<=16 char) identifier for the dam's breach Connection.

    Deliberately distinct from `breach_structure_name` (a human-readable
    label, e.g. "Fall River Reservoir Dam" -- 24 characters). The installed
    ras-commander's `GeomLateral.set_connection` silently fixed-width-
    truncates Connection names and Connection Up/Dn SA references to 16
    characters (found by writing a real connection: "Fall River Reservoir
    Dam" got silently mangled to "Fall River Reser", which then failed to
    round-trip against its own untruncated Storage Area name) -- so the
    name actually written into the geometry file needs to already fit,
    not just happen to.
    """
    return f"Dam {dam.state_dam_id}"


def _require_ras_name_length(name: str, field: str) -> None:
    if len(name) > MAX_RAS_NAME_LENGTH:
        raise ValueError(
            f"{field}={name!r} is {len(name)} characters; HEC-RAS's Connection/"
            f"Storage-Area name fields are fixed-width and silently truncate past "
            f"{MAX_RAS_NAME_LENGTH} (see ras_connection_name's docstring) -- shorten it."
        )


def _polygon_centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _format_storage_area_surface_line(coords: list[tuple[float, float]]) -> list[str]:
    """16-char fixed-width XY pairs, 4 values (2 coordinate pairs) per line --
    the same format GeomStorage reads for `Storage Area Surface Line=` data.
    """
    flat = [v for xy in coords for v in xy]
    lines = []
    for i in range(0, len(flat), 4):
        row = flat[i : i + 4]
        lines.append("".join(f"{v:16.2f}" for v in row) + "\n")
    return lines


def create_reservoir_storage_area(
    geom_file: str | Path,
    storage_area_name: str,
    perimeter_coords: list[tuple[float, float]],
    create_backup: bool = True,
) -> Path:
    """Create a lumped (non-2D) Storage Area geometry block representing the
    reservoir pool -- a polygon perimeter only, no mesh. Includes an empty
    placeholder elevation-volume record so `GeomStorage.set_elevation_volume`
    (which replaces an existing "Storage Area Elev Volume=" line rather than
    inserting a new one) can be called afterward to attach the
    `storage_curve.py`-derived rating curve.
    """
    geom_file = Path(geom_file)
    if not geom_file.exists():
        raise FileNotFoundError(f"Geometry file not found: {geom_file}")
    if len(perimeter_coords) < 3:
        raise ValueError("perimeter_coords needs at least 3 (x, y) points")
    _require_ras_name_length(storage_area_name, "storage_area_name")

    with geom_file.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    cx, cy = _polygon_centroid(perimeter_coords)
    block = [
        f"Storage Area={storage_area_name},{cx:.7f},{cy:.7f}\n",
        f"Storage Area Surface Line= {len(perimeter_coords)}\n",
        *_format_storage_area_surface_line(perimeter_coords),
        "Storage Area Type= 0 \n",
        "Storage Area Area=\n",
        "Storage Area Min Elev=\n",
        "Storage Area Is2D=0\n",
        "Storage Area Elev Volume= 0 \n",
        "\n",
    ]
    lines.extend(block)
    return GeomParser.safe_write_geometry(geom_file, lines, create_backup=create_backup) or geom_file


def dam_crest_profile(dam: DamConfig, connection_length_ft: float) -> pd.DataFrame:
    """A flat 2-point weir-crest profile at the dam's crest elevation,
    spanning a Connection line's full length -- the simplest defensible
    embankment cross-section before a real surveyed crest profile is
    substituted in. `apply_breach_parameters` is what actually carves the
    breach into this crest once a `BreachEstimate` is computed.
    """
    return pd.DataFrame(
        {"Station": [0.0, connection_length_ft], "Elevation": [dam.crest_elevation_ft, dam.crest_elevation_ft]}
    )


def create_breach_structure(
    geom_file: str | Path,
    dam: DamConfig,
    connection_coords: list[tuple[float, float]],
    upstream_storage_area: str,
    downstream_flow_area: str,
    weir_coef: float = 3.0,
    create_backup: bool = True,
) -> Path:
    """Create the Connection representing the dam embankment itself,
    between the reservoir Storage Area and the downstream 2D Flow Area,
    named `ras_connection_name(dam)` (not `breach_structure_name(dam)` --
    see that function's docstring for why: HEC-RAS's fixed-width Connection
    name field can't safely hold a long, human-readable name).

    `connection_coords` is the dam-crest alignment as a polyline (at least
    2 points) in the project CRS -- typically digitized once from the
    terrain/imagery, same category of one-time GIS input as a reservoir
    footprint used to be before `storage_curve.py`'s flood-fill approach.
    Its total length becomes the flat crest profile's span (see
    `dam_crest_profile`); `apply_breach_parameters` should be called next
    (passing this same `ras_connection_name(dam)` as `structure_name`) to
    wire in the computed breach geometry.
    """
    import math

    geom_file = Path(geom_file)
    name = ras_connection_name(dam)
    _require_ras_name_length(upstream_storage_area, "upstream_storage_area")
    _require_ras_name_length(downstream_flow_area, "downstream_flow_area")
    weir_width_ft = dam.crest_length_ft

    rc.GeomLateral.set_connection(
        geom_file,
        name,
        connection_coords,
        upstream_area=upstream_storage_area,
        downstream_area=downstream_flow_area,
        weir_width=weir_width_ft,
        weir_coef=weir_coef,
        create_backup=create_backup,
    )

    length_ft = sum(
        math.dist(connection_coords[i], connection_coords[i + 1]) for i in range(len(connection_coords) - 1)
    )
    profile = dam_crest_profile(dam, length_ft)
    return rc.GeomLateral.set_connection_profile(geom_file, name, profile, create_backup=create_backup) or geom_file


def flow_area_perimeter_from_terrain(terrain_path: str | Path) -> list[tuple[float, float]]:
    """A rectangular 2D flow area perimeter covering a terrain raster's full extent.

    A reasonable default AOI -- the LiDAR survey extent already covers the
    reservoir/dam vicinity (see docs/data_sources.md). Refine with a
    hand-drawn perimeter once the downstream routing reach needs to extend
    further than the terrain source's coverage.
    """
    with rasterio.open(terrain_path) as src:
        left, bottom, right, top = src.bounds
    return [(left, bottom), (right, bottom), (right, top), (left, top), (left, bottom)]


def breach_geom_kwargs(
    estimate: BreachEstimate,
    breach_bottom_elev_ft: float,
    weir_top_elev_ft: float,
) -> dict:
    """Map a computed BreachEstimate onto HEC-RAS's breach geometry fields
    (RasBreach.set_breach_geom's kwargs). Kept separate from the actual
    ras-commander call so the mapping itself is unit-testable without a
    live HEC-RAS project.
    """
    return dict(
        initial_width=estimate.average_breach_width_ft,
        final_bottom_elev=breach_bottom_elev_ft,
        left_slope=estimate.side_slope_h_per_v,
        right_slope=estimate.side_slope_h_per_v,
        top_elev=weir_top_elev_ft,
        formation_time=estimate.formation_time_hr,
        active=True,
    )


def create_dam_project(
    dam: DamConfig,
    dest_dir: str | Path,
    ras_version: str = "7.0",
    crs: str = "EPSG:2232",
) -> Path:
    project_name = dam.name.replace(" ", "_")
    return rc.create_project_from_template(dest_dir, project_name=project_name, version=ras_version, target_crs=crs)


def attach_terrain(
    project_folder: str | Path,
    terrain_geotiff_paths: list[str | Path],
    projection_prj_path: str | Path,
    ras_version: str = "7.0",
) -> Path:
    out_hdf = Path(project_folder) / "Terrain" / "Terrain.hdf"
    return rc.RasTerrain.create_terrain_hdf(
        input_rasters=[str(p) for p in terrain_geotiff_paths],
        output_hdf=out_hdf,
        projection_prj=str(projection_prj_path),
        units="Feet",
        hecras_version=ras_version,
    )


def configure_2d_flow_area(
    geom_file: str | Path,
    flow_area_name: str,
    perimeter_coords: list[tuple[float, float]],
    mannings_n: float = 0.035,
) -> None:
    """mannings_n is a single default constant for now. manning_lookup.py
    (NLCD-derived, spatially varied Manning's n) is a planned follow-up
    module, not yet built -- see docs/methodology.md's pipeline diagram.
    """
    rc.GeomStorage.set_2d_flow_area_perimeter(geom_file, flow_area_name, coordinates=perimeter_coords)
    rc.GeomStorage.set_2d_flow_area_settings(geom_file, flow_area_name, mannings_n=mannings_n)


def generate_mesh(geom_number, cell_size_ft: float, ras_object=None):
    return rc.GeomMesh.generate_all(geom_number, cell_size=cell_size_ft, ras_object=ras_object)


def apply_breach_parameters(
    plan_number,
    structure_name: str,
    estimate: BreachEstimate,
    breach_bottom_elev_ft: float,
    weir_top_elev_ft: float,
    ras_object=None,
) -> None:
    """Wire a computed BreachEstimate into HEC-RAS's breach block for an
    already-existing structure -- call `create_breach_structure` first to
    create it (`structure_name` here should be that same
    `ras_connection_name(dam)`).
    """
    rc.RasBreach.create_breach_block(plan_number, structure_name, ras_object=ras_object)
    rc.RasBreach.set_breach_geom(
        plan_number,
        structure_name,
        ras_object=ras_object,
        **breach_geom_kwargs(estimate, breach_bottom_elev_ft, weir_top_elev_ft),
    )


def configure_initial_and_boundary_conditions(
    unsteady_file: str | Path,
    area_2d_name: str,
    normal_pool_elevation_ft: float,
    downstream_friction_slope: float,
    ras_object=None,
) -> None:
    """Sunny-day breach IC: reservoir starts at normal pool (per
    methodology.md's sunny-day assumption), downstream boundary is a
    normal-depth outflow using an estimated channel friction slope.
    """
    rc.RasUnsteady.set_initial_storage_elevation(
        unsteady_file, area_2d_name, normal_pool_elevation_ft, ras_object=ras_object
    )
    rc.RasUnsteady.set_normal_depth_boundary(
        unsteady_file, downstream_friction_slope, area_2d=area_2d_name, ras_object=ras_object
    )


def run_plan(plan_number, ras_object=None):
    return rc.RasCmdr.compute_plan(plan_number, ras_object=ras_object)
