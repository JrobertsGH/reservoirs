"""Static, EAP-ready inundation map rendering.

Basemap tiles (via contextily) require network access; pass `basemap=False`
to render without them (used by tests, and available as a fallback when
offline). Every rendered map gets a visible "preliminary" watermark in the
figure itself *and* a `.metadata.txt` sidecar file carrying the same
disclaimer in plain text -- the sidecar exists so the label's presence can
be checked mechanically (see `check_preliminary_label_present`) without
depending on how reliably image-format metadata round-trips, which hasn't
been verified.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib_scalebar.scalebar import ScaleBar

from reservoirs.config import DamConfig

PRELIMINARY_FOOTER = (
    "PRELIMINARY -- FOR PE REVIEW. Not a certified engineering deliverable. "
    "See docs/preliminary_disclaimer.md."
)


def _add_north_arrow(ax, x=0.95, y_tip=0.95, y_tail=0.88) -> None:
    ax.annotate(
        "N",
        xy=(x, y_tip),
        xytext=(x, y_tail),
        xycoords="axes fraction",
        textcoords="axes fraction",
        fontsize=14,
        fontweight="bold",
        ha="center",
        arrowprops=dict(arrowstyle="-|>", color="black", lw=2),
    )


def _dam_point_gdf(dam: DamConfig, target_crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": [dam.name]},
        geometry=gpd.points_from_xy([dam.location.longitude], [dam.location.latitude]),
        crs="EPSG:4326",
    ).to_crs(target_crs)


def render_inundation_map(
    dam: DamConfig,
    inundation_gdf: gpd.GeoDataFrame,
    out_path: str | Path,
    scenario_label: str = "Sunny-Day Breach",
    structures_gdf: gpd.GeoDataFrame | None = None,
    basemap: bool = True,
    figsize: tuple[float, float] = (11, 8.5),
    dpi: int = 200,
) -> Path:
    fig, ax = plt.subplots(figsize=figsize)

    if len(inundation_gdf) > 0:
        inundation_gdf.plot(ax=ax, color="#3182bd", alpha=0.55, edgecolor="#08519c", linewidth=0.8, zorder=3)

    if structures_gdf is not None and len(structures_gdf) > 0:
        structures_gdf.plot(ax=ax, color="#de2d26", markersize=8, zorder=4)

    dam_gdf = _dam_point_gdf(dam, inundation_gdf.crs)
    dam_gdf.plot(ax=ax, color="black", marker="^", markersize=100, zorder=5)
    dam_point = dam_gdf.geometry.iloc[0]
    ax.annotate(
        dam.name,
        xy=(dam_point.x, dam_point.y),
        xytext=(8, 8),
        textcoords="offset points",
        fontsize=9,
        fontweight="bold",
        zorder=6,
    )

    if basemap:
        import contextily as cx

        cx.add_basemap(ax, crs=inundation_gdf.crs.to_string(), source=cx.providers.OpenStreetMap.Mapnik)

    ax.set_title(
        f"{dam.name} Dam — Dam-Breach Inundation Map\n"
        f"State Dam ID {dam.state_dam_id} | Hazard Class: {dam.hazard_class.value} | {scenario_label}",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_axis_off()

    ax.add_artist(ScaleBar(1, units="ft", dimension="imperial-length", location="lower right"))
    _add_north_arrow(ax)

    fig.text(0.5, 0.01, PRELIMINARY_FOOTER, ha="center", fontsize=8, style="italic", color="#b30000")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    _write_metadata_sidecar(out_path, dam, scenario_label)
    return out_path


def _write_metadata_sidecar(map_path: Path, dam: DamConfig, scenario_label: str) -> Path:
    sidecar_path = map_path.with_suffix(map_path.suffix + ".metadata.txt")
    sidecar_path.write_text(
        f"Dam: {dam.name}\n"
        f"State Dam ID: {dam.state_dam_id}\n"
        f"Hazard Class: {dam.hazard_class.value}\n"
        f"Scenario: {scenario_label}\n"
        f"Preliminary: {dam.preliminary}\n\n"
        f"{PRELIMINARY_FOOTER}\n",
        encoding="utf-8",
    )
    return sidecar_path


def check_preliminary_label_present(map_path: str | Path) -> bool:
    """Release-blocking check (per docs/methodology.md's verification
    approach): every generated map must carry the preliminary disclaimer.
    """
    map_path = Path(map_path)
    sidecar_path = map_path.with_suffix(map_path.suffix + ".metadata.txt")
    if not sidecar_path.exists():
        return False
    return "PRELIMINARY" in sidecar_path.read_text(encoding="utf-8")
