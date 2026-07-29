"""Tests for cli.py's argument-parsing/wiring, one per console-script entry
point. Network- or HEC-RAS-dependent fetchers (OSM, NLCD, HDF results) are
monkeypatched with synthetic data -- these tests exercise the CLI wiring
itself (arg parsing, dam.yaml loading, file I/O), not the underlying
network calls, which are covered (or explicitly not covered) by each
module's own tests.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from reservoirs import cli

REPO_ROOT = Path(__file__).parent.parent
FALL_RIVER_YAML = REPO_ROOT / "dams" / "fall_river" / "dam.yaml"


def make_terrain_geotiff(path, size=15, cell_size_ft=5.0, crs="EPSG:2232"):
    elevation = np.fromfunction(
        lambda r, c: 100 + 0.5 * np.sqrt((r - size / 2) ** 2 + (c - size / 2) ** 2), (size, size)
    ).astype("float32")
    transform = from_origin(2_941_000.0, 1_724_500.0, cell_size_ft, cell_size_ft)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs=crs, transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(elevation, 1)
    return path, transform, crs


class TestBreachParamsCmd:
    def test_prints_report_for_all_three_methods(self, capsys):
        cli.breach_params_cmd([str(FALL_RIVER_YAML), "--volume-ac-ft", "890"])
        out = capsys.readouterr().out
        assert "Froehlich (2008)" in out
        assert "MacDonald & Langridge-Monopolis (1984)" in out
        assert "Washington State (2007)" in out
        assert "070129" in out

    def test_defaults_volume_to_dam_storage(self, capsys):
        cli.breach_params_cmd([str(FALL_RIVER_YAML)])
        out = capsys.readouterr().out
        assert "Reservoir volume at breach:" in out


class TestStorageCurveCmd:
    def test_writes_csv_with_expected_columns(self, tmp_path, capsys):
        terrain_path, _, _ = make_terrain_geotiff(tmp_path / "terrain.tif")
        out_csv = tmp_path / "curve.csv"

        cli.storage_curve_cmd([str(terrain_path), "--out", str(out_csv)])

        assert out_csv.exists()
        df = pd.read_csv(out_csv)
        assert {"elevation_ft", "area_ac", "storage_ac_ft", "touches_boundary"} <= set(df.columns)
        assert "Wrote storage curve" in capsys.readouterr().out

    def test_default_out_path_next_to_terrain(self, tmp_path):
        terrain_path, _, _ = make_terrain_geotiff(tmp_path / "terrain.tif")

        cli.storage_curve_cmd([str(terrain_path)])

        assert (tmp_path / "terrain.storage_curve.csv").exists()

    def test_anchor_near_crest_requires_dam_yaml(self, tmp_path):
        terrain_path, _, _ = make_terrain_geotiff(tmp_path / "terrain.tif")

        with pytest.raises(SystemExit):
            cli.storage_curve_cmd([str(terrain_path), "--anchor-near-crest"])

    def test_anchor_near_crest_extends_curve_and_reports_it(self, tmp_path, capsys):
        terrain_path, _, _ = make_terrain_geotiff(tmp_path / "terrain.tif")
        out_csv = tmp_path / "curve.csv"

        cli.storage_curve_cmd(
            [str(terrain_path), "--dam-yaml", str(FALL_RIVER_YAML), "--anchor-near-crest", "--out", str(out_csv)]
        )

        df = pd.read_csv(out_csv)
        assert "anchored" in df.columns
        assert df["anchored"].any()
        assert df.iloc[-1]["elevation_ft"] == pytest.approx(10841.0)  # Fall River's crest elevation
        out = capsys.readouterr().out
        assert "Anchored" in out
        assert "PRELIMINARY" in out


class TestMappingCmd:
    def test_writes_map_image(self, tmp_path, capsys):
        inundation_path = tmp_path / "inundation.shp"
        gpd.GeoDataFrame({"geometry": [box(2_941_500, 1_722_500, 2_943_500, 1_724_500)]}, crs="EPSG:2232").to_file(
            inundation_path
        )
        out_png = tmp_path / "map.png"

        cli.mapping_cmd([str(FALL_RIVER_YAML), "--inundation", str(inundation_path), "--out", str(out_png), "--no-basemap"])

        assert out_png.exists()
        assert "Wrote inundation map" in capsys.readouterr().out


class TestManningLookupCmd:
    def test_calls_fetch_and_writes_geotiff(self, tmp_path, monkeypatch):
        import rioxarray  # noqa: F401 -- registers the .rio accessor
        import xarray as xr

        def fake_fetch(dam, buffer_mi=1.0, year=2021, resolution_m=30):
            data = np.full((5, 5), 0.04)
            x = np.linspace(-105.70, -105.68, 5)
            y = np.linspace(39.83, 39.81, 5)
            return xr.DataArray(data, coords={"y": y, "x": x}, dims=["y", "x"]).rio.write_crs("EPSG:4326")

        monkeypatch.setattr("reservoirs.manning_lookup.fetch_manning_n_grid", fake_fetch)

        out_path = tmp_path / "manning_n.tif"
        cli.manning_lookup_cmd([str(FALL_RIVER_YAML), "--out", str(out_path)])

        assert out_path.exists()


class TestStructuresCmd:
    def test_reports_structures_and_par(self, tmp_path, monkeypatch, capsys):
        inundation_path = tmp_path / "inundation.shp"
        gpd.GeoDataFrame({"geometry": [box(2_941_500, 1_722_500, 2_943_500, 1_724_500)]}, crs="EPSG:2232").to_file(
            inundation_path
        )

        def fake_fetch(dam, buffer_mi=3.0):
            inside = box(2_942_000, 1_723_000, 2_942_100, 1_723_100)
            outside = box(3_000_000, 1_800_000, 3_000_100, 1_800_100)
            return gpd.GeoDataFrame({"geometry": [inside, outside]}, crs="EPSG:2232")

        monkeypatch.setattr("reservoirs.structures.fetch_structures_osm", fake_fetch)

        out_path = tmp_path / "structures.shp"
        cli.structures_cmd(
            [str(FALL_RIVER_YAML), "--inundation", str(inundation_path), "--out", str(out_path)]
        )

        assert out_path.exists()
        reloaded = gpd.read_file(out_path)
        assert len(reloaded) == 1

        out = capsys.readouterr().out
        assert "1 structures" in out
        assert "PAR estimate" in out

    def test_no_structures_found_skips_write(self, tmp_path, monkeypatch, capsys):
        inundation_path = tmp_path / "inundation.shp"
        gpd.GeoDataFrame({"geometry": [box(2_941_500, 1_722_500, 2_943_500, 1_724_500)]}, crs="EPSG:2232").to_file(
            inundation_path
        )

        monkeypatch.setattr(
            "reservoirs.structures.fetch_structures_osm",
            lambda dam, buffer_mi=3.0: gpd.GeoDataFrame({"geometry": []}, crs="EPSG:2232"),
        )

        out_path = tmp_path / "structures.shp"
        cli.structures_cmd([str(FALL_RIVER_YAML), "--inundation", str(inundation_path), "--out", str(out_path)])

        assert not out_path.exists()
        assert "No structures found" in capsys.readouterr().out


class TestPostprocessCmd:
    def test_writes_depth_grid_and_inundation_extent(self, tmp_path, monkeypatch, capsys):
        terrain_path, transform, crs = make_terrain_geotiff(tmp_path / "terrain.tif")

        max_ws_gdf = gpd.GeoDataFrame(
            {"wse": [110.0]},
            geometry=[box(2_941_000, 1_724_425, 2_941_075, 1_724_500)],
            crs=crs,
        )
        monkeypatch.setattr("reservoirs.postprocess.load_max_ws_from_hdf", lambda hdf_path: max_ws_gdf)

        cli.postprocess_cmd(
            [
                str(tmp_path / "fake.hdf"),
                "--wse-column", "wse",
                "--terrain", str(terrain_path),
                "--dam-yaml", str(FALL_RIVER_YAML),
                "--out-dir", str(tmp_path),
            ]
        )

        assert (tmp_path / "depth_grid.tif").exists()
        assert (tmp_path / "inundation_extent.shp").exists()
        assert "Wrote depth grid" in capsys.readouterr().out
