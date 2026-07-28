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

## Project layout

```
dams/<dam_name>/dam.yaml   per-dam config: geometry, storage, location,
                           cascade relationships, terrain source references
src/reservoirs/            the pipeline modules (see methodology.md)
tests/                     unit tests for the numerically-verifiable pieces
docs/                      documentation (this section)
```

## Status

Environment (Git, a conda-forge Python env, HEC-RAS 7.0.1) is set up and the
breach-parameter module (`breach_params.py`) is implemented and tested.
Terrain ingestion, HEC-RAS automation, GIS post-processing, and map
rendering are not built yet — see `methodology.md`'s pipeline diagram for
what's still ahead.

## Adding a new dam

Copy an existing `dams/<dam>/dam.yaml` as a template, fill in the schema
fields (`src/reservoirs/config.py` documents what's required), and point
`terrain_sources` at whatever survey data exists. No code changes needed for
a dam that fits the existing schema.

