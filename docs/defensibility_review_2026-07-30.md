# Defensibility Review — Breach Modeling Methodology

**Date:** 2026-07-30
**Scope:** Independent, source-grounded review of the breach-parameter and
HEC-RAS modeling approach in this repository (Loch Lomond & Fall River
Reservoir dam-breach inundation analysis for the ADRC EAPs).
**Method:** Every claim traces to a cited source and carries a source-trust
tier (see policy) and a confidence. Where sources disagree — including where
this project disagrees with an authoritative document, or a document
disagrees with itself — both sides are preserved, not silently resolved.
Discrepancies are a primary deliverable, listed in §5.

> This is a methodology review, **not** an engineering certification. Nothing
> here is a PE-stamped conclusion. It is meant to help a reviewing PE and the
> maintainer target the remaining defensibility questions before DWR
> submission. Read alongside [`preliminary_disclaimer.md`](preliminary_disclaimer.md).

---

## 1. Source-trust tiers used in this review

| Tier | Weight | Kind of source | Rationale |
|---|---|---|---|
| **T1** | Highest | Colorado DWR primary regulatory: *Rules & Regulations for Dam Safety and Dam Construction* (2 CCR 402-1); *Guidelines for Dam Breach Analysis* (Feb 10, 2010) | The regulator's own words define what will be accepted. Rules govern *what is required*; the Guideline governs *how* and *with what coefficients*. |
| **T2** | High | Federal / authoritative technical: USACE HEC-RAS Technical Reference; FEMA dam-safety inundation guidance; USBR | The methods and software the guidance is built on; authoritative but general, not Colorado-specific. |
| **T3** | High (literature) | Peer-reviewed primary literature: Froehlich (2008) *JHE* 134(12); MacDonald & Langridge-Monopolis (1984) *JHE* | Original derivations of the empirical equations. Authoritative for *what the equation is*, secondary to T1 for *what Colorado requires*. |
| **T4** | Medium | Professional secondary: ASDSO Dam Safety Toolbox, established consultant guidance (Goodell/Kleinschmidt 2D best-practice) | Reflects accepted practice; not a regulator or primary derivation. |
| **T5** | Low | Informal: search snippets, forum posts, blog paraphrases | Capture-and-verify only. Never a final citation; used only to find a T1–T3 source. |

Scores are **trust in the source, not a claim of present truth.** A T1 value
is "what Colorado's rule/guideline says," not "the correct answer for these
two dams today" — a PE still owns the judgment call and re-verification.

---

## 2. What is verified correct (high confidence)

The load-bearing claims I confirmed against a T1/T2/T3 primary source. This is
the strong core of the project.

### 2.1 Froehlich (2008) English-unit coefficients are mathematically faithful — **CONFIRMED**
Code: `Bavg = 8.239·Ko·Vw^0.32·Hb^0.04`, `Tf = 3.664·√(Vw/(g·Hb²))`, g = 32.2,
Vw in acre-ft, Hb in ft, Tf in hours. Canonical SI (T2 HEC-RAS Tech Ref; T3
Froehlich 2008): `Bavg = 0.27·Ko·Vw^0.32·hb^0.04`, `tf = 63.2·√(Vw/(g·hb²))`.
Hand-conversion SI→English:
- Width: `3.2808 × 0.27 × 1233.48^0.32 × 0.3048^0.04 = 8.239` ✓ (exact)
- Time (SI s → hr, g = 32.2, Vw in ac-ft): `= 3.664` ✓ (exact)

Both reproduce to the digit. **Confidence: high.** DWR 2010 Guideline Table 2
gives these "with English units" (T1, txt line 652/689).

### 2.2 Ko and breach side slopes — **CONFIRMED**
Ko = 1.0 (piping) / 1.3 (overtopping); side slopes 0.7H:1V (piping) / 1.0H:1V
(overtopping). DWR 2010 (T1, txt lines 720, 728, 1038); Froehlich 2008 (T3).
**Confidence: high.**

### 2.3 Validation heuristics and numeric ranges — **CONFIRMED**
- `1.6 ≤ ER/Hw ≤ 21` (ER = Bavg/Tf), database avg 6.7. DWR 2010 (T1, txt
  lines 752–757).
- `Bavg/Hb < 0.6` ⇒ likely piping-only / method suspect. DWR 2010 (T1, txt
  lines 771, 916–918). **Confidence: high.** (DWR self-inconsistency, §5-D.)

### 2.4 Method selection / 100-AF threshold — **CONFIRMED**
Froehlich primary for > 100 AF; MLM / Washington State for < 100 AF cohesive;
run more than one and cross-check (Table 3). Both dams (~875 / ~890–1,050 AF)
exceed 100 AF ⇒ Froehlich-primary correct. DWR 2010 (T1, txt 217, 801, 823).
**Confidence: high.**

### 2.5 Froehlich **2008** over "2016" — **CONFIRMED correct** (but see §4.6)
Colorado's recommended coefficients are the 2008 set; using the regulator's
published coefficients over a newer literature variant is defensible. DWR 2010
(T1). **Confidence: high.** (A stale "2016" reference remains in code — §4.6.)

### 2.6 Sunny-day (fair-weather) basis — **CONFIRMED as the correct Colorado basis** (with a refinement, §4.1)
Colorado Rule 4.13 defines Hazard Classification "by analysis of potential
consequences from a **sunny day failure** of the dam. Conditions for
evaluation are **absent flooding and the reservoir is assumed to be full to
the high water line** at the time of failure." Spillway *size* is the only
thing driven by the Hydrologic Hazard, not the breach/EAP map. **The project's
sunny-day, no-concurrent-flood choice is exactly Colorado's regulatory basis
— not a shortcut.** (T1, 2 CCR 402-1 Rule 4.13, txt lines 123–127.)
**Confidence: high.** The refinement (starting pool tier) is §4.1.

### 2.7 Targeting a 2D unsteady (Advanced-tier) model — **DEFENSIBLE** (frame it, §4.4)
2D unsteady HEC-RAS meets/exceeds DWR's Advanced tier. DWR 2010 Table 1 (T1,
txt line 525). **Confidence: high that 2D qualifies.**

### 2.8 Endorsed process choices
- Empirical breach params primary (not NWS BREACH) — DWR documents BREACH's
  accuracy problems (T1). ✓
- Three methods returned, PE picks — DWR "run more than one" (T1, Table 3). ✓
- SMPDBK peak-discharge vs spillway-capacity sanity check (T1). ✓
- **Plan/Unsteady file made once in the GUI, not by an untested writer**
  (`audit_trail.md` 2026-07-29). For a regulatory model, refusing to fabricate
  an unverified Plan/Unsteady/BC-line file is the *more* defensible choice.
  **Endorsed.**

---

## 3. Scenario coverage — RESOLVED at primary-source level

This was flagged as the top risk on first pass ("do they also need a
flood/PMF breach run?"). **Primary sources resolve it, and largely in the
project's favor:**

- **Rule 4.13 (T1):** the regulatory evaluation basis *is* a sunny-day
  failure, absent flooding, reservoir full to the high water line.
- **Rule 13.7.1.6.1 (T1, txt lines 1526–1537):** the inundation-map
  requirement calls for "the dam breach flood" extent and cross-sections — it
  does **not** mandate a separate flood-induced/PMF breach scenario for the map.

**Conclusion:** a concurrent-flood or PMF breach run is **not required** for
these EAP maps by Colorado rule. Modeling the sunny-day breach only is
compliant. (National multi-scenario *envelope* practice (T4) is a
belt-and-suspenders nicety, not a Colorado requirement — do not treat its
absence as a deficiency.) The real refinements are the *starting pool tier*
(§4.1) and the *required map outputs* (§4.2), both below.

---

## 4. Open defensibility items (resolve before submission)

Ranked by how likely a DWR/PE reviewer is to raise them.

### 4.1 Starting pool should be the HIGH water line, not normal pool — **CONCRETE T1 FINDING**
Rule 4.13 assumes the reservoir **full to the high water line** at failure.
Rule 4.14 (T1, txt line 138): **High Water Line = the emergency spillway
crest.** Rule 4.19 (txt line 157): **Normal Water Line = the service spillway
crest.** The DWR breach guideline is consistent: Hw is measured "from
emergency spillway crest down to breach invert for a full, fair-weather
breach" (T1, guideline txt lines 86–87).

The code's sunny-day initial condition uses `normal_pool_elevation_ft`, whose
own docstring defines it as "typically spillway crest" — i.e. the **service**
spillway crest / normal water line (`config.py` lines 96–105;
`ras_project.configure_initial_and_boundary_conditions`). That is **one
spillway tier below** the regulatory basis, and therefore **less conservative**
(smaller Hw, Vw, breach, and inundation footprint). `DamConfig` has **no
high-water-line / emergency-spillway-crest field** at all.

- **Caveat that can make this a non-issue for a given dam:** Rule 4.19 states
  that if there is *no* service spillway, the normal and high water lines are
  the same. If a dam has only one spillway, `normal_pool_elevation_ft` already
  equals the high water line.
- **Recommendation:** add `high_water_line_ft` (emergency spillway crest) to
  `DamConfig`; drive the sunny-day initial pool and Hw from it; keep
  `normal_pool_elevation_ft` only for the storage-curve cross-check. Confirm
  each dam's emergency spillway crest from its EIR. **Confidence: high that the
  regulatory basis is the high water line; medium on per-dam magnitude until
  each spillway configuration is checked.**

### 4.2 Required map outputs beyond depth/extent — **T1 OUTPUT-COMPLETENESS GAP**
Rule 13.7.1.6.1.B (T1, txt lines 1534–1537) requires cross-sections at
critical locations showing lateral extent, **depth of flooding, arrival time
of the initial and peak flood wave (from start of breach), and flood-wave
velocity.** Rule 13.7.1.6.3 (txt 1542–1545) requires **spillway and outlet
discharge rating tables/curves.**

`postprocess.py` currently derives max water-surface → depth grid →
inundation polygon. It does **not** yet extract **arrival time** (initial and
peak) or **velocity** from the HEC-RAS 2D HDF, and there is no rating-curve
output. These are explicit, enumerated EAP-map requirements, not optional.
- **Recommendation:** extend `postprocess.py` to pull the 2D results' arrival
  time and velocity fields from the HDF, and add cross-section cuts at
  critical locations; add a spillway/outlet rating-curve export. **Confidence:
  high (enumerated in rule).**

### 4.3 Starting-elevation / conservatism sensitivity — **DWR-recommended, partial hook exists**
DWR recommends a **sensitivity analysis on the piping start elevation** to
find the "realistically conservative" result (T1, guideline txt 1265–1269).
The config has a `SensitivityRange` (width, formation time) hook, but not a
start-elevation dimension, and no run currently sweeps it. **Recommendation:**
sweep start elevation / breach timing and report the controlling case.
**Confidence: high that DWR asks for this.**

### 4.4 Frame the 2D method against the 2010 guideline's 1D "rules of thumb" — **DOCUMENT the bridge**
DWR's 2010 HEC-RAS rules-of-thumb (T1, guideline txt 1276–1336) describe the
**1D storage-area + inline-weir** method (v4.0 era). This project uses the
modern **2D flow-area + Storage-Area/2D-connection** method — current best
practice, which resolves a limitation DWR's own text flags for the 1D
storage-area approach: it "does not calculate hydraulic losses as water in
upper portions of the reservoir travels to the dam breach" (T1, txt 1279). A
reviewer anchored on the 2010 doc won't see this as a strength unless told.
**Recommendation:** add a short `methodology.md` paragraph mapping the 2D
SA/2D-connection setup onto Advanced-tier intent, citing line 1279.
**Confidence: high that 2D is defensible; the gap is documentation.**

### 4.5 Breach weir coefficient default 3.0 vs DWR 3.08 — **MINOR, align it**
`create_breach_structure(..., weir_coef=3.0)`. DWR recommends **Cw ≈ 3.08**
(HEC-1 uses 3.1) for the breach/overtopping weir after crest erosion (T1,
guideline txt 1438, 1444). 3.0 is ~3% low; matching costs nothing.
**Recommendation:** default `weir_coef = 3.08` or document the 3.0 choice.
**Confidence: high.**

### 4.6 Stale "Froehlich (2016)" reference in code — **FIX (reviewer-facing)**
`config.py` `BreachOverride` docstring (line 37) says unset fields "fall back
to the toolkit's **Froehlich (2016)** estimate." The project deliberately uses
Froehlich **2008** (§2.5; `breach_models.md`). This leftover from the
abandoned 2016 plan sits in the schema a PE edits and could mislead a reviewer
about which method is in force. **Recommendation:** correct to 2008.
**Confidence: high (verified inconsistency).**

### 4.7 Mesh cell size must resolve the breach — **NOT YET SET (known)**
The breach is ~100+ ft wide; the 2D mesh needs several cells across the breach
opening and along the SA/2D connection, or peak discharge is smeared. General
2D practice (T4) starts at 50–100 ft cells but requires **local refinement at
the breach and in the downstream channel.** **Recommendation:** refine cells
well below the breach width at the connection; run a cell-size sensitivity
check (coarse vs refined peak WSE) and log it. **Confidence: high.**

### 4.8 2D flow-area extent = full terrain rectangle — **KNOWN gap, clip it**
`flow_area_perimeter_from_terrain()` returns the full LiDAR bounding box. The
active 2D area should be **clipped to the downstream corridor**, extended
"downstream to a location where the potential for loss of life and significant
property damage no longer exist" (T1, Rule 13.7.1.6.1.A, txt 1531–1533). An
oversized rectangle wastes cells and can add spurious ponding.
**Recommendation:** clip to the routed corridor — a concrete, low-risk code
contribution. **Confidence: high.**

### 4.9 Spatially-varied Manning's n not wired in — **improvement**
`configure_2d_flow_area()` applies a single `mannings_n = 0.035`. The repo has
`manning_lookup.py` (NLCD-derived spatially-varied n) but it is not fed into
the 2D area. A single n over a mixed forest/urban/channel corridor is a
reviewable simplification. **Recommendation:** wire the NLCD n-grid in, or
document the constant and a sensitivity check. **Confidence: medium-high.**

---

## 5. Discrepancy log (preserved, not resolved)

**A. HEC-RAS documentation is wrong about Froehlich time units; this project
is right.** HEC-RAS's *Estimating Dam Breach Parameters* labels the
`tf = 63.2·√(Vw/(g·hb²))` (SI) result "in hours" (T2). By derivation the 63.2
SI coefficient yields **seconds**; the project's English 3.664 correctly
yields hours (§2.1). **Kept both:** trust the math and Froehlich 2008 (T3),
flag the HEC-RAS doc phrasing as imprecise. A T2 source locally wrong, a
low-ceremony derivation wins — why a score is "trust in the source," not
"truth."

**B. Scenario scope — first-pass concern vs primary source.** Early T4-based
reasoning suggested a flood/PMF breach run might be required. Rule 4.13 +
Rule 13.7.1.6.1 (T1) resolve it: sunny-day only is compliant (§3). **Kept the
trail:** the initial concern is recorded and then overridden by the higher
tier — not deleted, so the reasoning is auditable.

**C. Starting pool: code (normal/service spillway crest) vs Rule 4.13/4.14
(high water line / emergency spillway crest).** A real, unresolved deviation
until per-dam spillway configs are checked (§4.1). Preserved.

**D. DWR internal inconsistency on the erosion-rate floor.** The guideline
states the minimum ER/Hw as **1.6** (txt 752) but also writes the check as
"**1** < ER/Hw < 21" (txt 819). Code uses **1.6** — the more specific,
conservative value. Preserved; flag the source's own inconsistency rather than
silently picking.

**E. Guideline method (1D storage-area, T1) vs project method (2D, T4 current
practice).** The newer, more accurate method departs from the letter of the
2010 rules-of-thumb — an improvement that must be *documented* as such (§4.4).
Preserved.

**F. Weir coefficient 3.0 (code) vs 3.08 (DWR, T1).** Preserved; §4.5.

---

## 6. Bottom line

The **breach-parameter engine is solid and independently verified** — the
equations, coefficients, validation ranges, method-selection thresholds, and
the Froehlich-2008 choice all reproduce against the DWR 2010 guideline (T1)
and primary literature (T2/T3). The **sunny-day basis is confirmed correct at
the rule level (T1), not a shortcut**, and the decision to hand-build the
Plan/Unsteady file rather than fabricate one is the more defensible path. The
in-repo traceability discipline (every equation cited to the guideline) is
genuinely strong.

The **defensibility work left is in HEC-RAS setup fidelity and EAP-map output
completeness**, not the math:

1. **Start the sunny-day pool at the HIGH water line (emergency spillway
   crest), per Rule 4.13/4.14** — add `high_water_line_ft`; current normal-pool
   IC is one tier low / less conservative (§4.1). *Highest priority.*
2. **Produce all rule-required map outputs** — arrival time (initial + peak),
   velocity, critical cross-sections, and spillway/outlet rating curves
   (Rule 13.7.1.6.1.B / .6.3) (§4.2).
3. Add the **start-elevation sensitivity** DWR asks for (§4.3).
4. **Document why 2D supersedes the 2010 doc's 1D rules-of-thumb** (§4.4).
5. Align the **weir coefficient to 3.08** (§4.5); fix the **stale "Froehlich
   2016"** reference (§4.6).
6. **Set/justify mesh cell size at the breach** and **clip the 2D area** to the
   downstream corridor (§4.7–4.8); wire in **spatially-varied Manning's n**
   (§4.9).

None require abandoning the architecture: 1 is a config/IC change the pipeline
already routes; 2–3 are outputs/runs; 4 is documentation; 5, 6, 8–9 are small
code changes.

---

### Source index
- **T1** Colorado DWR, *Rules & Regulations for Dam Safety and Dam
  Construction*, 2 CCR 402-1 — Rules 4.13, 4.14, 4.19 (definitions), 13.7 (EAP
  / inundation mapping). (Retrieved: sos.state.co.us CCR ruleVersionId 8426;
  40 pp. Line refs to extracted text.)
- **T1** Colorado DWR, *Guidelines for Dam Breach Analysis*, Feb 10, 2010.
  (Retrieved: hermes.cde.state.co.us/islandora/object/co:25732; 68 pp.)
- **T2** USACE HEC-RAS 1D Technical Reference, *Performing a Dam-Break Study /
  Estimating Dam Breach Parameters* (v6.5).
- **T3** Froehlich, D.C. (2008), "Embankment Dam Breach Parameters and Their
  Uncertainties," *J. Hydraulic Engineering* 134(12):1708.
- **T3** MacDonald, T.C. & Langridge-Monopolis, J. (1984), "Breaching
  Characteristics of Dam Failures," *J. Hydraulic Engineering*.
- **T4** ASDSO Dam Safety Toolbox — *Breach Scenarios*; 2D Dam Breach Modeling
  best-practice materials (Goodell).
- **T4** FEMA, *Federal Guidelines for Inundation Mapping of Flood Risks
  Associated with Dam Incidents and Failures*.

*All four verified numeric/threshold claims in §2 and the scenario resolution
in §3 now rest on T1 primary text read directly, not on secondary summaries.*
