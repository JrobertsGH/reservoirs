# Methodology

See also: [`preliminary_disclaimer.md`](preliminary_disclaimer.md) (read first),
[`breach_models.md`](breach_models.md) (equation-level detail),
[`data_sources.md`](data_sources.md) (what data feeds this and where it came from).

## Why this exists

Colorado Division of Water Resources (DWR), Dam Safety Branch requires every
High or Significant Hazard dam to have a dam-failure inundation map on file
as part of its Emergency Action Plan (EAP) (Rule 16.1.5). Both dams this
toolkit currently covers — **Loch Lomond Dam** and **Fall River Reservoir
Dam**, both in Clear Creek County, owned by the Agricultural Ditch &
Reservoir Company (ADRC) — are classified **High Hazard**, and their
inundation maps on file with the state date to **1996/1997**. This toolkit
exists to produce an updated, defensible inundation analysis for both, built
as a *reusable* pipeline so the next dam ADRC/CMWC needs to analyze isn't a
from-scratch effort.

DWR's 2025 Engineer's Inspection Reports for both dams state the need
directly: *"The current 1996 inundation map for Loch Lomond and Fall River
is not helpful... A detailed inundation map should be developed for Loch
Lomond and/or Fall River."* (See [`data_sources.md`](data_sources.md) for
the full context, including a 2025 GEI Consultants risk assessment
identifying internal erosion/piping — not overtopping — as the dominant
threat for both dams, which is why the toolkit treats `FailureMode.piping`
as the primary scenario for both, per each dam's `dam.yaml` notes.)

A third, much smaller dam in the same drainage — **Lake Caroline**,
immediately upstream of Loch Lomond, same owner — is tracked in
`dams/lake_caroline/dam.yaml` for watershed/cascade completeness only. It's
Low Hazard and DWR does not require an EAP or inundation map for it, so it
gets no HEC-RAS effort of its own.

## The regulatory framework

DWR's own "Guidelines for Dam Breach Analysis" (Feb 10, 2010) defines a
**tiered structure** for dam breach analysis (their Table 1):

| Tier | Breach parameters | Hydrograph | Routing | Hydraulics |
|---|---|---|---|---|
| Screening | Empirical equations | SMPDBK peak discharge only | Empirical/nomograph | Normal depth |
| Simple | Empirical equations | HEC-1/HEC-HMS | Hydrologic model | Steady-state HEC-RAS |
| Intermediate | Empirical equations | HEC-1/HEC-HMS | Unsteady HEC-RAS | Peak WS profile |
| **Advanced** | Empirical equations | **HEC-RAS or DAMBRK** | Unsteady HEC-RAS | Peak WS profile |

Screening is explicitly *not* sufficient for producing an EAP inundation
map — DWR requires at least the Simple tier. Given both dams are High
Hazard, this toolkit targets the **Advanced tier**: HEC-RAS's own unsteady
2D hydraulic model handles both the breach hydrograph generation and the
downstream routing/hydraulics in a single simulation, which is more accurate
than routing a separately-generated hydrologic hydrograph and avoids the
piping-failure modeling problems DWR's guidance documents with HEC-HMS
(see [`breach_models.md`](breach_models.md) for why).

## Pipeline overview

```
dam.yaml (per-dam config, hand-edited)
   │
   ├─→ terrain.py          → ingest 2021 LiDAR (or fall back to USGS 3DEP for
   │                          reach not covered by the survey) → DEM/terrain
   │
   ├─→ breach_params.py     → Froehlich (2008) + MacDonald & Langridge-Monopolis
   │                          + Washington State breach parameters, cross-checked
   │                          against each other and against spillway capacity
   │
   ├─→ storage_curve.py     → elevation-area-storage curve from terrain +
   │                          reservoir footprint
   │
   ├─→ manning_lookup.py    → NLCD land cover → Manning's n across the mesh
   │
   ├─→ ras_project.py       → build + run the HEC-RAS 2D unsteady project
   │                          (terrain, 2D flow area, breach structure,
   │                          boundary conditions) via ras-commander
   │
   ├─→ postprocess.py       → HDF results → GeoTIFF depth grid + Shapefile
   │                          inundation polygon, plausibility checks
   │
   ├─→ structures.py        → downstream structures/population-at-risk overlay
   │
   └─→ mapping.py           → static, EAP-ready PDF/PNG map
```

Each stage is independently runnable (console-script entry points in
`pyproject.toml`), so a breach-parameter report can be produced and reviewed
long before anyone touches HEC-RAS.

## No manual step: the dam embankment structure is scriptable too

`ras_project.py` automates project creation, terrain attachment, 2D flow
area definition/meshing, the reservoir Storage Area and its embankment
Connection, applying computed breach parameters, initial/boundary
conditions, and running the plan — all verified against the
actually-installed `ras-commander` 0.99.1 API (signatures checked by
inspecting the installed package directly, not assumed).

An earlier version of this section said the breachable embankment
structure had to be created by hand in the HEC-RAS GUI, because
`GeomInlineWeir` (checked at the time) is read-only in 0.99.1. That was
checking the wrong class: `GeomInlineWeir` parses **1D river-station**
inline structures, not the Storage-Area-to-2D-Area connection a 2D
dam-breach model actually needs. `GeomLateral` is the class for that, and
in the installed version it has full read/write support — `set_connection`,
`set_connection_profile`, `set_connection_gates`, `delete_connection`, all
"verified to compute" per its own docstrings against production 2D models.
`ras_project.create_reservoir_storage_area` (writing the reservoir pool's
Storage Area block directly, since no public ras-commander method creates
a plain non-2D storage area) and `create_breach_structure` (wrapping
`GeomLateral.set_connection`/`set_connection_profile`) use it, so the whole
chain from `dam.yaml` to a computed plan is scriptable with no GUI step —
the same resolution `storage_curve.py`'s flood-fill approach already gave
the reservoir-footprint-digitization concern this section used to also
cite: the human-in-the-loop step wasn't actually load-bearing, a real write
API existed, it just hadn't been found yet.

**One real, HEC-RAS-format constraint surfaced while wiring this up**: the
installed `GeomLateral.set_connection` silently fixed-width-truncates
Connection names (and its Up/Dn Storage Area references) to 16 characters.
A name like `"Fall River Reservoir Dam"` (24 chars, `breach_structure_name`'s
human-readable output) gets silently mangled to `"Fall River Reser"`,
which then fails to round-trip against its own untruncated Storage Area
name — caught by actually writing a real connection in a test, not by
inspection. `ras_project.ras_connection_name(dam)` (e.g. `"Dam 070129"`)
is the short, always-safe identifier actually used for the geometry-file
Connection; `create_reservoir_storage_area`/`create_breach_structure` both
raise `ValueError` rather than silently truncate if a caller passes a name
over 16 characters for any Storage-Area/Connection role.

## Key decisions and why

**Reusable toolkit, not a one-off script.** Every dam-specific fact lives in
that dam's `dam.yaml` (`dams/<dam>/dam.yaml`), validated against a shared
schema (`config.py`). Adding a third dam later means writing one new YAML
file, not new code.

**Sunny-day breach (normal pool, no concurrent flood).** This is the
standard baseline assumption for EAP inundation maps and is what DWR's
guidance implicitly assumes throughout (see the Screening/Simple/Advanced
tiers above — none of them require a concurrent hydrologic flood event by
default). It also means HEC-HMS is *not* in the critical path for these two
dams; it's noted as an optional future addition if a combined
flood-plus-breach scenario is ever specifically requested.

**Cascade routing: Loch Lomond → Fall River Reservoir → Idaho Springs.**
Loch Lomond Dam sits 9 miles upstream of Fall River Reservoir Dam on the
same stream (Fall River). A Loch Lomond breach doesn't reach Idaho Springs
directly — it hits Fall River Reservoir first. `ras_project.py` models this
explicitly (Loch Lomond's `dam.yaml` has a `cascade_downstream` block)
rather than treating the two dams as independent, isolated scenarios. This
also means a Loch Lomond failure is analyzed for whether it could
itself threaten Fall River Reservoir (a secondary cascading-failure
question), not just for its attenuated arrival further downstream.

**Existing 2021 LiDAR over public DEM.** Professional-grade LiDAR surveys of
both reservoir sites already exist (commissioned in 2021, apparently for a
reservoir-expansion feasibility study) — see
[`data_sources.md`](data_sources.md). These are higher resolution and more
accurate than anything `terrain.py` would otherwise download from USGS
3DEP, so they're the primary terrain source; public DEM is only a fallback
for the parts of the downstream routing corridor the LiDAR survey doesn't
cover.

**Downstream structures / population-at-risk (PAR) overlay included.**
Per your direction, maps show more than the bare inundation extent —
downstream buildings/roads/populated areas are overlaid, which is both more
useful for emergency responders and is what DWR's Rule 16.1.5.1 implies
("show...urban and rural impacts").

## What "done" looks like

For each dam: a breach-parameter report (all three empirical methods,
cross-checked), a GeoTIFF depth grid, a Shapefile inundation polygon, and a
static PDF/PNG map — all labeled preliminary, all traceable back to the
`dam.yaml` that generated them, ready to hand to a PE for review before
submission to DWR.
