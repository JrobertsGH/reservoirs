# reservoirs

A reusable dam-breach inundation mapping toolkit, built to satisfy Colorado
Division of Water Resources (DWR) Dam Safety Branch requirements for
Emergency Action Plan (EAP) inundation maps.

**Read [`docs/preliminary_disclaimer.md`](docs/preliminary_disclaimer.md)
first.** Every output is a preliminary technical analysis for PE review, not
a certified deliverable.

## Current scope

Two dams, both owned by the Agricultural Ditch & Reservoir Company (ADRC),
both High Hazard, both with inundation maps on file from 1997:

- **Loch Lomond Dam** — Clear Creek County (`dams/loch_lomond/`)
- **Fall River Reservoir Dam** — Idaho Springs (`dams/fall_river/`)

Loch Lomond sits 9 miles upstream of Fall River Reservoir on the same
stream, so a Loch Lomond breach is routed through Fall River Reservoir
before reaching Idaho Springs, rather than modeled in isolation.

## Documentation

- [`docs/methodology.md`](docs/methodology.md) — the regulatory framework,
  pipeline architecture, and the reasoning behind every major decision
  (why HEC-RAS's Advanced tier, why cascade routing, why 2021 LiDAR over
  public DEM, why sunny-day breach).
- [`docs/breach_models.md`](docs/breach_models.md) — every empirical breach
  model implemented (Froehlich 2008, MacDonald & Langridge-Monopolis,
  Washington State, SMPDBK), with full equations, variable definitions, and
  when each applies — transcribed directly from Colorado DWR's own
  guidance document.
- [`docs/data_sources.md`](docs/data_sources.md) — where every fact in each
  `dam.yaml` came from, what other source material exists but isn't
  ingested yet, and known data-quality gaps.
- [`docs/preliminary_disclaimer.md`](docs/preliminary_disclaimer.md) — the
  PE-review requirement, reused on every generated output.
- [`docs/user_guide.md`](docs/user_guide.md) — practical, run-this
  instructions for every pipeline stage, environment gotchas, and how to
  add a new dam.
- [`docs/audit_trail.md`](docs/audit_trail.md) — chronological record of
  non-obvious findings, fixes, and data-quality decisions, with evidence
  trails. Append to it; don't edit history.

## Project layout

```
dams/<dam_name>/dam.yaml   per-dam config: geometry, storage, location,
                           cascade relationships, terrain source references
src/reservoirs/            the pipeline modules (see methodology.md)
tests/                     unit tests for the numerically-verifiable pieces
docs/                      documentation (this section)
```

## Status

Environment (Git, a conda-forge Python env, HEC-RAS 7.0.1) is set up, and
every pipeline stage in `methodology.md`'s diagram is implemented and
tested: `breach_params.py`, `terrain.py`, `storage_curve.py`,
`manning_lookup.py`, `ras_project.py`, `postprocess.py`, `structures.py`,
and `mapping.py`. Each is runnable standalone via a console script
(`reservoirs-breach-params`, `reservoirs-terrain`, `reservoirs-storage-curve`,
`reservoirs-manning-lookup`, `reservoirs-structures`, `reservoirs-postprocess`,
`reservoirs-mapping` — run any with `--help`). `ras_project.py` has no
single-command CLI (it's inherently a multi-step, stateful HEC-RAS project
build, not a one-shot transform) but no longer needs any manual GUI step
either — see `methodology.md`'s "No manual step" section.

Real terrain and a real breach-parameter report have now been produced for
both dams from their actual 2021 LiDAR surveys. The storage-curve gap
(aerial LiDAR can't see through standing water, so it alone can't close
either reservoir's basin) is resolved for both dams, by two different
routes:

- **Loch Lomond**: a real 2022 bathymetric survey was found and merged in
  (`terrain.build_terrain_from_lidar_and_bathymetry`) — the basin now
  closes almost exactly to crest, and its curve matches the reported
  normal storage to within 1% near normal pool.
- **Fall River Reservoir**: no bathymetric survey exists yet, so
  `storage_curve.anchor_curve_near_crest` (via `reservoirs-storage-curve
  --anchor-near-crest`) bridges the small remaining gap (the real DEM
  closes to within a few feet of crest on its own) by anchoring to the
  dam's reported total storage. Flagged `anchored=True` per row and still
  needs PE sign-off — an explicit, documented interim approach, not a
  substitute for survey data.

A candidate dam-crest alignment (needed for `ras_project.
create_breach_structure`) has also been extracted from Fall River's real
terrain and visually confirmed (`terrain.extract_crest_alignment`), and
`DamConfig` now has a `normal_pool_elevation_ft` field sourced from each
dam's own EIR freeboard figure (not guessed).

**A first real HEC-RAS project build has been attempted** for Fall River
Reservoir, against the real, installed HEC-RAS 7.0.1 — not a hypothetical
run. Project creation, terrain attachment, the 2D flow area, the reservoir
Storage Area (real footprint + real elevation-volume curve), and the
breach Connection (real crest alignment + real computed breach parameters)
all succeeded. Two gaps were found by actually trying, not by inspection:
`init_ras_project` needs the exact installed HEC-RAS version string
(`"7.0.1"`, not the template's `"7.0"`), and — genuinely blocked, not just
undone — neither this toolkit nor the installed `ras-commander` can create
a Plan or Unsteady Flow file from scratch (only modify an existing one).
See `docs/audit_trail.md` and `docs/user_guide.md` §2.5 for the full,
verified sequence and both gaps.

**Plan/Unsteady-file gap: resolved by decision, not by code.** Confirmed
genuinely absent (even `ras-commander`'s own `set_normal_depth_boundary`
docstring says authoring one from scratch is an unbuilt follow-up) —
create the blank Plan + Unsteady Flow Data once in the HEC-RAS GUI (see
`docs/user_guide.md` §2.5b for the exact steps against this real project),
then hand back to Python for boundary condition values, breach parameters,
mesh generation, and running.

A shareable **model setup progress report** (real terrain, real reservoir
footprint, real crest alignment, real breach-parameter estimate — no
computed flood extent, since none has been run yet) is at
`dams/fall_river/outputs/fall_river_model_setup_progress_2026-07-29.html`.

What's left before a real run: finish the GUI step above, pick a mesh cell
size, refine the 2D Flow Area's perimeter (currently the full terrain
bounding rectangle, not yet clipped to downstream of the dam), then run
the plan and the rest of the chain (postprocess → structures/PAR → map)
for real.

## Adding a new dam

Copy an existing `dams/<dam>/dam.yaml` as a template, fill in the schema
fields (`src/reservoirs/config.py` documents what's required), and point
`terrain_sources` at whatever survey data exists. No code changes needed for
a dam that fits the existing schema.

