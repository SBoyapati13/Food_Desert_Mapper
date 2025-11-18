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
            return gdf
        
        # Convert to projected CRS for accurate buffering
        gdf_projected = gdf.to_crs(gdf.estimate_utm_crs())
        
        # Create buffer
        gdf_projected['geometry'] = gdf_projected.geometry.buffer(distance_meters)
        
        # Convert back to WGS84
        gdf_buffered = gdf_projected.to_crs('EPSG:4326')
        
        return gdf_buffered
    except Exception as e:
        logger.error(f"Error buffering geometry: {e}")
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
        
        # Calculate distances
        distances = stores_gdf.geometry.distance(point_geom)
        
        # Find minimum
        min_idx = distances.idxmin()
        min_distance = distances.loc[min_idx]
        
        # Convert index to int if it's not already
        if not isinstance(min_idx, int):
            min_idx = int(min_idx)
        
        # Convert to kilometers (rough approximation)
        # 1 degree ≈ 111 km at equator
        distance_km = min_distance * 111
        
        return (min_idx, round(distance_km, 2))
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
        
        # Create Point geometry
        point_geom = Point(point[1], point[0])  # Point(lon, lat)
        
        # Convert radius to degrees (rough approximation)
        radius_deg = radius_km / 111.0
        
        # Calculate distances
        distances = stores_gdf.geometry.distance(point_geom)
        
        # Count stores within radius
        count = (distances <= radius_deg).sum()
        
        return int(count)
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