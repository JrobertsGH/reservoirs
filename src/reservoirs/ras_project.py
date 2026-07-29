"""HEC-RAS 2D unsteady project automation via ras-commander.

**Automatable by this module**: creating a new project from a blank
template, attaching terrain, defining/meshing a 2D flow area, applying
computed breach parameters to an existing breach structure, setting
initial/boundary conditions, and running the plan.

**NOT automatable with the installed ras-commander version (0.99.1)**:
`GeomInlineWeir` is read-only in this version (`get_profile`/`get_weirs`/
`get_gates` only -- verified by inspecting the installed package directly,
no create/set methods exist). The dam embankment itself -- the breachable
inline weir / SA-2D connection structure representing the dam in the 2D
flow area -- must be created once, by hand, in the HEC-RAS GUI, named to
match `breach_structure_name(dam)`. Everything downstream of that one-time
manual step (breach parameters, boundary conditions, mesh, execution) is
fully automated and re-runnable from a `dam.yaml` + a `BreachEstimate`.

This asymmetry mirrors the reservoir-footprint-digitization step already
flagged in docs/methodology.md: some CAD/GUI steps aren't safely
automatable with current tooling and shouldn't be faked.
"""

from __future__ import annotations

from pathlib import Path

import rasterio
import ras_commander as rc

from reservoirs.breach_params import BreachEstimate
from reservoirs.config import DamConfig


def breach_structure_name(dam: DamConfig) -> str:
    return f"{dam.name} Dam"


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
    already-existing structure -- see module docstring for the manual
    prerequisite (the structure itself must already exist in the geometry).
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
