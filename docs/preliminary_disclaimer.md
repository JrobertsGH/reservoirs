# Preliminary — For PE Review

Every output this toolkit produces (breach-parameter reports, GIS layers,
rendered maps) is a **preliminary technical analysis**, not a certified
engineering deliverable.

Colorado Division of Water Resources (DWR), Dam Safety Branch requires
inundation maps submitted as part of a High or Significant Hazard dam's
Emergency Action Plan (EAP) to reflect sound engineering judgment applied by
a licensed Professional Engineer (PE) — not just the mechanical output of a
regression equation or a hydraulic model run with default assumptions. This
toolkit automates the mechanical parts of that process (breach parameter
estimation, terrain handling, HEC-RAS project setup, GIS post-processing,
map rendering) so a PE can spend their time on judgment calls, not data
wrangling — but it does not replace that judgment.

Before any output from this toolkit is submitted to DWR, a PE must
independently verify, at minimum:

- **Breach parameter selection** — which empirical method (Froehlich 2008,
  MacDonald & Langridge-Monopolis, Washington State) is appropriate for
  this dam's size and storage intensity, and whether the toolkit's
  regression-derived defaults should be overridden (see each dam's
  `breach_overrides` block in its `dam.yaml`).
- **Terrain and geometry adequacy** — whether the 2D mesh resolution and
  extent are sufficient to resolve the downstream valley, and whether the
  reservoir footprint/storage curve match reality.
- **Boundary condition assumptions** — normal-pool sunny-day breach vs. a
  concurrent flood event, base flow, tailwater effects.
- **Results plausibility** — the validation checks this toolkit runs
  automatically (erosion rate, breach-width-to-height ratio, comparison to
  spillway capacity) are necessary but not sufficient; engineering judgment
  is still required.

Every generated file carries a `preliminary: true` flag (from the source
`dam.yaml`) and this same disclaimer text in its metadata/footer. Treat the
absence of that flag on any output as a bug, not a green light.
