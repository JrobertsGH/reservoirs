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
both dams from their actual 2021 LiDAR surveys. **Known blocker**: the
elevation-area-storage curve (`storage_curve.py`) can't fully close either
reservoir's basin from that LiDAR alone — aerial LiDAR can't see through
standing water, so anything submerged during the Oct 2021 flight is simply
absent from the DEM, and the dry margin it did capture doesn't fully
enclose either reservoir's true rim within the survey extent. Confirmed by
placing the flood-fill seed to test multiple hypotheses, not just the
default. This needs a bathymetric/sonar survey or a historic
storage-capacity study to resolve — not something further code changes can
fix on their own.

What's left before a first real HEC-RAS run: resolve the storage-curve gap
above (at least well enough to build a defensible reservoir Storage Area
rating curve), then run the full chain (terrain → breach params → storage
curve → 2D flow area/mesh → reservoir Storage Area → breach structure →
run plan → postprocess → structures/PAR → map) for real for Loch Lomond and
Fall River Reservoir.

## Adding a new dam

Copy an existing `dams/<dam>/dam.yaml` as a template, fill in the schema
fields (`src/reservoirs/config.py` documents what's required), and point
`terrain_sources` at whatever survey data exists. No code changes needed for
a dam that fits the existing schema.

