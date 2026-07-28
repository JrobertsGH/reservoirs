# Data Sources

Where every fact in `dams/*/dam.yaml` came from, what else exists but isn't
ingested yet, and what's still missing.

## Public records

**Colorado dam inventory** — `data.colorado.gov`, Socrata dataset
`mgjv-xmr5` (queried via its JSON API). Gave both dams' NID ID, state Dam
ID, location, hazard class, height, storage, surface area, drainage area,
EAP/inundation-map-on-file dates.

- Loch Lomond: NID 00199, State Dam ID 070210, hazard class High, EAP dated
  2017-10-01, inundation map on file dated **1997-01-01**.
- Fall River Reservoir: NID 00193, State Dam ID 070129, hazard class High,
  EAP dated 2017-10-01, inundation map on file dated **1997-01-01**.

**Colorado DWR "Guidelines for Dam Breach Analysis" (Feb 10, 2010)** —
`hermes.cde.state.co.us/islandora/object/co:25732`. The source for every
breach-parameter equation in [`breach_models.md`](breach_models.md), and for
the tiered-analysis framework in [`methodology.md`](methodology.md).

## Internal records (`\\ORION\Departments`)

Found by searching the company's own network share once it became clear
CMWC supports ADRC's dam safety work (see the folder `Engineering\
RESERVOIRS\ADRC- Reservoirs\`, matching "Agricultural Ditch & Reservoir
Company," the owner of record on both dams).

**2020-07-20 Engineer's Inspection Report, Fall River Dam** (State Dam ID
070129) — `Water Resources\Ditch Operations & Ownership\Agricultural
Ditch_Welch Ditch\FallRiver070129_EIR-20200720.pdf`. Confirmed dam
geometry (crest width 20 ft, crest elevation 10,841 ft — not available from
the public record), and gave current condition: rated **"Conditionally
Satisfactory"** due to slowly worsening toe/left-groin seepage; the state
directed the owner to retain an engineer for a toe-drain fix. This is EAP
narrative context, not a breach-parameter input, but worth citing in the
final report.

**2021 LiDAR surveys, both reservoirs** —
`Engineering\RESERVOIRS\ADRC- Reservoirs\Fall River\CCLiDAR_FallRiver_
20211018\` and `...\Loch Lomond\Topo-2021\...\CCLiDAR_LochLomond_20211018\`.
Each contains 2ft and 5ft contour DXFs, an ALL_LAYERS DXF, a TIN DXF, and a
raw point-cloud CSV — professional-grade survey data, referenced in
`dam.yaml`'s `terrain_sources` block for both dams, and the planned primary
terrain source for `terrain.py` (not yet built). Appears to have been
commissioned for a "Mountain Reservoir Expansion" feasibility study (see the
sibling folder of that name, which has its own cover PDFs) — likely covers
the reservoir/dam vicinity well but not necessarily the full downstream
routing corridor to Idaho Springs.

**`Fall River Watershed Topo.pdf` / `Fall River Watershed.pdf`** —
`Engineering\GIS_FILES\PMF\Projects\AdDitch Mountain Reservoir Tour\`. Not
yet opened/reviewed — worth checking early in `terrain.py` development
whether these extend topographic coverage down toward Idaho Springs, which
would reduce or eliminate the need to fall back to public USGS 3DEP data
for that reach.

**`FallRiver_ClearCreek.shp`** (+ `.dbf`/`.prj`/`.shx`/etc.) — `Engineering\
GIS_FILES\PMF\Projects\Quick Maps\Quick Maps\`. An existing GIS shapefile
for the Fall River/Clear Creek area; not yet opened to see what it actually
contains (watershed boundary? stream network? something else). Worth a
look before building `terrain.py`/`storage_curve.py` from scratch.

**Other files found, not yet reviewed for breach-relevant content:**
- `1988_Preliminary Investigation Loch Lomond Reservoir Group.pdf` —
  `Water Resources\Scans\`. "Reservoir Group" in the title suggests this
  historical study may cover both Loch Lomond and Fall River Reservoir
  together.
- `Loch Lomond Flow Measurement Alternatives_5Aug2021.pdf` and `2020
  Inspection - Loch Lomond.pdf` / `...Pictures.pdf` — `Water Resources\
  Ditch Operations & Ownership\Agricultural Ditch_Welch Ditch\`.
- `LochLomond21H264 (1).mov` — `Engineering\GIS_FILES\PMF\Misc\`. Video,
  possibly drone footage of the dam/reservoir.

## Known gap: the actual 1997 inundation map / 2017 EAP documents

Unlike CMWC's other reservoirs (Fairmount, Fortune, Maple Grove, Smart,
Welton — which have EAP `.docx` files directly in `Water Resources\Dam
Emergency Action Plans\`), **no EAP document or inundation map file for
Loch Lomond or Fall River Reservoir has been found on the share** — only
the supporting engineering data listed above. The state record confirms
both documents exist (dated 2017-10-01 and 1997-01-01 respectively), so
they're on file *somewhere* — likely with DWR directly, or in ADRC's own
separate records rather than CMWC's share. Worth requesting from DWR or
ADRC early: even a crude 1997-vintage inundation extent is a useful sanity
check against this toolkit's output.

## Known data-quality issue: Loch Lomond drainage area

The state record lists Loch Lomond's drainage area as 685 sq mi (438,400
ac) — implausibly larger than Fall River Reservoir's 1,792 ac, even though
Fall River Reservoir sits *downstream* of Loch Lomond on the same stream and
should have the larger contributing area. Flagged as `UNVERIFIED` in
`dams/loch_lomond/dam.yaml`; re-delineate from watershed data (possibly the
`Fall River Watershed Topo.pdf` above) before relying on it for anything.
