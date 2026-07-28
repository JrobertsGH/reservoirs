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

## 2025 Engineer's Inspection Reports (EIRs) — the actual regulatory driver

Found in `C:\Users\jroberts\Downloads\`: `LochLomond_EIR-20250716.pdf` and
`FallRiver_EIR-20250716.pdf` (State Dam IDs 070210 and 070129 — confirmed
correct dams), each far more current than the 2020 EIR previously on the
network share. These are the single most important documents found so far:

- **Confirms the regulatory driver directly, in DWR's own words**: *"The
  current 1996 inundation map for Loch Lomond and Fall River is not
  helpful... The EAP in our records only includes a detailed inundation map
  for the much smaller Lower Chinns dam. A detailed inundation map should be
  developed for Loch Lomond and/or Fall River."* (There's a third dam,
  Lower Chinns, in the same EAP that already has one — not otherwise in
  this project's scope, but a useful reference for format/precedent.)
- **A 2025 GEI Consultants Comprehensive Dam Safety Evaluation (CDSE)**
  identified specific Potential Failure Modes (PFMs) with a formal risk
  matrix for both dams. For **Loch Lomond**: internal erosion/piping along
  the outlet conduit (PFMs 15, 17) rated "poor confidence," near the
  unacceptable-risk boundary. For **Fall River Reservoir**: internal
  erosion through the foundation via contact/scour (PFM #10) is the
  single highest-risk PFM, also "poor confidence," in GEI's unacceptable
  zone. **This means piping/internal-erosion, not overtopping, should be
  the primary failure mode reported for both dams** — see the notes now in
  each `dam.yaml`.
- Corrected Loch Lomond's crest width to 12 ft (previously unset/assumed).
- Both dams remain rated "Conditionally Satisfactory," consistent with the
  2020 Fall River EIR's seepage findings (multiple mapped seep locations,
  a historic sand boil at Fall River's Seep D).

An email thread accompanying these (`Kirch - DNR, Jim` to Peter Acker/
ADRC, Aug 2024) confirms Jim Kirch, P.E. is DWR's Water Division 1 dam
safety engineer for this system, and that EAPs must be updated **annually**
per Rule 13.7.4 — useful contact/process context for the final deliverable.

## A third dam: Lake Caroline

The same 2024/2025 DWR inspection cycle covers **Lake Caroline** (State Dam
ID 070211), sitting immediately upstream of Loch Lomond in the same
drainage, same owner (ADRC). It's Low Hazard, tiny (10 ft dam, 144 AF), and
**EAP/inundation map is explicitly not required** for it under DWR rules.
Added as `dams/lake_caroline/dam.yaml` for cascade/watershed completeness
(it feeds into Loch Lomond) — not because it needs its own breach analysis.
Do not spend Advanced-tier HEC-RAS effort on it unless asked.

## Resolved: Grand County files are unrelated -- ignore

Confirmed with the user (2026-07-28): the reservoirs of interest are the
Clear Creek County dams only. The Grand-County-looking files below are
unrelated to this project and are not used anywhere in this toolkit.

## Ignored (unrelated, do not use) -- previously-flagged ambiguous files

Several files in `C:\Users\jroberts\Downloads\` appear, from their own
internal content, to describe a **different, unrelated "Loch Lomond"** in
**Grand County** (near Granby/Shadow Mountain Reservoir, Upper Colorado
River basin — not Clear Creek County):

- `loch_lomond_breach_analysis.html`, `loch_lomond_breach_analysis_
  summary.json`, `loch_lomond_breach_flood_analysis.geojson`,
  `loch_lomond_inundation.geojson` — the JSON explicitly states
  `"county": "Grand County"`, `"region": "Upper Colorado River Basin"`,
  center coordinates lat 40.85°N (our Loch Lomond is at 39.83°N), and
  downstream impacts to "Granby" and "Kremmling" via "Cascade Creek" —
  none of which match this project's Loch Lomond (Clear Creek County,
  Fall River drainage, Idaho Springs).
- `LOCH_LOMOND_TOPO_10042022.csv` / `.dwg` / `_PTS.pts` — raw coordinates
  fall within the same UTM-13N-style range the mismatched JSON above
  claims for the Grand County site.

However, `CAROLINE_TOPO_10042022.csv`'s raw elevations (~11,874 ft) line up
closely with the *correct*, Clear-Creek-County Lake Caroline's real crest
elevation (11,880 ft, per its verified 2024 EIR) — so it's plausible that
file is genuinely correct while the same-dated "LOCH_LOMOND_TOPO" file
next to it is not, or that both were exported with an unusual/undocumented
coordinate convention. **This is not resolved** — none of these
Downloads topo/breach-analysis files have been used to inform any
`dam.yaml` or terrain source in this project. Before incorporating any of
them: confirm with the user what project/client they actually came from,
since the accompanying JSON's own stated location doesn't match.

## Known data-quality issue: Loch Lomond drainage area

The state record lists Loch Lomond's drainage area as 685 sq mi (438,400
ac) — implausibly larger than Fall River Reservoir's 1,792 ac, even though
Fall River Reservoir sits *downstream* of Loch Lomond on the same stream and
should have the larger contributing area. Flagged as `UNVERIFIED` in
`dams/loch_lomond/dam.yaml`; re-delineate from watershed data (possibly the
`Fall River Watershed Topo.pdf` above) before relying on it for anything.
