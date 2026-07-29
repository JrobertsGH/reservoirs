import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from reservoirs.postprocess import (
    check_downstream_connectivity,
    check_max_depth_plausible,
    compute_depth_grid,
    extract_inundation_polygon,
    rasterize_max_ws,
    write_depth_geotiff,
    write_inundation_shapefile,
)


class TestComputeDepthGrid:
    def test_depth_is_difference_where_positive(self):
        max_ws = np.array([[105.0, 110.0]])
        terrain = np.array([[100.0, 108.0]])
        depth = compute_depth_grid(max_ws, terrain)
        assert np.allclose(depth, [[5.0, 2.0]])

    def test_negative_depth_floored_at_zero(self):
        max_ws = np.array([[100.0]])
        terrain = np.array([[105.0]])  # terrain above water -> dry
        depth = compute_depth_grid(max_ws, terrain)
        assert depth[0, 0] == 0.0

    def test_nan_propagates(self):
        max_ws = np.array([[np.nan, 110.0]])
        terrain = np.array([[100.0, 108.0]])
        depth = compute_depth_grid(max_ws, terrain)
        assert np.isnan(depth[0, 0])
        assert depth[0, 1] == 2.0


class TestRasterizeMaxWs:
    def test_rasterizes_polygon_value_onto_terrain_grid(self, tmp_path):
        terrain_path = tmp_path / "terrain.tif"
        transform = from_origin(0, 100, 10, 10)
        with rasterio.open(
            terrain_path, "w", driver="GTiff", height=10, width=10, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(np.zeros((10, 10), dtype="float32"), 1)

        # A polygon covering the left half of the raster, WSE = 105.0
        poly = box(0, 0, 50, 100)
        gdf = gpd.GeoDataFrame({"max_ws": [105.0]}, geometry=[poly], crs="EPSG:2232")

        raster = rasterize_max_ws(gdf, "max_ws", terrain_path)

        assert raster.shape == (10, 10)
        assert np.allclose(raster[:, :5], 105.0)  # left half covered
        assert np.isnan(raster[:, 5:]).all()  # right half uncovered

    def test_reprojects_when_crs_differs(self, tmp_path):
        # Point given in lon/lat -- find its true EPSG:2232 location first so
        # the terrain raster below is built to actually contain it (rather
        # than guessing a real-world correspondence and getting it wrong).
        point_gdf = gpd.GeoDataFrame({"max_ws": [11400.0]}, geometry=[Point(-105.69, 39.82)], crs="EPSG:4326")
        reprojected_point = point_gdf.to_crs("EPSG:2232").geometry.iloc[0]

        terrain_path = tmp_path / "terrain.tif"
        transform = from_origin(reprojected_point.x - 1000.0, reprojected_point.y + 1000.0, 200.0, 200.0)
        with rasterio.open(
            terrain_path, "w", driver="GTiff", height=10, width=10, count=1,
            dtype="float32", crs="EPSG:2232", transform=transform, nodata=np.nan,
        ) as dst:
            dst.write(np.zeros((10, 10), dtype="float32"), 1)

        raster = rasterize_max_ws(point_gdf, "max_ws", terrain_path)
        assert not np.isnan(raster).all()  # something landed after reprojection


class TestExtractInundationPolygon:
    def test_thresholds_and_dissolves_flooded_cells(self):
        depth = np.array([[0.0, 0.0, 0.0], [0.0, 2.0, 2.0], [0.0, 2.0, 2.0]])
        transform = from_origin(0, 30, 10, 10)
        gdf = extract_inundation_polygon(depth, transform, crs="EPSG:2232", depth_threshold_ft=0.1)
        assert len(gdf) >= 1
        assert gdf.geometry.iloc[0].area > 0

    def test_all_dry_returns_empty_geodataframe(self):
        depth = np.zeros((3, 3))
        transform = from_origin(0, 30, 10, 10)
        gdf = extract_inundation_polygon(depth, transform, crs="EPSG:2232")
        assert len(gdf) == 0

    def test_nan_cells_excluded(self):
        depth = np.array([[np.nan, 5.0], [5.0, 5.0]])
        transform = from_origin(0, 20, 10, 10)
        gdf = extract_inundation_polygon(depth, transform, crs="EPSG:2232", depth_threshold_ft=0.1)
        assert len(gdf) >= 1


class TestWriteOutputs:
    def test_write_depth_geotiff_round_trips(self, tmp_path):
        depth = np.array([[1.0, 2.0], [3.0, 4.0]], dtype="float32")
        transform = from_origin(0, 20, 10, 10)
        out_path = write_depth_geotiff(depth, transform, tmp_path / "sub" / "depth.tif", crs="EPSG:2232")
        with rasterio.open(out_path) as src:
            assert np.array_equal(src.read(1), depth)

    def test_write_inundation_shapefile(self, tmp_path):
        gdf = gpd.GeoDataFrame({"geometry": [box(0, 0, 10, 10)]}, crs="EPSG:2232")
        out_path = write_inundation_shapefile(gdf, tmp_path / "sub" / "inundation.shp")
        assert out_path.exists()
        reloaded = gpd.read_file(out_path)
        assert len(reloaded) == 1


class TestCheckDownstreamConnectivity:
    def test_no_warning_for_single_connected_body(self):
        depth = np.array([[5.0, 5.0, 0.0], [0.0, 5.0, 5.0], [0.0, 0.0, 5.0]])
        assert check_downstream_connectivity(depth, seed_rc=(0, 0)) == []

    def test_warns_on_disconnected_island(self):
        depth = np.zeros((10, 10))
        depth[0:2, 0:2] = 5.0  # main body at the seed
        depth[8:10, 8:10] = 5.0  # disconnected island far away, same size as main body
        warnings = check_downstream_connectivity(depth, seed_rc=(0, 0))
        assert len(warnings) == 1
        assert "disconnected" in warnings[0]

    def test_warns_when_seed_itself_is_dry(self):
        depth = np.array([[0.0, 0.0], [0.0, 5.0]])
        warnings = check_downstream_connectivity(depth, seed_rc=(0, 0))
        assert len(warnings) == 1
        assert "not itself flooded" in warnings[0]

    def test_warns_when_entirely_dry(self):
        depth = np.zeros((3, 3))
        warnings = check_downstream_connectivity(depth, seed_rc=(0, 0))
        assert len(warnings) == 1
        assert "entirely dry" in warnings[0]


class TestCheckMaxDepthPlausible:
    def test_no_warning_within_tolerance(self):
        depth = np.array([[50.0, 60.0]])
        assert check_max_depth_plausible(depth, dam_height_ft=85.0) == []

    def test_warns_when_depth_implausibly_exceeds_dam_height(self):
        depth = np.array([[500.0]])
        warnings = check_max_depth_plausible(depth, dam_height_ft=85.0, tolerance_factor=1.5)
        assert len(warnings) == 1
        assert "exceeds" in warnings[0]
