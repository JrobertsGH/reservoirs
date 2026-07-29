"""Console-script entry points -- one per independently-runnable pipeline
stage (see docs/methodology.md's pipeline diagram). Each command takes a
dam's `dam.yaml` (plus whatever that stage additionally needs) and either
prints a report or writes an output file, so a stage can be run and
inspected long before the next one in the pipeline exists.

`ras_project.py` has no CLI command here: it requires a one-time manual
HEC-RAS GUI step partway through (see that module's docstring), so it isn't
a single push-button operation the way the other stages are.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reservoirs.config import DamConfig, FailureMode, load_dam_config


def _dam_yaml_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("dam_yaml", type=Path, help="Path to a dams/<dam>/dam.yaml config file")


def _print_breach_report(dam: DamConfig, vw_ac_ft: float, estimates: dict) -> None:
    print(f"Breach-parameter estimate -- {dam.name} (State Dam ID {dam.state_dam_id})")
    print(f"Reservoir volume at breach: {vw_ac_ft:.1f} ac-ft\n")
    for key, est in estimates.items():
        print(f"[{est.method}] failure mode: {est.failure_mode.value}")
        print(f"  Average breach width (Bavg): {est.average_breach_width_ft:.1f} ft")
        print(f"  Side slope (Z, H:V):         {est.side_slope_h_per_v:.2f}")
        print(f"  Formation time (Tf):         {est.formation_time_hr:.2f} hr")
        print(f"  Erosion rate:                {est.erosion_rate_ft_per_hr:.1f} ft/hr")
        print(f"  ER/Hw:                       {est.erosion_rate_over_hw:.2f}")
        print(f"  Bavg/Hb:                     {est.breach_width_over_height:.2f}")
        for warning in est.warnings:
            print(f"  WARNING: {warning}")
        print()


def breach_params_cmd(argv: list[str] | None = None) -> None:
    from reservoirs.breach_params import estimate_all_methods

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    _dam_yaml_arg(parser)
    parser.add_argument(
        "--failure-mode",
        choices=[m.value for m in FailureMode],
        default=FailureMode.piping.value,
        help="Defaults to piping -- see docs/data_sources.md's 2025 GEI CDSE findings.",
    )
    parser.add_argument(
        "--volume-ac-ft",
        type=float,
        default=None,
        help="Reservoir volume at breach; defaults to the dam's max (or normal) storage.",
    )
    args = parser.parse_args(argv)

    dam = load_dam_config(args.dam_yaml)
    vw_ac_ft = args.volume_ac_ft if args.volume_ac_ft is not None else dam.max_storage_ac_ft_or_normal
    estimates = estimate_all_methods(dam, FailureMode(args.failure_mode), vw_ac_ft)
    _print_breach_report(dam, vw_ac_ft, estimates)


def terrain_cmd(argv: list[str] | None = None) -> None:
    from reservoirs.terrain import build_terrain_from_lidar, fetch_public_dem

    parser = argparse.ArgumentParser(description="Build a terrain GeoTIFF for a dam.")
    _dam_yaml_arg(parser)
    parser.add_argument(
        "--public-dem",
        action="store_true",
        help="Fetch a public USGS 3DEP DEM instead of using the dam's configured LiDAR source.",
    )
    parser.add_argument("--buffer-mi", type=float, default=3.0, help="Public-DEM only: AOI half-width, miles.")
    parser.add_argument("--resolution-m", type=int, default=10, help="Public-DEM only: DEM resolution, meters.")
    parser.add_argument("--cell-size-ft", type=float, default=2.0, help="LiDAR only: output grid cell size, feet.")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    dam = load_dam_config(args.dam_yaml)
    if args.public_dem:
        out_path = fetch_public_dem(dam, buffer_mi=args.buffer_mi, resolution_m=args.resolution_m, out_dir=args.out_dir)
    else:
        out_path = build_terrain_from_lidar(dam, cell_size_ft=args.cell_size_ft, out_dir=args.out_dir)
    print(f"Wrote terrain GeoTIFF: {out_path}")


def storage_curve_cmd(argv: list[str] | None = None) -> None:
    from reservoirs.storage_curve import anchor_curve_near_crest, compare_to_reported_storage, compute_elevation_area_storage_curve

    parser = argparse.ArgumentParser(description="Derive an elevation-area-storage curve from a terrain GeoTIFF.")
    parser.add_argument("terrain_path", type=Path)
    parser.add_argument("--dam-yaml", type=Path, default=None, help="If given, cross-check against the dam's reported normal storage.")
    parser.add_argument("--seed-x", type=float, default=None)
    parser.add_argument("--seed-y", type=float, default=None)
    parser.add_argument("--elevation-step-ft", type=float, default=1.0)
    parser.add_argument("--max-elevation-ft", type=float, default=None)
    parser.add_argument("--out", type=Path, default=None, help="CSV output path; defaults next to the terrain file.")
    parser.add_argument(
        "--anchor-near-crest",
        action="store_true",
        help="When the DEM can't resolve the reservoir's true rim (touches_boundary before crest), "
        "extend the curve to crest by linearly interpolating to a known reported storage figure. "
        "Requires --dam-yaml. Every added/replaced row is marked anchored=True -- an explicit, "
        "flagged approximation, not a substitute for real survey data. Needs PE sign-off.",
    )
    parser.add_argument(
        "--anchor-storage-ac-ft",
        type=float,
        default=None,
        help="--anchor-near-crest only: the known storage figure to anchor to; "
        "defaults to the dam's reported normal_storage_ac_ft.",
    )
    args = parser.parse_args(argv)

    if args.anchor_near_crest and args.dam_yaml is None:
        parser.error("--anchor-near-crest requires --dam-yaml")

    seed_xy = (args.seed_x, args.seed_y) if args.seed_x is not None and args.seed_y is not None else None
    curve = compute_elevation_area_storage_curve(
        args.terrain_path, seed_xy=seed_xy, elevation_step_ft=args.elevation_step_ft, max_elevation_ft=args.max_elevation_ft
    )

    dam = load_dam_config(args.dam_yaml) if args.dam_yaml is not None else None

    if args.anchor_near_crest:
        anchor_storage = args.anchor_storage_ac_ft if args.anchor_storage_ac_ft is not None else dam.normal_storage_ac_ft
        curve = anchor_curve_near_crest(curve, dam.crest_elevation_ft, anchor_storage, elevation_step_ft=args.elevation_step_ft)
        n_anchored = int(curve["anchored"].sum())
        print(
            f"Anchored {n_anchored} row(s) above the last DEM-trustworthy elevation to reach "
            f"{anchor_storage:.1f} ac-ft at crest ({dam.crest_elevation_ft} ft) -- PRELIMINARY, "
            "needs PE sign-off (see docs/preliminary_disclaimer.md)."
        )

    out_path = args.out if args.out is not None else Path(args.terrain_path).with_suffix(".storage_curve.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    curve.to_csv(out_path, index=False)
    print(f"Wrote storage curve ({len(curve)} rows): {out_path}")

    if dam is not None and not args.anchor_near_crest:
        for warning in compare_to_reported_storage(curve, dam.crest_elevation_ft, dam.normal_storage_ac_ft):
            print(f"WARNING: {warning}")


def manning_lookup_cmd(argv: list[str] | None = None) -> None:
    from reservoirs.manning_lookup import fetch_manning_n_grid, write_manning_n_geotiff

    parser = argparse.ArgumentParser(description="Fetch NLCD-derived Manning's n around a dam.")
    _dam_yaml_arg(parser)
    parser.add_argument("--buffer-mi", type=float, default=1.0)
    parser.add_argument("--year", type=int, default=2021)
    parser.add_argument("--resolution-m", type=int, default=30)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    dam = load_dam_config(args.dam_yaml)
    roughness_da = fetch_manning_n_grid(dam, buffer_mi=args.buffer_mi, year=args.year, resolution_m=args.resolution_m)
    out_path = args.out if args.out is not None else Path("dams") / dam.name.lower().replace(" ", "_") / "data" / "manning_n.tif"
    write_manning_n_geotiff(roughness_da, out_path)
    print(f"Wrote Manning's n GeoTIFF: {out_path}")


def structures_cmd(argv: list[str] | None = None) -> None:
    import geopandas as gpd

    from reservoirs.structures import (
        estimate_population_at_risk,
        fetch_structures_osm,
        structures_to_points,
        structures_within_inundation,
        write_structures_shapefile,
    )

    parser = argparse.ArgumentParser(description="Identify downstream structures within an inundation extent and estimate PAR.")
    _dam_yaml_arg(parser)
    parser.add_argument("--inundation", type=Path, required=True, help="Inundation extent (shapefile/GeoJSON) from postprocess.py.")
    parser.add_argument("--buffer-mi", type=float, default=3.0, help="OSM fetch AOI half-width, miles.")
    parser.add_argument("--persons-per-structure", type=float, default=2.5)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    dam = load_dam_config(args.dam_yaml)
    inundation_gdf = gpd.read_file(args.inundation)

    all_structures = fetch_structures_osm(dam, buffer_mi=args.buffer_mi)
    affected = structures_within_inundation(all_structures, inundation_gdf)
    points = structures_to_points(affected)

    out_path = args.out if args.out is not None else Path("dams") / dam.name.lower().replace(" ", "_") / "data" / "structures_at_risk.shp"
    if len(points) > 0:
        write_structures_shapefile(points, out_path)
        print(f"Wrote {len(points)} at-risk structure(s): {out_path}")
    else:
        print("No structures found within the inundation extent.")

    par = estimate_population_at_risk(affected, persons_per_structure=args.persons_per_structure)
    print(
        f"Preliminary PAR estimate: {par['structure_count']} structures x "
        f"{par['persons_per_structure']} persons/structure = ~{par['estimated_par']} persons at risk "
        "(planning-level only -- see docs/preliminary_disclaimer.md)."
    )


def postprocess_cmd(argv: list[str] | None = None) -> None:
    import rasterio

    from reservoirs.postprocess import (
        check_downstream_connectivity,
        check_max_depth_plausible,
        compute_depth_grid,
        extract_inundation_polygon,
        load_max_ws_from_hdf,
        rasterize_max_ws,
        write_depth_geotiff,
        write_inundation_shapefile,
    )

    parser = argparse.ArgumentParser(description="Turn a computed HEC-RAS plan's HDF results into a depth grid and inundation extent.")
    parser.add_argument("hdf_path", type=Path)
    parser.add_argument("--wse-column", required=True, help="Column in the HDF results holding max water-surface elevation.")
    parser.add_argument("--terrain", type=Path, required=True)
    parser.add_argument("--dam-yaml", type=Path, default=None, help="If given, runs the max-depth plausibility check against the dam's height.")
    parser.add_argument("--seed-x", type=float, default=None, help="Dam/breach location, for the downstream-connectivity check.")
    parser.add_argument("--seed-y", type=float, default=None)
    parser.add_argument("--depth-threshold-ft", type=float, default=0.1)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    max_ws_gdf = load_max_ws_from_hdf(args.hdf_path)
    max_ws = rasterize_max_ws(max_ws_gdf, args.wse_column, args.terrain)

    with rasterio.open(args.terrain) as src:
        terrain = src.read(1)
        transform = src.transform
        crs = src.crs

    depth = compute_depth_grid(max_ws, terrain)
    inundation_gdf = extract_inundation_polygon(depth, transform, crs, depth_threshold_ft=args.depth_threshold_ft)

    out_dir = args.out_dir if args.out_dir is not None else Path(args.terrain).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    depth_path = write_depth_geotiff(depth, transform, out_dir / "depth_grid.tif", crs)
    inundation_path = write_inundation_shapefile(inundation_gdf, out_dir / "inundation_extent.shp")
    print(f"Wrote depth grid: {depth_path}")
    print(f"Wrote inundation extent: {inundation_path}")

    if args.seed_x is not None and args.seed_y is not None:
        col, row = ~transform * (args.seed_x, args.seed_y)
        for warning in check_downstream_connectivity(depth, (int(round(row)), int(round(col)))):
            print(f"WARNING: {warning}")

    if args.dam_yaml is not None:
        dam = load_dam_config(args.dam_yaml)
        for warning in check_max_depth_plausible(depth, dam.height_ft):
            print(f"WARNING: {warning}")


def mapping_cmd(argv: list[str] | None = None) -> None:
    import geopandas as gpd

    from reservoirs.mapping import render_inundation_map

    parser = argparse.ArgumentParser(description="Render a static, EAP-ready inundation map.")
    _dam_yaml_arg(parser)
    parser.add_argument("--inundation", type=Path, required=True)
    parser.add_argument("--structures", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario-label", default="Sunny-Day Breach")
    parser.add_argument("--no-basemap", action="store_true", help="Skip network basemap tiles (also the offline fallback).")
    args = parser.parse_args(argv)

    dam = load_dam_config(args.dam_yaml)
    inundation_gdf = gpd.read_file(args.inundation)
    structures_gdf = gpd.read_file(args.structures) if args.structures is not None else None

    out_path = render_inundation_map(
        dam, inundation_gdf, args.out,
        scenario_label=args.scenario_label,
        structures_gdf=structures_gdf,
        basemap=not args.no_basemap,
    )
    print(f"Wrote inundation map: {out_path}")
