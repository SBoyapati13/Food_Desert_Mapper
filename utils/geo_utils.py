"""
Geometry processing utilities for the Food Desert Mapper.

Provides functions for working with geographic data,
including distance calculations and geometry manipulation.
"""

import logging
from typing import Tuple, Optional, Union
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union
import traceback

logger = logging.getLogger(__name__)

def calculate_distance(
    point1: Tuple[float, float],
    point2: Tuple[float, float]
) -> float:
    """
    Calculate distance between two points in kilometers using Haversine formula.
    
    Args:
        point1: (latitude, longitude) tuple
        point2: (latitude, longitude) tuple
        
    Returns:
        Distance in kilometers
    """
    from math import radians, sin, cos, sqrt, atan2
    
    lat1, lon1 = point1
    lat2, lon2 = point2
    
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert to radians
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    distance = R * c
    
    return round(distance, 2)

def get_bbox_from_gdf(gdf: gpd.GeoDataFrame) -> Tuple[float, float, float, float]:
    """
    Get bounding box from a GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        
    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)
    """
    try:
        bounds = gdf.total_bounds  # Returns [minx, miny, maxx, maxy]
        return (bounds[0], bounds[1], bounds[2], bounds[3])
    except Exception as e:
        logger.error(f"Error getting bounding box: {e}")
        return (-180, -90, 180, 90)
    
def get_centroid(gdf: gpd.GeoDataFrame) -> Optional[Tuple[float, float]]:
    """
    Get centroid of a GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame
        
    Returns:
        (latitude, longitude) tuple or None if error
    """
    try:
        if gdf is None or gdf.empty:
            return None
        
        geom = gdf.geometry.iloc[0]
        
        # Type check for Shapely geometry
        if not isinstance(geom, (Point, Polygon, MultiPolygon)):
            logger.error("Geometry must be a valid Shapely geometry")
            return None
        
        centroid = geom.centroid
        return (centroid.y, centroid.x)
    
    except Exception as e:
        logger.error(f"Error calculating centroid: {e}")
        return None
    
def simplify_geometry(
    gdf: gpd.GeoDataFrame,
    tolerance: float = 0.001
) -> gpd.GeoDataFrame:
    """
    Simplify geometries in a GeoDataFrame.
    
    Args:
        gdf: GeoDataFrame with geometries
        tolerance: Simplification tolerance in degrees
        
    Returns:
        GeoDataFrame with simplified geometries
    """
    try:
        if gdf is None or gdf.empty:
            return gdf
        
        gdf_simplified = gdf.copy()
        gdf_simplified['geometry'] = gdf_simplified.geometry.simplify(
            tolerance,
            preserve_topology=True
        )
        
        return gdf_simplified
    except Exception as e:
        logger.error(f"Error simplifying geometry: {e}")
        return gdf
    
def buffer_geometry(
    gdf: gpd.GeoDataFrame,
    distance_meters: float
) -> gpd.GeoDataFrame:
    """
    Create a buffer around geometries.
    
    Args:
        gdf: GeoDataFrame with geometries
        distance_meters: Buffer distance in meters
        
    Returns:
        GeoDataFrame with buffered geometries
    """
    try:
        if gdf is None or gdf.empty:
            logger.warning("Empty GeoDataFrame provided for buffering")
            return gdf
        
        # Create a copy to avoid modifying the original
        gdf_copy = gdf.copy()
        
        # Ensure we're in WGS84 first
        if gdf_copy.crs is None:
            gdf_copy = gdf_copy.set_crs('EPSG:4326')
        elif gdf_copy.crs != 'EPSG:4326':
            gdf_copy = gdf_copy.to_crs('EPSG:4326')
        
        # Estimate UTM CRS for accurate buffering
        utm_crs = gdf_copy.estimate_utm_crs()
        logger.info(f"Using UTM CRS for buffering: {utm_crs}")
        
        # Convert to projected CRS for accurate buffering
        gdf_projected = gdf_copy.to_crs(utm_crs)
        
        # Create buffer
        gdf_projected['geometry'] = gdf_projected.geometry.buffer(distance_meters)
        
        # Convert back to WGS84
        gdf_buffered = gdf_projected.to_crs('EPSG:4326')
        
        logger.info(f"Created buffer of {distance_meters}m around {len(gdf)} geometries")
        return gdf_buffered
        
    except Exception as e:
        logger.error(f"Error buffering geometry: {e}")
        logger.error(traceback.format_exc())
        return gdf
    
def merge_geometries(gdf: gpd.GeoDataFrame) -> Optional[Union[Polygon, MultiPolygon]]:
    """
    Merge all geometries in a GeoDataFrame into a single geometry.
    
    Args:
        gdf: GeoDataFrame with multiple geometries
        
    Returns:
        Single merged Polygon/MultiPolygon or None if error
    """
    try:
        if gdf is None or gdf.empty:
            return None
        
        merged = unary_union(gdf.geometry)
        
        # Ensure result is Polygon or MultiPolygon
        if isinstance(merged, (Polygon, MultiPolygon)):
            return merged
        else:
            logger.warning(f"Merge resulted in unexpected type: {type(merged)}")
            return None
        
    except Exception as e:
        logger.error(f"Error merging geometries: {e}")
        return None
    
def find_nearest_store(
    point: Tuple[float, float],
    stores_gdf: gpd.GeoDataFrame
) -> Optional[Tuple[int, float]]:
    """
    Find the nearest store to a given point.
    
    Args:
        point: (latitude, longitude) tuple
        stores_gdf: GeoDataFrame with store locations
        
    Returns:
        Tuple of (store_index, distance_km) or None if no stores
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            return None
        
        # Create Point geometry
        point_geom = Point(point[1], point[0])  # Point(lon, lat)
        
        # Calculate distances using Haversine for accuracy
        distances = []
        for idx, store in stores_gdf.iterrows():
            store_lat = store.geometry.y
            store_lon = store.geometry.x
            dist = calculate_distance(point, (store_lat, store_lon))
            distances.append((idx, dist))
        
        # Find minimum
        if not distances:
            return None
        
        min_item = min(distances, key=lambda x: x[1])
        return min_item
        
    except Exception as e:
        logger.error(f"Error finding nearest store: {e}")
        return None
    
def count_stores_in_radius(
    point: Tuple[float, float],
    stores_gdf: gpd.GeoDataFrame,
    radius_km: float
) -> int:
    """
    Count stores within a radius of a point.
    
    Args:
        point: (latitude, longitude) tuple
        stores_gdf: GeoDataFrame with store locations
        radius_km: Search radius in kilometers
        
    Returns:
        Number of stores within radius
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            return 0
        
        # Count stores within radius using Haversine distance
        count = 0
        for idx, store in stores_gdf.iterrows():
            store_lat = store.geometry.y
            store_lon = store.geometry.x
            dist = calculate_distance(point, (store_lat, store_lon))
            if dist <= radius_km:
                count += 1
        
        return count
        
    except Exception as e:
        logger.error(f"Error counting stores in radius: {e}")
        return 0
    
def validate_crs(gdf: gpd.GeoDataFrame, expected_crs: str = 'EPSG:4326') -> bool:
    """
    Validate that a GeoDataFrame has the expected CRS.
    
    Args:
        gdf: GeoDataFrame to check
        expected_crs: Expected CRS (default: EPSG:4326)
        
    Returns:
        True if CRS matches, False otherwise
    """
    try:
        if gdf is None or gdf.empty:
            return False
        
        return str(gdf.crs) == expected_crs
    except Exception as e:
        logger.error(f"Error validating CRS: {e}")
        return False
    
def reproject_to_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Reproject a GeoDataFrame to WGS84 (EPSG:4326).
    
    Args:
        gdf: GeoDataFrame to reproject
        
    Returns:
        Reprojected GeoDataFrame
    """
    try:
        if gdf is None or gdf.empty:
            return gdf
        
        if gdf.crs != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
        
        return gdf
    except Exception as e:
        logger.error(f"Error reprojecting to WGS84: {e}")
        return gdf

def calculate_coverage_percentage(
    stores_gdf: gpd.GeoDataFrame,
    boundary_gdf: gpd.GeoDataFrame,
    radius_meters: float
) -> dict:
    """
    Calculate what percentage of a city is within walking distance of stores.
    
    Args:
        stores_gdf: GeoDataFrame with store locations
        boundary_gdf: GeoDataFrame with city boundary
        radius_meters: Walking distance radius in meters
        
    Returns:
        Dictionary with coverage statistics
    """
    default_result = {
        'covered_area_km2': 0.0,
        'total_area_km2': 0.0,
        'coverage_percentage': 0.0,
        'uncovered_area_km2': 0.0
    }
    
    try:
        if stores_gdf is None or stores_gdf.empty:
            return default_result
        
        if boundary_gdf is None or boundary_gdf.empty:
            return default_result
        
        # Create buffers around stores
        buffered_stores = buffer_geometry(stores_gdf, radius_meters)
        
        # Merge all buffers
        merged_buffers = unary_union(buffered_stores.geometry)
        
        # Get city boundary as a proper Shapely geometry
        city_boundary_geom = boundary_gdf.geometry.iloc[0]
        
        # Ensure it's a valid Shapely geometry
        if not isinstance(city_boundary_geom, (Polygon, MultiPolygon)):
            logger.error(f"City boundary is not a valid geometry: {type(city_boundary_geom)}")
            return default_result
        
        # Calculate intersection using Shapely directly
        covered_area_geom = merged_buffers.intersection(city_boundary_geom)
        
        # Create GeoDataFrames with proper geometry lists
        covered_gdf = gpd.GeoDataFrame(
            {'id': [1]}, 
            geometry=gpd.GeoSeries([covered_area_geom]), 
            crs='EPSG:4326'
        )
        city_gdf = gpd.GeoDataFrame(
            {'id': [1]}, 
            geometry=gpd.GeoSeries([city_boundary_geom]), 
            crs='EPSG:4326'
        )
        
        utm_crs = covered_gdf.estimate_utm_crs()
        covered_projected = covered_gdf.to_crs(utm_crs)
        city_projected = city_gdf.to_crs(utm_crs)
        
        covered_area_km2 = covered_projected.geometry.area.iloc[0] / 1_000_000
        total_area_km2 = city_projected.geometry.area.iloc[0] / 1_000_000
        
        coverage_pct = (covered_area_km2 / total_area_km2) * 100 if total_area_km2 > 0 else 0
        
        return {
            'covered_area_km2': round(covered_area_km2, 2),
            'total_area_km2': round(total_area_km2, 2),
            'coverage_percentage': round(coverage_pct, 1),
            'uncovered_area_km2': round(total_area_km2 - covered_area_km2, 2)
        }
        
    except Exception as e:
        logger.error(f"Error calculating coverage: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return default_result
    
if __name__ == "__main__":
    """Test geometry utilities."""
    print("=" * 60)
    print("Geometry Utilities Test")
    print("=" * 60)
    
    # Test distance calculation
    print("\nDistance Calculation:")
    philly = (39.9526, -75.1652)
    nyc = (40.7128, -74.0060)
    distance = calculate_distance(philly, nyc)
    print(f"  Philadelphia to New York: {distance} km")
    
    # Test with sample GeoDataFrame
    print("\nGeoDataFrame Operations:")
    sample_points = [
        Point(-75.1652, 39.9526),
        Point(-74.0060, 40.7128),
        Point(-71.0589, 42.3601)
    ]
    sample_gdf = gpd.GeoDataFrame(
        {'city': ['Philadelphia', 'New York', 'Boston']},
        geometry=sample_points,
        crs='EPSG:4326'
    )
    
    bbox = get_bbox_from_gdf(sample_gdf)
    print(f"  Bounding box: {bbox}")
    
    centroid = get_centroid(sample_gdf)
    print(f"  Centroid: {centroid}")
    
    crs_valid = validate_crs(sample_gdf)
    print(f"  CRS valid: {crs_valid}")
    
    # Test buffer
    print("\nBuffer Test:")
    buffered = buffer_geometry(sample_gdf, 1000)  # 1km buffer
    print(f"  Created {len(buffered)} buffered geometries")
    print(f"  Buffer type: {type(buffered.geometry.iloc[0])}")