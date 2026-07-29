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
`Engineering\GIS_FILES\PMF\Projects\AdDitch Mountain Reservoir Tour\`.
**Reviewed 2026-07-29**: these are orientation/locator map exports (a topo
basemap and an aerial/satellite basemap, respectively), each carrying a
single "Fall River Watershed" pin down near Slater/Sherwin/Chinns Lakes and
Fall River Reservoir. No delineated watershed boundary, no acreage figure,
and the main map extent doesn't even include Loch Lomond (only the inset
locator does) — these do not extend topographic coverage toward Idaho
Springs and don't help with drainage-area or terrain questions. A third,
previously-uncatalogued file in the same folder, **`Mountain Res Watershed
Topo.pdf`**, is more useful: a wider hillshade+contour view showing both a
"Loch Lomand Watershed" pin (near Loch Lomond, Lake Caroline, Ohman/Steuart/
Reynolds Lakes) and the "Fall River Watershed" pin, giving good qualitative
context on the small alpine cirque basin upstream of Loch Lomond — but its
green boundary lines are Arapaho National Forest / James Peak Wilderness
administrative boundaries (labeled as such), not a hydrologic delineation,
and it likewise carries no acreage callout.

**`FallRiver_ClearCreek.shp`** (+ `.dbf`/`.prj`/`.shx`/etc.) — `Engineering\
GIS_FILES\PMF\Projects\Quick Maps\Quick Maps\`. **Reviewed 2026-07-29**:
this is a stream **centerline** layer (shapefile geometry type PolyLine),
not a watershed boundary — only 5 features (`Unnamed Stream`, `Clear Creek`
x2, `Fall River`, `AgDitch`), and despite having NHD-style attribute fields
(`FTYPE`, `FCODE`, `STRM_LEVEL`, `METERS`, `FEET`) all of them are
unpopulated/zero. It's evidently a hand-selected set of reaches for
labeling on quick-reference maps, not a hydrologic dataset. It does give one
useful cross-check: its `Fall River` line measures ~49,301 ft (9.3 mi),
consistent with the `cascade_downstream.distance_mi: 9.0` already in
`dams/loch_lomond/dam.yaml`. It gives no drainage-area information and
isn't a substitute for `terrain.py`/`storage_curve.py` inputs.

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

## Ignored (unrelated, do not use) -- the breach-analysis bundle

Four files in `C:\Users\jroberts\Downloads\` describe a **different,
unrelated "Loch Lomond"** in **Grand County** (near Granby/Shadow Mountain
Reservoir, Upper Colorado River basin — not Clear Creek County):
`loch_lomond_breach_analysis.html`, `loch_lomond_breach_analysis_
summary.json`, `loch_lomond_breach_flood_analysis.geojson`,
`loch_lomond_inundation.geojson`. The JSON explicitly states `"county":
"Grand County"`, `"region": "Upper Colorado River Basin"`, center
coordinates lat 40.85°N (our Loch Lomond is at 39.83°N), and downstream
impacts to "Granby" and "Kremmling" via "Cascade Creek." A 2026-07-29
follow-up review found further, independent confirmation: these files'
own derived statistics (~192 ac surface area, ~80,000 ac-ft storage) are
6x/91x larger than this project's real Loch Lomond (31 ac / 875 ac-ft) —
not the same dam by any measure. **Confirmed unrelated, not used.**

## Corrected 2026-07-29: `LOCH_LOMOND_TOPO_10042022.csv` IS genuine Clear Creek County data

Previously grouped with the unrelated batch above because its raw
coordinate range matched the Grand County JSON's stated range. That was
the JSON's location metadata being wrong, not this file: cross-checking
directly (not just against the JSON) shows its 1,321 points (718 marked
`description="BTM"`, i.e. bottom/bathymetric soundings) have an elevation
range of 11,124–11,203 ft — matching this project's real Loch Lomond crest
elevation (11,200 ft) almost exactly, not the Grand County reservoir's
figures. Its `x`/`y` columns are swapped relative to (Easting, Northing)
convention; once swapped, its points fall entirely inside Loch Lomond's
real 2021 LiDAR survey extent (EPSG:2232 bounds
2,945,116–2,952,492 / 1,726,409–1,733,181), and its centroid lands within
~0.15 mi of the dam's recorded lat/lon. This is a genuine 2022-10-04
bathymetric (submerged lakebed) survey of the real Loch Lomond — now
referenced as a `bathymetry_points_csv` terrain source in
`dams/loch_lomond/dam.yaml` (see `terrain.py`'s
`build_terrain_from_lidar_and_bathymetry`, and `audit_trail.md`'s
corresponding entry for the storage-curve impact). The `.dwg`/`_PTS.pts`
siblings are the same survey in other formats; not independently
re-verified, but presumed genuine alongside the CSV.

`CAROLINE_TOPO_10042022.csv`, from the same batch, remains **unresolved**.
Its elevation (~11,874 ft) and bounding-box area both land within a few
percent of Lake Caroline's real figures, but its raw coordinates share the
same undocumented local grid as files proven unrelated — worth revisiting
with the same swap-xy + real-extent cross-check used above, but not done
yet. Do not incorporate it without that check.

## Known data-quality issue: Loch Lomond drainage area

The state record lists Loch Lomond's drainage area as 685 sq mi (438,400
ac) — implausibly larger than Fall River Reservoir's 1,792 ac, even though
Fall River Reservoir sits *downstream* of Loch Lomond on the same stream and
should have the larger contributing area. Flagged as `UNVERIFIED` in
`dams/loch_lomond/dam.yaml`.

**Update, 2026-07-29 — still `UNVERIFIED`, needs PE sign-off before use.**
Neither network-share candidate named above resolved this: the "Fall River
Watershed" PDFs and `FallRiver_ClearCreek.shp` turned out to be a locator
map and a stream-centerline layer, respectively — not watershed boundaries
(see the reviewed descriptions above). The classic USGS StreamStats REST
API (`streamstats.usgs.gov/streamstatsservices/watershed.geojson`) returned
HTTP 404 as of this check and appears to be down or retired, so it could not
be queried directly either.

As a substitute, USGS NLDI (built on the same underlying NHDPlus network
StreamStats uses) delineated the total upstream drainage basin at Loch
Lomond's recorded lat/lon (snapping ~5.8 m onto the mapped flowline) at
**~740 ac (1.16 sq mi)**. That basin polygon correctly contains Lake
Caroline, the known upstream tributary reservoir, which supports the
delineation being basically sound. Running the identical NLDI method on
Fall River Reservoir's own point reproduces ~2,102 ac against its accepted
1,792 ac (+17%), so treat the ~740 ac figure as order-of-magnitude (roughly
700–900 ac), not precise. Also worth noting for anyone building
`terrain.py`'s routing: NLDI's flow network does *not* show Loch Lomond's
flowline as topologically upstream of Fall River Reservoir's snapped point
within 20 km — most likely an artifact of the Agricultural Ditch diversion
(the "AgDitch" feature in `FallRiver_ClearCreek.shp`; same "Agricultural
Ditch & Reservoir Company" that owns both dams) or of medium-resolution
NHDPlus network simplification in this terrain, rather than an error in
Loch Lomond's own local catchment polygon — but it's a reason not to
over-trust NHDPlus/NLDI here without a proper recheck.

`dams/loch_lomond/dam.yaml`'s `drainage_area_ac` has been provisionally
updated from 438,400 to 740.0 with this full evidence trail in its comment,
still marked `UNVERIFIED`. Only one independent quantitative source (NLDI)
was obtained, not the two corroborating sources originally hoped for — the
network-share files gave qualitative context at best. Re-delineating from
the 2021 LiDAR already in `terrain_sources` (far higher resolution than
NHDPlus's ~30 m DEM) and getting PE sign-off is the recommended next step
before this figure is used in the storage curve or any hydrology calc.
