"""Empirical dam-breach parameter estimation.

Implements the three methods Colorado DWR's "Guidelines for Dam Breach
Analysis" (Feb 10, 2010), Table 2, recommends for dams over 100 AF:
Froehlich (2008), MacDonald & Langridge-Monopolis (1984), and Washington
State (2007). Coefficients are transcribed directly from that document, not
reconstructed from memory. English units throughout (ft, ac-ft, hr, cfs),
matching the guideline.

This module produces a preliminary technical estimate only -- see
docs/preliminary_disclaimer.md. A PE must review breach parameter selection
before any DWR submission.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from reservoirs.config import DamConfig, FailureMode

G_FT_S2 = 32.2


@dataclass
class BreachEstimate:
    method: str
    failure_mode: FailureMode
    breach_formation_factor_ac_ft2: float | None
    volume_eroded_yd3: float | None
    average_breach_width_ft: float
    side_slope_h_per_v: float
    formation_time_hr: float
    erosion_rate_ft_per_hr: float
    erosion_rate_over_hw: float
    breach_width_over_height: float
    warnings: list[str]


def _froehlich_2008(vw_ac_ft: float, hb_ft: float, hw_ft: float, failure_mode: FailureMode) -> BreachEstimate:
    ko = 1.3 if failure_mode is FailureMode.overtopping else 1.0
    zb = 1.0 if failure_mode is FailureMode.overtopping else 0.7

    bavg = 8.239 * ko * vw_ac_ft**0.32 * hb_ft**0.04
    tf = 3.664 * math.sqrt(vw_ac_ft / (G_FT_S2 * hb_ft**2))

    return _finalize("Froehlich (2008)", failure_mode, None, None, bavg, zb, tf, hb_ft, hw_ft)


def _macdonald_langridge_monopolis(
    vw_ac_ft: float,
    hb_ft: float,
    hw_ft: float,
    failure_mode: FailureMode,
    crest_width_ft: float,
    upstream_slope_h_per_v: float,
    downstream_slope_h_per_v: float,
    rockfill: bool,
) -> BreachEstimate:
    bff = hw_ft * vw_ac_ft
    ver = 0.714 * bff**0.852 if rockfill else 3.264 * bff**0.77

    w_avg = crest_width_ft + hb_ft * (upstream_slope_h_per_v + downstream_slope_h_per_v) / 2
    bavg = ver / (hb_ft * w_avg)
    zb = 2.0
    tf = 0.016 * ver**0.364

    return _finalize(
        "MacDonald & Langridge-Monopolis (1984)", failure_mode, bff, ver, bavg, zb, tf, hb_ft, hw_ft
    )


def _washington_state(
    vw_ac_ft: float,
    hb_ft: float,
    hw_ft: float,
    failure_mode: FailureMode,
    crest_width_ft: float,
    upstream_slope_h_per_v: float,
    downstream_slope_h_per_v: float,
    cohesionless: bool,
) -> BreachEstimate:
    bff = hw_ft * vw_ac_ft
    ver = 3.75 * bff**0.77 if cohesionless else 2.5 * bff**0.77
    tf = 0.02 * ver**0.36 if cohesionless else 0.036 * ver**0.36

    w_avg = crest_width_ft + hb_ft * (upstream_slope_h_per_v + downstream_slope_h_per_v) / 2
    bavg = ver / (hb_ft * w_avg)
    zb = 2.0

    return _finalize("Washington State (2007)", failure_mode, bff, ver, bavg, zb, tf, hb_ft, hw_ft)


def _finalize(
    method: str,
    failure_mode: FailureMode,
    bff: float | None,
    ver: float | None,
    bavg: float,
    zb: float,
    tf: float,
    hb_ft: float,
    hw_ft: float,
) -> BreachEstimate:
    er = bavg / tf
    er_over_hw = er / hw_ft
    bavg_over_hb = bavg / hb_ft

    warnings = []
    if not (1.6 <= er_over_hw <= 21):
        warnings.append(
            f"ER/Hw = {er_over_hw:.2f} is outside the guideline's validated range (1.6-21); "
            "Tf may be too long or Bavg too small (or vice versa) -- treat this result as suspect."
        )
    if bavg_over_hb < 0.6:
        warnings.append(
            f"Bavg/Hb = {bavg_over_hb:.2f} is below 0.6 -- the guideline suggests this dam may "
            "only develop a piping hole rather than a full breach; consider modeling as a "
            "piping-only failure (sluice gate in HEC-RAS) instead of a full trapezoidal breach."
        )

    return BreachEstimate(
        method=method,
        failure_mode=failure_mode,
        breach_formation_factor_ac_ft2=bff,
        volume_eroded_yd3=ver,
        average_breach_width_ft=bavg,
        side_slope_h_per_v=zb,
        formation_time_hr=tf,
        erosion_rate_ft_per_hr=er,
        erosion_rate_over_hw=er_over_hw,
        breach_width_over_height=bavg_over_hb,
        warnings=warnings,
    )


def storage_intensity(vw_ac_ft: float, hw_ft: float) -> float:
    """SI = Vw/Hw (ac-ft/ft). Used per Table 3 to pick the recommended method."""
    return vw_ac_ft / hw_ft


def smpdbk_peak_discharge(bavg_ft: float, hw_ft: float, tf_hr: float, surface_area_ac: float) -> float:
    """Screening-level peak breach discharge (SMPDBK / Wetmore & Fread 1984), cfs."""
    gamma = 23.4 * surface_area_ac / bavg_ft
    return 3.1 * bavg_ft * hw_ft**1.5 * (gamma / (gamma + tf_hr * math.sqrt(hw_ft))) ** 3


def estimate_all_methods(
    dam: DamConfig,
    failure_mode: FailureMode,
    vw_ac_ft: float,
    hb_ft: float | None = None,
    hw_ft: float | None = None,
    crest_width_ft: float | None = None,
    upstream_slope_h_per_v: float = 3.0,
    downstream_slope_h_per_v: float = 2.0,
    cohesive: bool = True,
) -> dict[str, BreachEstimate]:
    """Run Froehlich (2008), MacDonald & Langridge-Monopolis, and Washington State
    for the given dam/scenario and return all three for comparison, per the
    guideline's recommendation to cross-check methods rather than rely on one.

    hb_ft/hw_ft default to the dam's full height if not given -- an
    approximation for a full-depth breach at normal pool; refine with
    surveyed breach-invert/spillway-crest elevations where available.
    """
    hb_ft = hb_ft if hb_ft is not None else dam.height_ft
    hw_ft = hw_ft if hw_ft is not None else dam.height_ft
    crest_width_ft = crest_width_ft if crest_width_ft is not None else (dam.crest_width_ft or 20.0)
    rockfill = "rock" in dam.embankment_type.lower()

    return {
        "froehlich_2008": _froehlich_2008(vw_ac_ft, hb_ft, hw_ft, failure_mode),
        "macdonald_langridge_monopolis": _macdonald_langridge_monopolis(
            vw_ac_ft, hb_ft, hw_ft, failure_mode, crest_width_ft,
            upstream_slope_h_per_v, downstream_slope_h_per_v, rockfill,
        ),
        "washington_state": _washington_state(
            vw_ac_ft, hb_ft, hw_ft, failure_mode, crest_width_ft,
            upstream_slope_h_per_v, downstream_slope_h_per_v, cohesionless=not cohesive,
        ),
    }
