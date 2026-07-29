"""Per-dam configuration schema (dam.yaml) and loader.

This is the single source of truth an engineer edits by hand for a new dam.
Every other pipeline stage (terrain, breach parameters, HEC-RAS automation,
mapping) reads its inputs from a validated DamConfig instance.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class HazardClass(str, Enum):
    high = "High"
    significant = "Significant"
    low = "Low"
    nph = "NPH"


class FailureMode(str, Enum):
    overtopping = "overtopping"
    piping = "piping"


class Location(BaseModel):
    latitude: float
    longitude: float


class BreachOverride(BaseModel):
    """A PE-reviewed override for one or more regression-derived breach parameters.

    Any field left unset falls back to the toolkit's Froehlich (2016) estimate.
    """

    failure_mode: FailureMode
    width_ft: float | None = None
    side_slope_h_per_v: float | None = None
    formation_time_hr: float | None = None
    note: str | None = None


class SensitivityRange(BaseModel):
    width_ft: tuple[float, float] | None = None
    formation_time_hr: tuple[float, float] | None = None


class CascadeTarget(BaseModel):
    """Identifies a downstream dam that this dam's breach hydrograph must be routed through."""

    dam_id: str
    distance_mi: float
    note: str | None = None


class TerrainSource(BaseModel):
    """A survey-grade terrain deliverable to ingest ahead of any public-DEM fallback."""

    path: str
    kind: str = Field(
        description="e.g. 'lidar_contours_dxf', 'lidar_tin_dxf', 'lidar_points_csv', "
        "'bathymetry_points_csv' (submerged lakebed soundings -- see terrain.py's "
        "build_terrain_from_lidar_and_bathymetry)"
    )
    description: str | None = None


class DamConfig(BaseModel):
    name: str
    state_dam_id: str
    nid_id: str | None = None
    county: str
    stream: str | None = None
    owner: str | None = None
    location: Location
    hazard_class: HazardClass
    embankment_type: str
    year_completed: int

    height_ft: float
    crest_length_ft: float
    crest_width_ft: float | None = None
    crest_elevation_ft: float

    normal_storage_ac_ft: float
    max_storage_ac_ft: float | None = None
    surface_area_ac: float
    drainage_area_ac: float

    spillway_width_ft: float | None = None
    spillway_capacity_cfs: float | None = None

    breach_overrides: list[BreachOverride] = Field(default_factory=list)
    sensitivity: SensitivityRange | None = None
    cascade_downstream: CascadeTarget | None = None
    terrain_sources: list[TerrainSource] = Field(default_factory=list)

    preliminary: bool = True

    @property
    def max_storage_ac_ft_or_normal(self) -> float:
        return self.max_storage_ac_ft if self.max_storage_ac_ft is not None else self.normal_storage_ac_ft


def load_dam_config(path: str | Path) -> DamConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return DamConfig.model_validate(raw)
