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

#### Known gap: 2021 LiDAR alone can't close either basin (now resolved, two ways)

The 2021 LiDAR survey can't see through standing water, so the flood-fill's
low point doesn't fully enclose either reservoir from LiDAR alone (see
[`audit_trail.md`](audit_trail.md)). Two resolutions exist, both
preliminary/PE-review-required:

- **Loch Lomond has a real bathymetric survey.** Build terrain with it
  merged in:
  ```
  reservoirs-terrain dams/loch_lomond/dam.yaml   # still LiDAR-only; see below for the merged build
  ```
  There's no CLI wrapper for the merged build yet — call it directly:
  ```python
  from reservoirs.config import load_dam_config
  from reservoirs.terrain import build_terrain_from_lidar_and_bathymetry
  dam = load_dam_config("dams/loch_lomond/dam.yaml")
  build_terrain_from_lidar_and_bathymetry(dam)  # -> dams/loch_lomond/data/terrain_lidar_bathy.tif
  ```
  Then run `reservoirs-storage-curve` against that file with a seed placed
  inside the reservoir (not the default global-minimum seed — see below).
  The basin now closes past crest elevation.

- **No bathymetric survey exists for Fall River Reservoir (or any other
  dam without one).** Use `--anchor-near-crest`:
  ```
  reservoirs-storage-curve dams/fall_river_reservoir/data/terrain_lidar.tif --dam-yaml dams/fall_river/dam.yaml --seed-x <x> --seed-y <y> --anchor-near-crest
  ```
  This keeps the DEM-derived curve up to the last elevation it can
  actually resolve, then linearly interpolates to the dam's reported
  storage at crest. Every added row is marked `anchored=True` in the
  output CSV — check that column before trusting any row near the top of
  the curve. Add `--anchor-storage-ac-ft` to anchor to a different figure
  than `normal_storage_ac_ft` (e.g. `max_storage_ac_ft`).

**Either way, use an informed seed, not the default.** The default seed
(global minimum elevation) lands in the downstream channel for both dams
and gives a nonsensical cross-check (thousands of percent off) — pass
`--seed-x`/`--seed-y` for a point you know is inside the actual reservoir
pool (e.g. a bathymetric survey's deepest point, if one exists).

**Getting the reservoir's actual footprint polygon** (not just the
elevation-area-storage numbers) for `ras_project.create_reservoir_
storage_area`'s `perimeter_coords`: `storage_curve.reservoir_footprint_
polygon(terrain_path, elevation_ft, seed_xy=...)` runs the same flood-fill
and returns the exterior ring coordinates directly. The result is the raw
pixel-traced outline (thousands of vertices at 2ft resolution) —
`shapely`'s `.simplify()` before using it in a real HEC-RAS project, not
blocking for a first attempt.

### 2.3b Dam-crest alignment and downstream channel slope

Two more terrain-derived helpers feed `ras_project.py`'s later steps:

- `terrain.extract_crest_alignment(terrain_path, dam, search_radius_ft=600.0)`
  — finds the connected ridge of terrain cells at/above the dam's crest
  elevation nearest its `dam.yaml` location and fits a line through it,
  returning the two endpoints as a candidate `connection_coords` for
  `create_breach_structure`. Review the result visually (plot it over the
  terrain) before trusting it — it's a heuristic over survey data, not
  as-built drawings.
- `terrain.estimate_downstream_channel_slope(terrain_path, crest_alignment, sample_distance_ft=2000.0)`
  — a first-pass estimate of the downstream channel's bed slope (ft/ft),
  for `configure_initial_and_boundary_conditions`'s `downstream_friction_
  slope` (HEC-RAS's normal-depth boundary approximates friction slope with
  bed slope). Samples terrain perpendicular to the crest alignment on
  whichever side is lower (downstream) and fits a linear trend. Coarse and
  terrain-only — it doesn't know about tailwater effects or channel
  roughness, so treat it as a starting point, not a final value.

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
multi-step, stateful build, not a one-shot transform. The sequence below
is **verified against a real run** against Fall River Reservoir's actual
data on this machine's installed HEC-RAS 7.0.1 (see
[`audit_trail.md`](audit_trail.md) for the full account, including two
gaps found only by actually running it — read those before relying on
this being copy-paste-to-a-finished-model):

```python
from reservoirs.config import load_dam_config, FailureMode
from reservoirs.breach_params import estimate_all_methods
from reservoirs.storage_curve import reservoir_footprint_polygon
from reservoirs.terrain import extract_crest_alignment
from reservoirs import ras_project as rp
import pandas as pd
import numpy as np

dam = load_dam_config("dams/fall_river/dam.yaml")
terrain_path = "dams/fall_river_reservoir/data/terrain_lidar.tif"  # note the _reservoir suffix -- see §2.1's gotcha

prj_path = rp.create_dam_project(dam, dest_dir="dams/fall_river/ras_project", crs="EPSG:2232")
project_folder = prj_path.parent
geom_file = project_folder / f"{prj_path.stem}.g01"

rp.attach_terrain(project_folder, [terrain_path], project_folder / f"{prj_path.stem}.projection.prj")

flow_area_name = "Downstream 2D"          # <=16 chars -- see the gotcha below
storage_area_name = "Fall River Pool"     # <=16 chars

rp.configure_2d_flow_area(geom_file, flow_area_name, rp.flow_area_perimeter_from_terrain(terrain_path))
# NOTE: this perimeter is the terrain's full bounding rectangle, which overlaps
# the reservoir footprint below rather than being clipped to just downstream of
# the dam -- a known simplification (see audit_trail.md), refine before a real run.

seed_xy = (2946045.22, 1723847.37)  # a point known to be inside the real pool -- see §2.3
footprint = reservoir_footprint_polygon(terrain_path, dam.normal_pool_elevation_ft, seed_xy=seed_xy)
rp.create_reservoir_storage_area(geom_file, storage_area_name, footprint)

curve = pd.read_csv("dams/fall_river_reservoir/data/storage_curve_anchored.csv")
curve = curve[curve.elevation_ft <= dam.crest_elevation_ft].reset_index(drop=True)
idx = sorted(set(np.linspace(0, len(curve) - 1, 20).round().astype(int)))  # keep both endpoints -- see the gotcha below
thin = curve.iloc[idx]
import ras_commander as rc
rc.GeomStorage.set_elevation_volume(geom_file, storage_area_name, thin.elevation_ft.tolist(), thin.storage_ac_ft.tolist())

crest_alignment = extract_crest_alignment(terrain_path, dam, search_radius_ft=600.0)
rp.create_breach_structure(geom_file, dam, crest_alignment, storage_area_name, flow_area_name)

estimates = estimate_all_methods(dam, FailureMode.piping, dam.max_storage_ac_ft_or_normal)
# rp.apply_breach_parameters(...) and everything past this point needs a real plan/unsteady
# file to attach to -- see the "blocked" gotcha below; this is as far as verified automation
# currently reaches.
```

**Gotcha — 16-character name limit.** Any name you pass as a Storage Area
name, 2D Flow Area name, or the dam's connection (`ras_connection_name`
handles the last one for you) must be ≤16 characters — HEC-RAS's classic
geometry text format silently truncates past that, which caused a real,
silent round-trip bug during development (see `audit_trail.md`).
`create_reservoir_storage_area`/`create_breach_structure` raise
`ValueError` instead of truncating if you pass something too long — pick
short names (`"Fall River Pool"`, `"Dam 070129"`) from the start.

**Gotcha — thin the storage curve with both endpoints kept.** A naive
`df.iloc[::20]` positional stride can miss the crest-elevation row
entirely, silently giving the Storage Area a rating curve that doesn't
actually reach crest. Use `np.linspace(0, len(df)-1, n).round()` (as
above) so both ends are always included — verify with
`GeomStorage.get_storage_areas(...)['MaxElev']` after setting it, don't
assume.

**Gotcha — `init_ras_project`'s version string must match the installed
HEC-RAS build exactly**, not just the template version. On this machine,
HEC-RAS 7.0.1 is installed at `C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\`
— passing `"7.0"` to `rc.init_ras_project(...)` fails to find `Ras.exe`
("not found at expected path"); pass `"7.0.1"` (check
`Get-ChildItem 'C:\Program Files (x86)\HEC\HEC-RAS'` for the exact
installed version on any given machine). This is unrelated to
`create_dam_project`'s `ras_version="7.0"` default, which selects a
bundled *template* and is correct as-is.

**Blocked — no Plan or Unsteady Flow file creation exists yet.**
`apply_breach_parameters` and `configure_initial_and_boundary_conditions`
both *modify* an existing plan/unsteady file; neither `ras_project.py` nor
the installed `ras-commander` (no bundled template, no `clone`-from-nothing
option, and `set_normal_depth_boundary`'s own docstring explicitly says
authoring a brand-new boundary block is "tracked separately as a
follow-up" — confirmed by reading the library's source, not assumed) can
create one from scratch. **Decision made 2026-07-29**: create the blank
Plan + Unsteady Flow Data once in the HEC-RAS GUI (§2.5b below) rather
than write new, unverified file-format code for something the library's
own authors haven't built yet either — everything else (geometry, breach
parameters, boundary condition *values*, mesh, running the plan) still
goes back to being scriptable from there.

**Reminder**: always pass `ras_project.ras_connection_name(dam)` — not
`breach_structure_name(dam)` — anywhere the actual HEC-RAS geometry file
needs the connection's name (creating it, and later in
`apply_breach_parameters`'s `structure_name`). `breach_structure_name` is
for human-readable labels only (reports, titles).

### 2.5b Finishing the model in the HEC-RAS GUI

Picking up where §2.5 leaves off — the geometry (2D flow area, reservoir
Storage Area, breach Connection) is already built and saved in the real
`.g01` file. This is the GUI portion needed once per project before
control returns to Python. Names below match what the real Fall River
Reservoir project actually has.

1. **Open the project.** File → Open Project → `Fall_River_Reservoir.prj`
   in `dams/fall_river/ras_project/`.
2. **Create Unsteady Flow Data.** Edit → Unsteady Flow Data (or Ctrl+U).
   - **Initial Conditions tab**: find the "Fall River Pool" storage area
     and enter its starting (sunny-day, normal-pool) elevation — use
     `normal_pool_elevation_ft` from `dam.yaml` (**10,835.0 ft**, sourced
     from the EIR's freeboard figure — see `audit_trail.md`).
   - **Boundary Conditions tab** needs a place for flow to leave the
     "Downstream 2D" flow area. If no BC line exists yet on its
     downstream perimeter, add one first in the Geometric Data editor
     (2D Flow Area editor → "SA/2D Area BC Lines" tool → draw a line
     across the downstream edge of the mesh perimeter, name it something
     short like `"DS Exit"` — remember the ≤16-character limit). Back in
     Unsteady Flow Data, select that BC line and set **Normal Depth**,
     friction slope starting point **≈0.16** (`terrain.
     estimate_downstream_channel_slope`'s real-terrain estimate for this
     site) — this is unusually steep for a normal-depth boundary, so
     cross-check it against a topo map or the channel's visible grade in
     RAS Mapper before trusting it; it's a first-pass terrain-only number,
     not a final value.
   - Save as `u01`, give it a title (e.g. "Sunny-Day Breach").
3. **Create a new Plan.** File → New Plan. Select Geometry `g01` and
   Unsteady Flow `u01`. Set:
   - **Simulation window**: short — a sunny-day breach only needs enough
     time to capture the peak and initial recession, e.g. 6–12 hours.
   - **Computation Interval**: start small (1–5 sec) given the steep
     downstream slope above; HEC-RAS's own compute-window stability
     warnings will tell you if it needs to be smaller.
   - Save as `p01`.
4. **Set the breach parameters.** Either in the GUI (double-click the "Dam
   070129" connection in the Geometric Data editor → Breach tab → enter
   the Froehlich (2008) values already computed: width 91.2 ft, side
   slope 0.7 H:V, formation time 0.246 hr), **or** — once the plan exists
   — hand this back to Python to avoid transcription errors:
   ```python
   rp.apply_breach_parameters(
       "01", rp.ras_connection_name(dam), estimates["froehlich_2008"],
       breach_bottom_elev_ft=dam.crest_elevation_ft - dam.height_ft,
       weir_top_elev_ft=dam.crest_elevation_ft,
   )
   ```
5. **Generate the mesh.** In the Geometric Data editor, right-click the
   "Downstream 2D" flow area → Generate Computation Points (or just check
   "Force Geometry Preprocessor" in the Plan's compute options and let it
   mesh at compute time).
6. **Compute.** Run → Compute Current Plan (F10). Watch the compute
   window — HEC-RAS reports instability, dry-cell, and convergence
   warnings there directly; don't trust a "finished" run that has them.
7. **Get results back to this toolkit.** Once computed, hand off to the
   pipeline's own postprocessing (§2.6–2.8 below) for a polished,
   preliminary-labeled EAP-style map, rather than exporting straight from
   RAS Mapper.

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

As of 2026-07-29, both dams have workable inputs — see
[`audit_trail.md`](audit_trail.md) for the full evidence trail behind each
item below:

**Resolved:**
- ✅ Storage-curve gap — Loch Lomond via a real bathymetric survey
  (§2.3), Fall River via `--anchor-near-crest` (only 3 rows needed
  anchoring; its real DEM closure already reaches to within a few feet of
  crest).
- ✅ Dam-crest alignment — extracted from Fall River's real terrain
  (`terrain.extract_crest_alignment`) and visually confirmed. Not yet done
  for Loch Lomond.
- ✅ Fall River's `max_storage_ac_ft: 1050` — confirmed by the owner.
- ✅ `normal_pool_elevation_ft` — added to `DamConfig`, sourced from each
  dam's own EIR (`FREEBOARD` field), not guessed: 10,835.0 ft (Fall River),
  11,196.5 ft (Loch Lomond). Loch Lomond's real numbers show concretely why
  the field matters: DEM-derived storage matches the reported figure to
  within 1% a few feet away from this value, but is 17% off *at* it —
  a real, unresolved discrepancy, not a bug (see `audit_trail.md`).
- ✅ A first real HEC-RAS project build was attempted for Fall River
  Reservoir — project creation, terrain attachment, 2D flow area, the
  reservoir Storage Area (real footprint + real elevation-volume curve),
  and the breach Connection (real crest alignment + real Froehlich 2008
  parameters) all succeeded for real. See §2.5 for the verified sequence.
- ✅ A first-pass downstream friction-slope estimate
  (`terrain.estimate_downstream_channel_slope`) is available, computed
  directly from real terrain along the channel perpendicular to the crest
  alignment — review before trusting (it doesn't know about tailwater
  effects or channel roughness), but it's a real number, not a bare guess.

**Still needed before a real HEC-RAS run:**
1. **Plan and Unsteady Flow file creation** — genuinely blocked, not just
   undone. Neither `ras_project.py` nor `ras-commander` can create either
   file from scratch (only modify an existing one) — see §2.5's "Blocked"
   gotcha and `audit_trail.md` for the full account of what was checked.
   Needs a decision: write a new file-writer, or create a blank plan +
   unsteady once by hand in the GUI.
2. **Mesh cell size** — still an engineering judgment call
   `ras_project.py` takes as a parameter rather than assumes.
3. **Refine the 2D Flow Area perimeter** — currently the terrain's full
   bounding rectangle (overlaps the reservoir footprint); should be clipped
   to strictly downstream of the crest alignment before a real run.
4. Then: finish the project build (§2.5), run the plan in the installed
   HEC-RAS 7.0.1, and run `reservoirs-postprocess` → `reservoirs-structures`
   → `reservoirs-mapping` against its real output.

Every output from that chain is still preliminary per
[`preliminary_disclaimer.md`](preliminary_disclaimer.md) until a PE signs
off on the anchored curve, the extracted crest alignment, the sourced
`normal_pool_elevation_ft`, and the values chosen above.
