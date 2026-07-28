# Breach Parameter Models

Implemented in [`src/reservoirs/breach_params.py`](../src/reservoirs/breach_params.py),
tested in [`tests/test_breach_params.py`](../tests/test_breach_params.py).

All three empirical methods below are transcribed directly from Colorado
DWR's **"Guidelines for Dam Breach Analysis" (Feb 10, 2010), Table 2** —
verified against the source PDF, not reconstructed from memory. This
matters: an earlier draft of this project's plan assumed a "Froehlich
(2016)" update should be used instead, on the theory that it was newer and
better-regarded. Reading DWR's actual guidance directly showed that
Colorado's own recommended method is **Froehlich (2008)**, not 2016 — so
that's what's implemented. When a regulator publishes exact coefficients,
use theirs.

All equations use **English units** throughout: feet, acre-feet, hours,
cubic feet per second — matching the guideline exactly, to avoid unit-
conversion bugs.

## Why three models, not one

DWR's guidance doesn't pick a single winner — it recommends running more
than one and cross-checking (their Table 3 maps dam size × storage
intensity to a recommended combination). `estimate_all_methods()` always
returns all three so nothing is thrown away; picking which one to trust for
a given dam is exactly the kind of judgment call a PE should make (see
[`preliminary_disclaimer.md`](preliminary_disclaimer.md)).

## Shared variables

| Symbol | Meaning | Units |
|---|---|---|
| `Hb` | Height of breach — vertical distance, dam crest to breach invert | ft |
| `Hw` | Max depth of water stored behind the breach (spillway crest to breach invert, full pool) | ft |
| `Vw` | Reservoir volume at `Hw` | ac-ft |
| `BFF` | Breach Formation Factor = `Hw × Vw` — a rough proxy for the reservoir's erosive potential | ac-ft² |
| `Ver` | Volume of embankment eroded during the breach | yd³ |
| `Bavg` | Average breach width (at the trapezoid's mid-height, `Hb/2`) | ft |
| `Zb` | Breach side slopes, `Zb`(H) : 1(V) | ft/ft |
| `Tf` | Breach formation time | hr |
| `Wavg` | Average dam width in the direction of flow at `Hb/2`, `= C + Hb·(Zu+Zd)/2` | ft |
| `C` | Dam crest width | ft |
| `Zu`, `Zd` | Upstream/downstream embankment slopes | ft/ft |
| `Ko` | Froehlich failure-mode factor: 1.3 overtopping, 1.0 piping | — |

`Hb`/`Hw` default to the dam's surveyed height (`dam.yaml`'s `height_ft`) if
not given explicitly — an approximation for a full-depth breach at normal
pool. This should be refined with actual breach-invert/spillway-crest
elevations once survey data supports it (see the `data_sources.md` gap on
the original 1997 studies).

---

## 1. Froehlich (2008)

*"Embankment Dam Breach Parameters and Their Uncertainties," Journal of
Hydraulic Engineering, Vol. 134, No. 12 — built from 74 case histories.*

**DWR's recommended primary method** for Small or Large dams with volume
> 100 AF — both Loch Lomond (875 AF) and Fall River Reservoir (890–1,050 AF)
qualify. Depends only on reservoir volume and breach height — no dam
geometry or soil type required, which makes it robust when detailed
geotechnical data isn't available (our situation for both dams currently).

```
Bavg = 8.239 · Ko · Vw^0.32 · Hb^0.04
Tf   = 3.664 · sqrt(Vw / (g · Hb²))          g = 32.2 ft/s²

Zb = 1.0  (overtopping)   Ko = 1.3
Zb = 0.7  (piping)        Ko = 1.0
```

Implemented in `_froehlich_2008()`.

---

## 2. MacDonald & Langridge-Monopolis (1984)

*"Breaching Characteristics of Dam Failures," Journal of Hydraulic
Engineering — the original systematic study, 42 case histories.*

DWR recommends this (with Washington State's failure-time refinement) for
**Minor and Small dams under 100 AF built with cohesive material** — neither
of our dams strictly qualifies (both exceed 100 AF), but it's computed
regardless as a cross-check, per DWR's own case-study practice.

Unlike Froehlich, this method explicitly uses **dam geometry** (crest
width, embankment slopes) to convert an eroded *volume* into a breach
*width* — it distinguishes rockfill from earthen embankments via the BFF
exponent.

```
BFF = Hw · Vw
Ver = 3.264 · BFF^0.77    (earthen/cohesive)
Ver = 0.714 · BFF^0.852   (rockfill)

Bavg = Ver / (Hb · Wavg)
Zb   = 2.0
Tf   = 0.016 · Ver^0.364
```

Implemented in `_macdonald_langridge_monopolis()`. Because it needs
`Wavg` (and therefore crest width + embankment slopes), and neither dam's
`dam.yaml` yet has surveyed slope data, the code defaults to typical
earthfill slopes (3:1 upstream, 2:1 downstream) per DWR's own Table 5 note
that those are "typical" — override via `upstream_slope_h_per_v` /
`downstream_slope_h_per_v` once real geometry is known.

---

## 3. Washington State (2007)

*Washington State Dept. of Ecology, "Dam Safety Guidelines, Technical Note
1" — a refinement of MacDonald & Langridge-Monopolis distinguishing
cohesive from cohesionless embankment material.*

```
BFF = Hw · Vw
Ver = 3.75 · BFF^0.77   (cohesionless)
Ver = 2.5  · BFF^0.77   (cohesive)

Bavg = Ver / (Hb · Wavg)     (same geometry relationship as MLM)
Zb   = 2.0
Tf   = 0.02  · Ver^0.36   (cohesionless)
Tf   = 0.036 · Ver^0.36   (cohesive)
```

Implemented in `_washington_state()`. Both dams are treated as cohesive by
default (`cohesive=True` in `estimate_all_methods()`) — earthen embankments
built in the 1960s–70s are commonly cohesive-core, but this is exactly the
kind of assumption a PE should confirm against as-built records or a
geotechnical report before relying on it.

---

## Screening cross-check: SMPDBK peak discharge

*Wetmore & Fread (1984), "The NWS Simplified Dam Break Flood Forecasting
Model."*

Not a breach-*parameter* method — it takes breach parameters (from any of
the three above) and estimates peak outflow directly, without needing a full
hydrograph. DWR uses this at the Screening tier and also as a sanity check
at higher tiers: peak discharge should come out to a large multiple of the
dam's spillway capacity (1,200 cfs for Loch Lomond, 6,400 cfs for Fall River
Reservoir) — if it doesn't, something upstream is wrong.

```
γ  = 23.4 · As / Bavg                    As = reservoir surface area (ac)
Qp = 3.1 · Bavg · Hw^1.5 · (γ / (γ + Tf·sqrt(Hw)))³
```

Implemented as `smpdbk_peak_discharge()`.

---

## Built-in validation heuristics (DWR Section 7.1.1)

`_finalize()` runs two checks from the guideline on every estimate and
attaches human-readable warnings rather than silently returning a suspect
number:

1. **Erosion rate check.** `ER = Bavg / Tf`; the guideline's own case-study
   database supports `1.6 ≤ ER/Hw ≤ 21`. Outside that range, either `Tf` is
   too long or `Bavg` too small (or vice versa).
2. **Piping-only check.** If `Bavg / Hb < 0.6`, the guideline notes the dam
   may only develop a piping hole that drains the reservoir *without* a full
   crest collapse — a different (and simpler) failure mode than a full
   trapezoidal breach, which changes how it should be modeled in HEC-RAS
   (a sluice gate rather than a breach structure).

## What isn't implemented (by design, for now)

- **NWS BREACH** and other physically-based models — DWR's guidance
  documents specific, significant accuracy problems with BREACH (premature
  crest collapse, ignored head-cutting) and recommends it only for small/
  minor dams as a secondary check, not primary analysis. Not worth the
  added complexity for two Large/Small dams already covered by the three
  empirical methods above.
- **HEC-HMS hydrologic breach routing** — see
  [`methodology.md`](methodology.md) for why the sunny-day/Advanced-tier
  approach doesn't need it for these two dams.
