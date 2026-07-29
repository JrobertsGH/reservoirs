import geopandas as gpd
from shapely.geometry import Point, box

from reservoirs.config import DamConfig, HazardClass, Location
from reservoirs.mapping import check_preliminary_label_present, render_inundation_map


def make_dam(**overrides) -> DamConfig:
    defaults = dict(
        name="Fall River Reservoir",
        state_dam_id="070129",
        county="Clear Creek",
        owner="Agricultural Ditch & Reservoir Company",
        location=Location(latitude=39.819876, longitude=-105.690771),
        hazard_class=HazardClass.high,
        embankment_type="Earth embankment",
        year_completed=1974,
        height_ft=85.0,
        crest_length_ft=840.0,
        crest_elevation_ft=10841.0,
        normal_storage_ac_ft=890.0,
        surface_area_ac=24.0,
        drainage_area_ac=1792.0,
    )
    defaults.update(overrides)
    return DamConfig(**defaults)


def make_inundation_gdf(crs="EPSG:2232"):
    return gpd.GeoDataFrame({"geometry": [box(2_941_500, 1_722_500, 2_943_500, 1_724_500)]}, crs=crs)


class TestRenderInundationMap:
    def test_creates_image_file(self, tmp_path):
        dam = make_dam()
        gdf = make_inundation_gdf()
        out_path = render_inundation_map(dam, gdf, tmp_path / "map.png", basemap=False)

        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_creates_metadata_sidecar_with_disclaimer(self, tmp_path):
        dam = make_dam()
        gdf = make_inundation_gdf()
        out_path = render_inundation_map(dam, gdf, tmp_path / "map.png", basemap=False)

        sidecar = out_path.with_suffix(out_path.suffix + ".metadata.txt")
        assert sidecar.exists()
        content = sidecar.read_text()
        assert "PRELIMINARY" in content
        assert dam.name in content
        assert dam.state_dam_id in content

    def test_check_preliminary_label_present_true_after_render(self, tmp_path):
        dam = make_dam()
        gdf = make_inundation_gdf()
        out_path = render_inundation_map(dam, gdf, tmp_path / "map.png", basemap=False)
        assert check_preliminary_label_present(out_path) is True

    def test_check_preliminary_label_present_false_without_sidecar(self, tmp_path):
        fake_path = tmp_path / "not_rendered.png"
        fake_path.write_bytes(b"not a real image")
        assert check_preliminary_label_present(fake_path) is False

    def test_handles_empty_inundation_extent(self, tmp_path):
        dam = make_dam()
        empty_gdf = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:2232")
        out_path = render_inundation_map(dam, empty_gdf, tmp_path / "map.png", basemap=False)
        assert out_path.exists()

    def test_includes_structures_overlay_without_error(self, tmp_path):
        dam = make_dam()
        gdf = make_inundation_gdf()
        structures = gpd.GeoDataFrame(
            {"geometry": [Point(2_942_500, 1_723_500), Point(2_942_600, 1_723_600)]}, crs="EPSG:2232"
        )
        out_path = render_inundation_map(dam, gdf, tmp_path / "map.png", structures_gdf=structures, basemap=False)
        assert out_path.exists()

    def test_renders_pdf_as_well_as_png(self, tmp_path):
        dam = make_dam()
        gdf = make_inundation_gdf()
        out_path = render_inundation_map(dam, gdf, tmp_path / "map.pdf", basemap=False)
        assert out_path.exists()
        assert check_preliminary_label_present(out_path) is True
