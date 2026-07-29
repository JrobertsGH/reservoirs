import geopandas as gpd
from shapely.geometry import Point, box

from reservoirs.structures import (
    DEFAULT_PERSONS_PER_STRUCTURE,
    estimate_population_at_risk,
    structures_to_points,
    structures_within_inundation,
    write_structures_shapefile,
)

CRS = "EPSG:2232"


def make_inundation_gdf():
    return gpd.GeoDataFrame({"geometry": [box(2_941_500, 1_722_500, 2_943_500, 1_724_500)]}, crs=CRS)


def make_structures_gdf(geoms, crs=CRS):
    return gpd.GeoDataFrame({"geometry": geoms}, crs=crs)


class TestStructuresWithinInundation:
    def test_keeps_structures_intersecting_extent(self):
        inundation = make_inundation_gdf()
        inside = box(2_942_000, 1_723_000, 2_942_100, 1_723_100)
        outside = box(3_000_000, 1_800_000, 3_000_100, 1_800_100)
        structures = make_structures_gdf([inside, outside])

        result = structures_within_inundation(structures, inundation)

        assert len(result) == 1
        assert result.geometry.iloc[0].equals(inside)

    def test_empty_structures_returns_empty(self):
        inundation = make_inundation_gdf()
        structures = make_structures_gdf([])

        result = structures_within_inundation(structures, inundation)

        assert len(result) == 0

    def test_empty_inundation_returns_empty(self):
        empty_inundation = gpd.GeoDataFrame({"geometry": []}, crs=CRS)
        structures = make_structures_gdf([box(2_942_000, 1_723_000, 2_942_100, 1_723_100)])

        result = structures_within_inundation(structures, empty_inundation)

        assert len(result) == 0

    def test_reprojects_mismatched_crs(self):
        inundation = make_inundation_gdf()
        inside = box(2_942_000, 1_723_000, 2_942_100, 1_723_100)
        structures = make_structures_gdf([inside], crs=CRS).to_crs("EPSG:4326")

        result = structures_within_inundation(structures, inundation)

        assert len(result) == 1
        assert result.crs == inundation.crs


class TestStructuresToPoints:
    def test_converts_polygons_to_centroids(self):
        square = box(0, 0, 10, 10)
        structures = make_structures_gdf([square])

        points = structures_to_points(structures)

        assert len(points) == 1
        assert isinstance(points.geometry.iloc[0], Point)
        assert (points.geometry.iloc[0].x, points.geometry.iloc[0].y) == (5.0, 5.0)

    def test_handles_empty_input(self):
        structures = make_structures_gdf([])
        points = structures_to_points(structures)
        assert len(points) == 0


class TestEstimatePopulationAtRisk:
    def test_counts_structures_and_scales_by_default_factor(self):
        structures = make_structures_gdf([box(0, 0, 1, 1), box(2, 2, 3, 3), box(4, 4, 5, 5)])

        result = estimate_population_at_risk(structures)

        assert result["structure_count"] == 3
        assert result["persons_per_structure"] == DEFAULT_PERSONS_PER_STRUCTURE
        assert result["estimated_par"] == round(3 * DEFAULT_PERSONS_PER_STRUCTURE)

    def test_custom_persons_per_structure(self):
        structures = make_structures_gdf([box(0, 0, 1, 1), box(2, 2, 3, 3)])

        result = estimate_population_at_risk(structures, persons_per_structure=4.0)

        assert result["estimated_par"] == 8

    def test_zero_structures_gives_zero_par(self):
        structures = make_structures_gdf([])
        result = estimate_population_at_risk(structures)
        assert result == {"structure_count": 0, "persons_per_structure": DEFAULT_PERSONS_PER_STRUCTURE, "estimated_par": 0}


class TestWriteStructuresShapefile:
    def test_writes_readable_shapefile(self, tmp_path):
        structures = make_structures_gdf([Point(2_942_000, 1_723_000)])
        out_path = write_structures_shapefile(structures, tmp_path / "sub" / "structures.shp")

        assert out_path.exists()
        reloaded = gpd.read_file(out_path)
        assert len(reloaded) == 1
