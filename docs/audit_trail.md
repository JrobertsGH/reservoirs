# Audit Trail

A chronological record of non-obvious findings, fixes, and decisions made
while building and running this toolkit — the "why" behind commits that
isn't already captured in commit messages or the other docs. Append to
this rather than editing history; each entry should be understandable on
its own without re-reading the whole file.

See also: [`methodology.md`](methodology.md) (the pipeline's design and
architectural decisions), [`data_sources.md`](data_sources.md) (where every
`dam.yaml` fact came from), [`preliminary_disclaimer.md`](preliminary_disclaimer.md)
(what every entry here is subject to: nothing below is a certified
engineering conclusion).

## 2026-07-29 — Plan/Unsteady-file gap: confirmed genuinely absent, decided on GUI

Followed up on the previous entry's open question (write a new Plan/
Unsteady-file writer, vs. create one by hand in the GUI) by checking
harder for a hidden capability first, the same way the breach-structure
"manual step" turned out to be a wrong-class assumption earlier this
session. This time the answer held up under scrutiny:

- Downloaded `ras-commander`'s official HEC-RAS example project set
  (`RasExamples.get_example_projects`/`extract_project`) and inspected a
  real "2D Unsteady Flow Hydraulics" project (`Muncie`, plan `p04` +
  geometry `g04`) directly — confirms what a real, valid 2D unsteady Plan
  file looks like (a ~300-line keyword file, mostly program defaults) and
  a real Unsteady Flow file's `Boundary Location=` block format. Muncie's
  own boundaries are all 1D river/reach/station-keyed, though, not
  SA/2D-keyed like our project — not directly reusable as a template for
  our case, but confirms the general file shape.
- Read `RasUnsteady.set_normal_depth_boundary`'s source directly: its own
  docstring states plainly that it "ONLY edits a boundary that already
  exists... Authoring brand-new boundary blocks from geometry definitions
  is tracked separately as a follow-up" — i.e. even `ras-commander`'s own
  authors haven't built this yet. `set_initial_storage_elevation` *does*
  append a new entry if one is absent (checked its source too), but a
  Normal Depth boundary on a 2D BC line needs the BC line itself to exist
  in the geometry first, which has the same "not yet buildable" status.

**Decision**: create the blank Plan + Unsteady Flow Data once in the
HEC-RAS GUI (§2.5b in `user_guide.md`) rather than write new, unverified
file-writing code for a gap the library's own maintainers have explicitly
flagged as unbuilt. Writing an untested Plan/Unsteady/BC-line writer for a
real regulatory dam-breach model carries more risk (a subtly wrong file
that HEC-RAS silently mis-runs) than a five-minute, well-understood GUI
step — unlike the embankment-structure case, where a real, tested write
API turned out to already exist and just needed finding.

## 2026-07-29 — Model-setup progress report (not a computed inundation map)

Produced `dams/fall_river/outputs/fall_river_model_setup_progress_
2026-07-29.html` — a shareable status snapshot for stakeholders, built
entirely from real data already in hand (2021 LiDAR terrain hillshade,
the real reservoir footprint at normal pool, the real extracted crest
alignment, the real Froehlich 2008 breach estimate) with **no computed
flood extent**, since no HEC-RAS simulation has run yet. Labeled
explicitly as "NOT A COMPUTED INUNDATION EXTENT" in the figure itself and
the report text, not just in a disclaimer someone could skip past — this
distinction matters because it's exactly the kind of thing that could be
mistaken for a real result if forwarded without context.

## 2026-07-29 — Environment: broken MKL/BLAS install

**Finding.** The `reservoirs` conda environment had `numpy` linked against
an MKL build (`libblas`/`libcblas`/`liblapack` at `3.11.0=*_mkl`, `mkl
2026.1.0`) that crashed with a native, unrecoverable exception
(`Windows fatal exception: code 0xc06d007f`) on **any** BLAS-backed
operation — confirmed with a minimal `np.eye(3) @ np.eye(3)`, which crashed
identically with no other imports involved. Pure elementwise numpy
(`a + 1`, `np.sum`) worked fine; only real matrix multiplication triggered
it. This silently broke every `matplotlib`/`geopandas` plot call (they hit
BLAS internally via affine-transform math), which is what made `mapping.py`
look broken even though its own logic was correct.

**Root cause.** Not conclusively identified (didn't reproduce it under an
isolated debugger), but forcing `MKL_ENABLE_INSTRUCTIONS=SSE4_2` /
`MKL_NUM_THREADS=1` didn't help, which rules out the usual "hybrid-CPU
AVX-512 core migration" MKL bug on 12th/13th/14th-gen Intel chips (this
machine: i7-14700HX). Most likely a corrupted or ABI-mismatched MKL install
in this specific conda env, not a fundamental incompatibility.

**Fix.** Switched the env's BLAS backend from MKL to OpenBLAS:
```
conda install -n reservoirs "libblas=*=*openblas"
```
This removed `mkl`/`onemkl-license`/`tbb`/`libhwloc` and pulled in
`libopenblas 0.3.33` — a ~4 MB change, reversible by reinstalling the
`*mkl*` build variant. Currently installed: `libblas`/`libcblas`/`liblapack`
`3.11.0` (`*_openblas` build), `libopenblas 0.3.33`. All 89 tests (at the
time) passed immediately after. **Not tracked in git** — this is a
conda-env fix, not a code or dependency-manifest change; anyone rebuilding
this env from `environment.yml` who hits the same crash should apply the
same fix (the failure mode is unmistakable: any `@`/`np.dot`/plotting call
crashes the whole Python process with no traceback, just a native
exception).

## 2026-07-29 — Completed the pipeline: `structures.py` + `cli.py`

**Finding.** `structures.py` (downstream structures / population-at-risk
overlay) was the one stage in `methodology.md`'s pipeline diagram with no
code or tests — `mapping.py` already had a `structures_gdf` parameter
waiting for it. Separately, `pyproject.toml` declared three
`reservoirs-*` console scripts pointing at `reservoirs.cli`, a module that
had never existed in this repo's history (`git log --all -- cli.py`
returns nothing) — those entry points would have failed with
`ModuleNotFoundError` if anyone had actually run them.

**Fix.** Added `structures.py` (OSM building-footprint fetch via `osmnx` +
spatial filter to inundation extent + a preliminary structure-count PAR
estimate) and `cli.py` (wiring all seven runnable stages as console
scripts). See commits `c03fb2d` and `561f004`.

## 2026-07-29 — The "manual HEC-RAS GUI step" was a wrong-class assumption, not a real limitation

**Finding.** `methodology.md` and `ras_project.py`'s docstring both stated
that the breachable dam-embankment structure had to be created by hand in
the HEC-RAS GUI, because `GeomInlineWeir` — `ras-commander` 0.99.1's class
for "the breachable inline weir / SA-2D connection" — is read-only
(`get_profile`/`get_weirs`/`get_gates` only, verified by reading its
source directly). This was true as stated, but **`GeomInlineWeir` is the
wrong class**: reading its source shows it parses 1D river-station inline
structures (keyed by River/Reach/RS), not a Storage-Area-to-2D-Area
connection. The actual class for that — `GeomLateral` — was sitting in the
same package the whole time, fully read/write (`set_connection`,
`set_connection_profile`, `set_connection_gates`, `delete_connection`,
each explicitly documented as "verified to compute" against production 2D
models).

**Fix.** Added `create_reservoir_storage_area` (writes a plain, non-2D
Storage Area block directly — no public `ras-commander` method creates one)
and `create_breach_structure` (wraps `GeomLateral.set_connection` +
`set_connection_profile`) to `ras_project.py`. The whole chain from
`dam.yaml` to a computed HEC-RAS plan is now scriptable with no GUI step.
See commit `9709a71`; `methodology.md`'s "No manual step" section has the
full writeup.

**A real bug found while verifying this, not by inspection.** Writing an
actual test connection named `"Fall River Reservoir Dam"` (24 characters —
`breach_structure_name`'s normal output) revealed that
`GeomLateral.set_connection` silently fixed-width-truncates Connection
names *and* their Storage-Area references to 16 characters. The connection
got stored as `"Fall River Reser"`, which then failed to round-trip
against the Storage Area's own (untruncated) name — a silent data
corruption, not an exception, so it would have gone unnoticed without a
real round-trip test. Added `ras_connection_name(dam)` (e.g. `"Dam
070129"`, always ≤16 chars) as the identifier actually written to the
geometry file, kept distinct from the human-readable
`breach_structure_name`, plus validation that raises `ValueError` rather
than silently truncating for any name over 16 characters passed to either
new function.

## 2026-07-29 — Real terrain + breach-parameter run for both dams

**What ran.** `reservoirs-terrain`, `reservoirs-storage-curve`, and
`reservoirs-breach-params` against both dams' actual 2021 LiDAR surveys
(not synthetic test data) for the first time. Outputs are in
`dams/<dam>/data/` (gitignored — not in version control):
`terrain_lidar.tif`, `storage_curve.csv`, `storage_curve_defaultseed.csv`.

**Fix found along the way.** `dams/loch_lomond/dam.yaml`'s
`lidar_points_csv` path named a file
(`AW_CCLiDAR_LochLomond_ALL_POINTS.csv`) that doesn't exist on
`\\ORION\Departments\...`; the real file has an extra date token
(`AW_CCLiDAR_LochLomond_20211018_ALL_POINTS.csv`). Corrected in commit
`ed8f80a`. Fall River Reservoir's three configured sources all matched
as-written.

**Known, unresolved blocker: the storage curve can't close either
reservoir's basin.** `storage_curve.py`'s flood-fill approach needs the
DEM to show a fully enclosed low point around the reservoir; it doesn't,
for either dam:
- **Loch Lomond**: at every elevation tested (default seed at the global
  minimum, and a manually-placed seed on the actual pool side of the dam),
  the flooded region touches the LiDAR survey's boundary — meaning **0
  ac-ft** of enclosed storage is recoverable from this terrain at the
  dam's crest elevation, regardless of seed placement.
- **Fall River Reservoir**: better but still short. A genuinely closed
  basin (`touches_boundary=False`) exists from roughly 10,824–10,838 ft,
  topping out around 316 ac-ft / ~23.6 ac (plausibly close to the dam's
  reported 24 ac surface area) — but it breaks out to the survey boundary
  before reaching the dam's crest elevation (10,841 ft), where the
  cross-check against reported storage (890 ac-ft) comes up 48% low
  (465.4 ac-ft).

**Root cause, not a code bug**: aerial LiDAR can't see through standing
water. Anything submerged during the October 2021 flight is simply absent
from the DEM — the survey only captured the dry margin above that day's
water line, and that margin doesn't fully enclose either reservoir's true
rim within the flown extent. No amount of seed-placement or code fixing
resolves this; it needs a bathymetric/sonar survey of the submerged
reservoir floor, or a historical storage-capacity study, as an additional
terrain source. See the README's "Status" section and
[`user_guide.md`](user_guide.md#known-gap-the-storage-curve-cant-fully-close-either-basin)
for how to work around it for a preliminary example.

**Secondary, independent limitation**: the storage-curve cross-check
compares DEM-derived storage at `crest_elevation_ft` (the top of the dam),
not at normal pool elevation (which sits below crest by design freeboard
margin) — `dam.yaml`'s schema has no separate normal-pool-elevation field
yet, so even a perfect DEM wouldn't make this particular check exact. Worth
adding a `normal_pool_elevation_ft` field to `config.py`'s `DamConfig`
before relying on this check numerically.

**Breach-parameter results** (piping failure mode, per each dam's 2025 GEI
CDSE note): both dams' Froehlich (2008) result lands in the guideline's
valid range (ER/Hw ≈ 4.4 for both); MacDonald & Langridge-Monopolis and
Washington State both collapse to sub-2-ft breach widths with both
plausibility warnings tripped for both dams — the toolkit's own logic is
independently pointing at a piping-hole failure rather than a full
trapezoidal breach, consistent with GEI's Potential-Failure-Mode findings
already cited in `data_sources.md`. Fall River's volume input
(`max_storage_ac_ft: 1050`) is itself flagged `# confirm against EIR/owner
records` in its `dam.yaml` — unverified, not yet a fact.

## 2026-07-29 — Loch Lomond drainage area: provisional correction, still unverified

**Finding.** The state dam-inventory record's 685 sq mi (438,400 ac)
drainage area for Loch Lomond is physically impossible: Fall River
Reservoir sits 9 miles downstream of Loch Lomond on the same stream and
its own drainage area is only 1,792 ac — a downstream dam cannot have a
smaller contributing area than one upstream of it.

**What was checked.** Two network-share files previously flagged as
possible resolutions turned out not to help: `Fall River Watershed
Topo.pdf` / `Fall River Watershed.pdf` are locator maps with a single pin
and no delineated boundary or acreage figure (and don't even show Loch
Lomond in their main extent); `FallRiver_ClearCreek.shp` is a 5-feature
stream **centerline** layer, not a watershed polygon, with all its
NHD-style attribute fields empty. USGS StreamStats's REST API returned
HTTP 404 (appears to be down/retired as of this check). USGS NLDI (same
underlying NHDPlus network) delineated Loch Lomond's basin at ~740 ac,
corroborated by correctly containing the known upstream Lake Caroline —
but running the identical method on Fall River Reservoir's own point
overshoots its accepted figure by 17%, so treat 740 ac as
order-of-magnitude (roughly 700–900 ac), not exact.

**Status.** `dams/loch_lomond/dam.yaml`'s `drainage_area_ac` was updated
from 438,400 to 740.0, with the full evidence trail as an in-file comment,
still explicitly marked `UNVERIFIED`. Re-delineating from the on-file 2021
LiDAR (far higher resolution than NHDPlus's ~30 m DEM) and PE sign-off are
the recommended path to a defensible final figure. See commit `ed8f80a`
and `data_sources.md`'s "Known data-quality issue" section for the full
writeup.

## 2026-07-29 — `normal_pool_elevation_ft`: sourced from each dam's EIR, not guessed

Added the field (noted as missing above) to `DamConfig`. Rather than derive
a value from the DEM-storage-curve match point (a reasonable cross-check,
but not authoritative), searched each dam's 2025 EIR PDF (in Downloads)
directly and found an explicit, official freeboard figure for both:
Fall River Reservoir `FREEBOARD (FT): 6.0`, Loch Lomond `FREEBOARD (FT):
3.5`. `normal_pool_elevation_ft = crest_elevation_ft - freeboard_ft`:
**10,835.0 ft** (Fall River) and **11,196.5 ft** (Loch Lomond).

Cross-checking each against its real DEM-derived storage curve at that
elevation surfaced two different, both-worth-noting outcomes:
- **Loch Lomond**: DEM storage at 11,196.5 ft is 1,021.7 ac-ft vs. the
  reported 875 (17% over) -- while the curve actually matches 875 almost
  exactly a few feet lower, around 11,191.5 ft. Both figures are sourced
  (one from the EIR, one from real bathymetric survey data); the ~5 ft
  discrepancy is real and unresolved, flagged in `dam.yaml` for PE
  attention -- not something to silently pick a winner on.
- **Fall River Reservoir**: DEM storage at 10,835.0 ft is only 239.5 ac-ft
  vs. the reported 890 (73% short) -- a *bigger* gap than at crest, where
  `anchor_curve_near_crest` forces an exact match by construction. This is
  real, non-anchored DEM data (elevation 10,835 ft sits within the
  trustworthy, non-boundary-touching range, which extends to ~10,838 ft) --
  meaning even at normal operating pool, the real 2021 LiDAR terrain can
  only account for about a quarter of the reservoir's true volume.
  Consistent with the reservoir having been partially full during the
  October 2021 flight (aerial LiDAR can't see the submerged portion) --
  and a concrete illustration that `anchor_curve_near_crest`'s bridged
  region (10,838-10,841 ft) is a real approximation, not a minor rounding
  gap. Fall River needs its own bathymetric survey before its curve should
  be trusted between normal pool and crest.

## 2026-07-29 — First real attempt at building a HEC-RAS project (Fall River Reservoir)

With real terrain, a real anchored storage curve, a real extracted crest
alignment, and a sourced `normal_pool_elevation_ft` all in hand, attempted
the actual `ras_project.py` build sequence end-to-end against the real,
installed HEC-RAS 7.0.1 -- not a synthetic/hypothetical run. Project at
`dams/fall_river/ras_project/` (gitignored, matching `dams/*/ras_project/`
in `.gitignore`).

**Succeeded, for real:**
1. `create_dam_project` -- real project created from the bundled RAS 7.0
   template, reprojected to EPSG:2232.
2. `attach_terrain` -- real Terrain.hdf built from
   `dams/fall_river_reservoir/data/terrain_lidar.tif` (0.27 MB, 18
   datasets).
3. `configure_2d_flow_area("Downstream 2D", ...)` -- using
   `flow_area_perimeter_from_terrain` (the terrain's full bounding
   rectangle -- see caveat below).
4. `create_reservoir_storage_area("Fall River Pool", ...)` using
   `storage_curve.reservoir_footprint_polygon` (new function, added this
   session) at `normal_pool_elevation_ft`, seeded inside the real pool --
   1,613 boundary vertices (the raw pixel-traced outline at 2ft
   resolution; should be simplified before a real submission, not blocking
   for this attempt). Its elevation-volume curve was set from the real
   anchored storage curve, thinned to 20 points via
   `np.linspace`-with-both-endpoints (an earlier naive positional-stride
   thinning attempt missed the crest endpoint entirely -- caught by
   checking `GeomStorage.get_storage_areas`'s `MaxElev` output against the
   expected crest elevation, not assumed).
5. `create_breach_structure` -- real Connection ("Dam 070129") from "Fall
   River Pool" to "Downstream 2D", using the real extracted crest
   alignment. Verified via `GeomLateral.get_connections`.
6. Computed real breach parameters (Froehlich 2008, piping,
   `max_storage_ac_ft_or_normal` = 1050 ac-ft): Bavg 91.2 ft, Tf 0.246 hr,
   ER/Hw 4.36.

**Two new gaps found by actually trying, not by inspection:**

1. **`init_ras_project`'s version string must match the installed HEC-RAS
   build exactly.** The bundled RAS 7.0 *template* (used by
   `create_dam_project`/`attach_terrain`) is unrelated to the installed
   *executable*'s version -- this machine has HEC-RAS **7.0.1** installed
   at `C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe`, and passing the
   template's `"7.0"` to `init_ras_project` fails to find it ("Ras.exe not
   found at expected path"). Passing `"7.0.1"` (the exact installed
   version, from `Get-ChildItem 'C:\Program Files (x86)\HEC\HEC-RAS'`)
   resolves it correctly. Not a code bug -- `create_dam_project`'s
   `ras_version="7.0"` default is correct and unrelated; this is purely a
   call-site detail for whoever runs `init_ras_project`, documented in
   `user_guide.md`.
2. **No automatable path exists (yet) to create a Plan file or Unsteady
   Flow file from scratch.** `ras_project.configure_initial_and_boundary_
   conditions` and `apply_breach_parameters` both assume a plan/unsteady
   file already exists (they only *modify* one, via `RasUnsteady.set_*`/
   `RasBreach.*`) -- confirmed by checking: the bundled RAS 7.0 template
   ships **only** a blank geometry (no `.pXX`/`.uXX` files at all, verified
   by listing `ras_commander`'s `resources/templates/RAS_7.0/` directory
   directly), and `RasPlan`/`RasUnsteady`'s only creation-adjacent methods
   are `clone_plan`/`clone_unsteady` (copy an *existing* plan/unsteady --
   nothing to clone from here). This is the one piece of the pipeline
   still genuinely blocked, and unlike the breach-structure discovery
   earlier this session, checking harder didn't turn up an existing write
   API -- it isn't there. Two ways forward, not yet decided: (a) write a
   new, carefully-verified minimal Plan-file/Unsteady-file writer (same
   rigor as `create_reservoir_storage_area`'s from-scratch text writer),
   or (b) create a blank plan + unsteady file once by hand in the HEC-RAS
   GUI (a much smaller one-time step than the embankment structure used to
   be, since geometry/breach/IC-BC would still all be scripted from there).

**Known simplification, not yet refined:** the 2D Flow Area's perimeter is
the terrain's full bounding rectangle, which geometrically overlaps the
reservoir Storage Area's footprint rather than being clipped to strictly
the downstream side of the crest alignment. Acceptable for proving the
automation chain works; should be refined (clip the 2D perimeter to the
downstream half using the extracted crest alignment) before this feeds a
real hydraulic run.

## 2026-07-29 — Loch Lomond's storage-curve gap resolved via real bathymetry

Following up on the storage-curve gap documented above, the user directed
attention to `LOCH_LOMOND_TOPO_10042022.csv` in Downloads specifically as a
real Loch Lomond bathymetric survey. That file had previously been grouped
with a confirmed-unrelated Grand County batch (see the entry below) based
on its raw coordinates matching that batch's *stated* range — but
cross-checking it directly (not through that batch's metadata) tells a
different story: 718 of its 1,321 points are marked `description="BTM"`
(bottom soundings), with an elevation range (11,124–11,203 ft) matching
this project's real Loch Lomond crest elevation (11,200 ft) almost
exactly. Its `x`/`y` columns are swapped relative to (Easting, Northing)
convention; once swapped, its points fall entirely inside Loch Lomond's
real 2021 LiDAR survey extent, and its centroid lands within ~0.15 mi of
the dam's recorded lat/lon. **Genuine data, mislabeled by association** —
see `data_sources.md`'s corrected entry for the full cross-check.

**Fix.** Added `load_bathymetry_points_csv` (handles the column swap,
filters to bottom soundings) and `build_terrain_from_lidar_and_bathymetry`
(merges bathymetric points with the existing LiDAR point cloud before
gridding) to `terrain.py`, plus a new `bathymetry_points_csv`
`terrain_sources` kind. Referenced the file in `dams/loch_lomond/dam.yaml`
at its current Downloads path (not yet moved onto `\\ORION` — flagged for
durability).

**Result — the gap is essentially closed for Loch Lomond.** Rebuilding
terrain with the merged data and reseeding the flood-fill at the deepest
bathymetric point (rather than the default global-minimum seed, which
still lands in the downstream channel and gives a nonsensical 6,508 ac-ft):
the basin now stays closed (`touches_boundary=False`) all the way *past*
crest elevation, only breaking out at 11,203.7 ft — 3.7 ft above crest
(11,200 ft). Storage at crest comes to 1,129.5 ac-ft vs. the reported 875
(29% over) — but at 11,191.7 ft, storage is 880.3 ac-ft, a 0.6% match to
the reported figure. This strongly suggests normal pool sits a few feet
below crest (as freeboard design would predict) and that the "29% at
crest" figure is an artifact of comparing at the wrong elevation (crest
instead of normal pool) — reinforcing the `normal_pool_elevation_ft`
schema gap noted above, now with real numbers showing where it actually
matters.

## 2026-07-29 — `anchor_curve_near_crest`: an explicit interim fallback where bathymetry isn't available

Fall River Reservoir has no equivalent bathymetric survey. Added
`storage_curve.anchor_curve_near_crest` — given a curve, a crest elevation,
and a known reported storage figure, it keeps the DEM-derived curve up to
its last trustworthy (non-boundary-touching) point, then linearly
interpolates storage from there to the crest anchor. Every added/replaced
row is marked `anchored=True`, so it can never be silently mistaken for
survey data. Wired into the CLI as `reservoirs-storage-curve
--anchor-near-crest` (requires `--dam-yaml`; `--anchor-storage-ac-ft` to
override the default of `normal_storage_ac_ft`).

Run for real against Fall River's terrain (informed seed inside the
reservoir pool, since the default seed fails identically to Loch Lomond's):
only **3 rows** needed anchoring/extrapolation — the real DEM-derived
closed basin already reaches to within 3 ft of crest on its own (matching
the ~10,824–10,838 ft closed range found in the original real-terrain run),
so this interim approach only bridges a small, well-characterized gap
here, not a large assumption. Output: `dams/fall_river_reservoir/data/
storage_curve_anchored.csv`. Still explicitly preliminary — needs PE
sign-off per the CLI's own printed reminder.

## 2026-07-29 — Fall River's dam-crest alignment: extracted from terrain, visually confirmed

`ras_project.create_breach_structure` needs the dam-crest alignment as a
polyline — the one remaining real one-time GIS input, not derivable from
`storage_curve.py`'s flood-fill the way the reservoir footprint is. Added
`terrain.extract_crest_alignment`: finds the connected component of
terrain cells at or above the dam's crest elevation nearest its `dam.yaml`
location (an intact embankment's own top surface sits at/above design
crest, distinguishing it from the surrounding valley), then fits a line
through it via PCA and returns its two endpoints.

Run against Fall River Reservoir's real terrain and checked visually
(plotted over a hillshade of the local terrain window): the result is a
clear, ~30–40 ft-wide linear ridge exactly where the dam.yaml location
sits, distinct from incidental far-away contour crossings elsewhere in the
scene. Extracted length: 918.2 ft vs. `dam.yaml`'s `crest_length_ft: 840.0`
— 9% over, plausibly because the elevation threshold picks up a bit of
abutment/spillway tie-in beyond the literal design crest length. Treat the
endpoints as a good candidate, not ground truth — review against as-built
drawings before using in a real HEC-RAS project; this is a heuristic over
survey terrain, the same category of judgment call as picking a storage-
curve seed point.

## 2026-07-29 — Fall River's `max_storage_ac_ft` confirmed

The `# confirm against EIR/owner records` flag on `max_storage_ac_ft:
1050.0` in `dams/fall_river/dam.yaml` is resolved: confirmed directly by
the owner (Jarod Roberts, CMWC) as correct. Comment updated accordingly.

## 2026-07-29 — Grand County file mix-up: confirmed unrelated, one open question

**Finding.** The Downloads-folder files previously flagged as describing a
different, Grand-County "Loch Lomond" (`loch_lomond_breach_analysis.*`,
`LOCH_LOMOND_TOPO_10042022.*`) are confirmed unrelated to this project,
with a stronger evidence trail than before: beyond the county/coordinate
mismatch already documented, the data implies a reservoir with ~192 ac
surface area and 80,000 ac-ft of storage — 6x the area and **91x the
volume** of this project's real, 31 ac / 875 ac-ft Loch Lomond. Not the
same dam by any measure.

**Open question, not resolved.** `CAROLINE_TOPO_10042022.csv`, filed
alongside the unrelated batch with the same date stamp, is a genuine
judgment call: its max elevation (11,874 ft) and bounding-box area (~21.7
ac) both land within single-digit percent of Lake Caroline's real, verified
figures (11,880 ft crest, 20 ac surface area) — hard to dismiss as
coincidence. But its raw coordinates sit in the same unverified local grid
as the confirmed-unrelated `LOCH_LOMOND_TOPO` file (neither transforms
cleanly under standard UTM 13N or Colorado State Plane conventions to
either dam's real lat/lon), so it can't be independently confirmed as
genuine Clear-Creek-County survey data. **Not incorporated into the
project.** Before using it: trace its actual provenance (check
`\\ORION\Departments` for an October 2022 survey order under either dam's
name, or ask whoever supplied the original Downloads batch what project it
came from).
