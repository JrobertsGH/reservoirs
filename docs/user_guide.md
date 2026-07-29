# User Guide

A practical, run-this walkthrough of the toolkit. For *why* it's built
this way, see [`methodology.md`](methodology.md); for what to check before
trusting any output, see
[`preliminary_disclaimer.md`](preliminary_disclaimer.md) — read that one
first if you haven't.

## 1. Environment

Everything runs inside the `reservoirs` conda environment
(`environment.yml` in the repo root). Activate it, or call its Python/
console scripts directly by full path:

```
conda activate reservoirs
reservoirs-breach-params --help
```

or, without activating:

```
"C:\Users\<you>\AppData\Local\miniforge3\envs\reservoirs\Scripts\reservoirs-breach-params.exe" --help
```

**Known gotcha — broken BLAS.** If any command crashes the whole Python
process with no traceback (just a native exception, often
`Windows fatal exception: code 0xc06d007f`), the env's BLAS backend is
likely broken (see [`audit_trail.md`](audit_trail.md)'s first entry for the
full diagnosis). Fix:
```
conda install -n reservoirs "libblas=*=*openblas"
```
This is an environment fix, not tracked in git — if you rebuild the env
from scratch and hit this, apply it again.

**Benign warning — `GDAL_DATA`.** You'll see `Warning 3: Cannot find
gdalvrt.xsd (GDAL_DATA is not defined)` on most commands that touch GDAL
(via `rasterio`/`geopandas`/`pyogrio`). It's noise, not a failure — every
command still produces correct output. Set `GDAL_DATA` if it bothers you,
but nothing here depends on it being set.

## 2. The pipeline, stage by stage

Everything starts from a dam's `dams/<dam>/dam.yaml`. Each stage below is
independently runnable — you can inspect and sanity-check one before
moving to the next, rather than running a black-box end-to-end script.

```
dam.yaml
   │
   ├─ reservoirs-terrain          → DEM/terrain GeoTIFF
   ├─ reservoirs-breach-params    → breach parameter report (3 methods)
   ├─ reservoirs-storage-curve    → elevation-area-storage curve (needs terrain)
   ├─ reservoirs-manning-lookup   → NLCD-derived roughness grid (needs network)
   │
   │   [ras_project.py: no CLI -- see step 6 below, Python/notebook only]
   │
   ├─ reservoirs-postprocess      → depth grid + inundation extent (needs a computed HEC-RAS plan's HDF)
   ├─ reservoirs-structures       → downstream structures + PAR estimate (needs network + an inundation extent)
   └─ reservoirs-mapping          → final PDF/PNG map (needs an inundation extent)
```

### 2.1 Terrain

```
reservoirs-terrain dams/fall_river/dam.yaml
```
Builds a terrain GeoTIFF from the dam's configured `lidar_points_csv`
source and writes it to `dams/<dam_name_slugified>/data/terrain_lidar.tif`.

**Watch for**: the output folder is slugified from `dam.name`, which may
not match the `dams/<dam>/` folder name you'd expect — e.g. "Fall River
Reservoir" slugifies to `dams/fall_river_reservoir/data/`, not
`dams/fall_river/data/` where its `dam.yaml` actually lives. Check
`terrain.py`'s `dam_data_dir()` if a run's output isn't where you expect
it, or pass `--out-dir` explicitly to control it.

Use `--public-dem` to fall back to USGS 3DEP instead of the configured
LiDAR source (needs network access; useful for extending coverage
downstream of the LiDAR survey's extent).

### 2.2 Breach parameters

```
reservoirs-breach-params dams/fall_river/dam.yaml --failure-mode piping
```
Prints all three empirical methods (Froehlich 2008, MacDonald &
Langridge-Monopolis, Washington State) with cross-check warnings. Defaults
to `piping` (both currently-modeled dams have this as their primary mode
per their 2025 GEI CDSE notes — check before assuming it's right for a new
dam) and to the dam's max/normal storage as the breach volume; override
either with `--failure-mode overtopping` / `--volume-ac-ft <n>`.

**Read the warnings.** If `ER/Hw` or `Bavg/Hb` trip a warning for the
Macdonald/Washington-State methods but not Froehlich, that's the toolkit
telling you the dam likely only develops a piping hole rather than a full
trapezoidal breach — worth modeling as a sluice-gate-style piping failure
in HEC-RAS rather than a full breach, per `breach_models.md`.

### 2.3 Storage curve

```
reservoirs-storage-curve dams/fall_river_reservoir/data/terrain_lidar.tif --dam-yaml dams/fall_river/dam.yaml
```
Derives an elevation-area-storage curve directly from terrain (flood-fill
from a seed point, no digitized reservoir polygon needed). Writes a CSV
next to the terrain file by default. `--dam-yaml` triggers a cross-check
against the dam's reported `normal_storage_ac_ft`; a warning here doesn't
mean the code is wrong — see the **known gap** below.

Default seed is the terrain's global minimum elevation cell, which is
often in the downstream channel, not the reservoir — if the cross-check
warning looks wildly wrong (e.g. thousands of percent off), pass
`--seed-x`/`--seed-y` for a point you know is inside the actual reservoir
pool.

#### Known gap: the storage curve can't fully close either basin

Confirmed for both Loch Lomond and Fall River Reservoir (see
[`audit_trail.md`](audit_trail.md)): the 2021 LiDAR survey can't see
through standing water, so the flood-fill's low point never fully
encloses within the surveyed extent. This is a **data gap, not a bug** —
don't spend time re-tuning the seed or the code; it needs a bathymetric/
sonar survey or a historic storage-capacity study as an additional
terrain source. See §5 below for how to work around this for a
preliminary example deliverable in the meantime.

### 2.4 Manning's n (optional, informational only right now)

```
reservoirs-manning-lookup dams/fall_river/dam.yaml
```
Fetches NLCD land cover and converts it to a Manning's n roughness grid
(network required). Not yet wired into HEC-RAS's own land-cover mechanism
— `ras_project.configure_2d_flow_area` still uses a single uniform
Manning's n constant. Useful today as a reference layer for manually
sanity-checking that assumption.

### 2.5 HEC-RAS project setup — Python/notebook, not a single CLI command

`ras_project.py` has no console script because it's an inherently
multi-step, stateful build (create project → attach terrain → define the
2D flow area → create the reservoir Storage Area → create the breach
Connection → apply computed breach parameters → set initial/boundary
conditions → mesh → run), not a one-shot transform. Drive it from a short
Python script or notebook, e.g.:

```python
from reservoirs.config import load_dam_config, FailureMode
from reservoirs.breach_params import estimate_all_methods
from reservoirs import ras_project as rp

dam = load_dam_config("dams/fall_river/dam.yaml")

project_folder = rp.create_dam_project(dam, dest_dir="ras_projects")
geom_file = project_folder / "..."  # the project's .g01, per ras-commander's project object

rp.attach_terrain(project_folder, ["dams/fall_river_reservoir/data/terrain_lidar.tif"], "path/to/projection.prj")

flow_area_name = "Downstream 2D"          # <=16 chars -- see the gotcha below
storage_area_name = "Fall River Pool"     # <=16 chars

rp.configure_2d_flow_area(geom_file, flow_area_name, rp.flow_area_perimeter_from_terrain(terrain_path))
rp.create_reservoir_storage_area(geom_file, storage_area_name, reservoir_perimeter_coords)
# GeomStorage.set_elevation_volume(geom_file, storage_area_name, elevations, volumes) next,
# using storage_curve.py's output for the reservoir footprint's elevation/volume columns

rp.create_breach_structure(geom_file, dam, dam_crest_alignment_coords, storage_area_name, flow_area_name)

estimates = estimate_all_methods(dam, FailureMode.piping, dam.max_storage_ac_ft_or_normal)
rp.apply_breach_parameters(
    plan_number, rp.ras_connection_name(dam), estimates["froehlich_2008"],
    breach_bottom_elev_ft=..., weir_top_elev_ft=dam.crest_elevation_ft,
)

rp.configure_initial_and_boundary_conditions(unsteady_file, flow_area_name, normal_pool_elev_ft=..., downstream_friction_slope=...)
rp.generate_mesh(geom_number, cell_size_ft=...)
rp.run_plan(plan_number)
```

**Gotcha — 16-character name limit.** Any name you pass as a Storage Area
name, 2D Flow Area name, or the dam's connection (`ras_connection_name`
handles the last one for you) must be ≤16 characters — HEC-RAS's classic
geometry text format silently truncates past that, which caused a real,
silent round-trip bug during development (see `audit_trail.md`).
`create_reservoir_storage_area`/`create_breach_structure` raise
`ValueError` instead of truncating if you pass something too long — pick
short names (`"Fall River Pool"`, `"Dam 070129"`) from the start.

**Reminder**: always pass `ras_project.ras_connection_name(dam)` — not
`breach_structure_name(dam)` — anywhere the actual HEC-RAS geometry file
needs the connection's name (creating it, and later in
`apply_breach_parameters`'s `structure_name`). `breach_structure_name` is
for human-readable labels only (reports, titles).

### 2.6 Postprocess

Once a plan has actually been computed in HEC-RAS:
```
reservoirs-postprocess path/to/plan.p01.hdf --wse-column <col> --terrain dams/fall_river_reservoir/data/terrain_lidar.tif --dam-yaml dams/fall_river/dam.yaml --seed-x <x> --seed-y <y>
```
Writes `depth_grid.tif` and `inundation_extent.shp`, and prints any
plausibility warnings (disconnected inundation "islands", implausible max
depth vs. dam height). `--wse-column` is whatever column name your
specific HDF results carry for max water-surface elevation — inspect the
HDF's own columns first (`postprocess.load_max_ws_from_hdf`) rather than
guessing.

### 2.7 Structures / PAR

```
reservoirs-structures dams/fall_river/dam.yaml --inundation dams/fall_river/data/inundation_extent.shp
```
Fetches OpenStreetMap building footprints (network required), filters to
the inundation extent, and prints a preliminary population-at-risk
estimate (structure count × persons/structure — a coarse planning-level
figure, override the default with `--persons-per-structure`).

### 2.8 Map

```
reservoirs-mapping dams/fall_river/dam.yaml --inundation dams/fall_river/data/inundation_extent.shp --structures dams/fall_river/data/structures_at_risk.shp --out dams/fall_river/data/inundation_map.pdf
```
Renders the final static map (PDF or PNG — extension controls format) with
the mandatory preliminary watermark and a `.metadata.txt` sidecar carrying
the same disclaimer as plain text. Use `--no-basemap` if you're offline or
want a faster render without OpenStreetMap tiles.

## 3. Adding a new dam

Copy an existing `dams/<dam>/dam.yaml` as a template (`config.py` documents
every field). No code changes needed for a dam that fits the existing
schema — just point `terrain_sources` at whatever survey data exists for
it, following the pattern in [`data_sources.md`](data_sources.md) for
citing where each fact came from.

## 4. Running the tests

```
cd C:\Users\<you>\dev\reservoirs
"C:\Users\<you>\AppData\Local\miniforge3\envs\reservoirs\python.exe" -m pytest -q
```
All tests use synthetic data and run with no network access, no live
HEC-RAS install, and no real dam data — they verify the code, not any
specific dam's numbers. 98 tests as of this writing, all passing.

## 5. Producing a first preliminary example deliverable

Fall River Reservoir is the better starting candidate — see
[`audit_trail.md`](audit_trail.md#2026-07-29--real-terrain--breach-parameter-run-for-both-dams):
its terrain shows a genuinely closed basin over part of its elevation
range, where Loch Lomond's currently shows none at any elevation. Getting
from here to a real first example still requires, in order:

1. **A decision on the storage-curve gap** (§2.3) — either commission
   bathymetric survey data, or have a PE approve a documented interim
   approach (e.g. blending the DEM-derived curve over the range it does
   cover with the dam's reported total storage as a single anchor point
   near crest). This is a judgment call for a PE to make and sign off on,
   not something to pick silently in code.
2. **Digitizing the dam-crest alignment** — `create_breach_structure`
   needs the crest centerline as a polyline in the project CRS. One-time
   GIS input, same category as the reservoir-footprint step
   `storage_curve.py`'s flood-fill approach made unnecessary elsewhere —
   this one hasn't been eliminated (the embankment's actual location isn't
   derivable from terrain alone).
3. **A `normal_pool_elevation_ft` field** — `config.py`'s `DamConfig`
   doesn't have one yet (noted in `audit_trail.md`); needed for the sunny-
   day initial condition (`configure_initial_and_boundary_conditions`) and
   to make the storage-curve cross-check compare at the right elevation
   instead of at crest.
4. **Confirming Fall River's storage figure** — `max_storage_ac_ft: 1050`
   in its `dam.yaml` is flagged `# confirm against EIR/owner records`,
   unverified. Resolve before it feeds a real breach-parameter estimate.
5. **Mesh cell size and boundary-condition values** (downstream friction
   slope, tailwater assumptions) — engineering judgment calls that
   `ras_project.py` takes as parameters rather than assumes.
6. Then: build the project (§2.5), run the plan in the installed
   HEC-RAS 7.0.1, and run `reservoirs-postprocess` →
   `reservoirs-structures` → `reservoirs-mapping` against its real output.

Every output from that chain is still preliminary per
[`preliminary_disclaimer.md`](preliminary_disclaimer.md) until a PE signs
off on the items above.
