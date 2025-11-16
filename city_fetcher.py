"""
City boundary fetcher for the Food Desert Mapper.

This module handles:
- Fetching city administrative boundaries from OpenStreetMap
- Validating and processing boundary geometries
- Calculating city area metrics
- Handling multiple boundary results
"""

import logging
from typing import Optional, Dict, Any, Tuple
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure osmnx settings
ox.settings.log_console = False
ox.settings.use_cache = True

def validate_inputs(city: str, state: str, country: str) -> bool:
    """
    Validate city fetcher inputs.
    
    Args:
        city: City name
        state: State name
        country: Country name
        
    Returns:
        True if valid, False otherwise
    """
    if not city or not city.strip():
        logger.error("City name cannot be empty")
        return False
    
    if not state or not state.strip():
        logger.error("State name cannot be empty")
        return False
    
    if not country or not country.strip():
        logger.error("Country name cannot be empty")
        return False
    
    return True

def build_query_string(city: str, state: str, country: str) -> str:
    """
    Build OSM query string for geocoding.
    
    Args:
        city: City name
        state: State name
        country: Country name
        
    Returns:
        Formatted query string
    """
    # For US cities, include state for better disambiguation
    if country.upper() == 'USA':
        return f"{city.strip()}, {state.strip()}, USA"
    else:
        # For international cities
        return f"{city.strip()}, {state.strip()}, {country.strip()}"
    
def fetch_city_boundary(
    city: str,
    state: str,
    country: str = "USA",
    which_result: Optional[int] = 1
) -> Optional[gpd.GeoDataFrame]:
    """
    Fetch city administrative boundary from OpenStreetMap.
    
    Args:
        city: City name (e.g., "Philadelphia")
        state: State name (e.g., "Pennsylvania")
        country: Country name (default: "USA")
        which_result: Which result to return if multiple matches (1-indexed, default: 1)
                     Use None to get all results in a single GeoDataFrame
        
    Returns:
        GeoDataFrame with city boundary or None if not found
    """
    # Validate inputs
    if not validate_inputs(city, state, country):
        return None
    
    try:
        # Build query string
        query = build_query_string(city, state, country)
        logger.info(f"Fetching boundary for: {query}")
        
        # Fetch boundary from OSM
        # which_result=None will return the first result
        # which_result=1 will also return the first result
        # which_result=2 will return the second result, etc.
        gdf = ox.geocode_to_gdf(query, which_result=which_result)
        
        if gdf is None or gdf.empty:
            logger.warning(f"No boundary found for: {query}")
            return None
        
        # Add metadata
        gdf['name'] = city.strip()
        gdf['state'] = state.strip()
        gdf['country'] = country.strip()
        
        # Calculate area
        gdf['area_km2'] = calculate_area(gdf)
        
        # Extract OSM ID from the 'osmid' column if it exists
        if 'osmid' in gdf.columns:
            gdf['osm_id'] = gdf['osmid']
        else:
            gdf['osm_id'] = 0
        
        # Ensure we're using EPSG:4326 (WGS84)
        if gdf.crs != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
        
        num_results = len(gdf)
        logger.info(f"Successfully fetched {num_results} boundary(ies) for {city}, {state}")
        if num_results == 1:
            logger.info(f"Area: {gdf['area_km2'].iloc[0]:.2f} km²")
        
        return gdf
        
    except Exception as e:
        logger.error(f"Error fetching city boundary: {e}")
        return None
    
def validate_boundary(gdf: gpd.GeoDataFrame) -> bool:
    """
    Validate that a boundary GeoDataFrame is valid and usable.
    
    Args:
        gdf: GeoDataFrame containing boundary
        
    Returns:
        True if valid, False otherwise
    """
    if gdf is None or gdf.empty:
        logger.error("GeoDataFrame is None or empty")
        return False
    
    if 'geometry' not in gdf.columns:
        logger.error("GeoDataFrame has no geometry column")
        return False
    
    # Check that geometry is valid
    geom = gdf.geometry.iloc[0]
    
    if geom is None:
        logger.error("Geometry is None")
        return False
    
    # Type check for Shapely geometry
    if not isinstance(geom, (Polygon, MultiPolygon)):
        logger.error(f"Geometry must be Polygon or MultiPolygon, got {type(geom)}")
        return False
    
    if not geom.is_valid:
        logger.error("Geometry is not valid")
        return False
    
    # Check that it's not empty
    if geom.is_empty:
        logger.error("Geometry is empty")
        return False
    
    return True

def calculate_area(gdf: gpd.GeoDataFrame) -> float:
    """
    Calculate area of a boundary in square kilometers.
    
    Args:
        gdf: GeoDataFrame with boundary geometry
        
    Returns:
        Area in square kilometers
    """
    try:
        # Convert to a projected CRS for accurate area calculation
        # Use UTM zone automatically based on centroid
        gdf_projected = gdf.to_crs(gdf.estimate_utm_crs())
        
        # Calculate area in square meters, convert to km²
        area_m2 = gdf_projected.geometry.area.iloc[0]
        area_km2 = area_m2 / 1_000_000
        
        return round(area_km2, 2)
        
    except Exception as e:
        logger.error(f"Error calculating area: {e}")
        return 0.0
    
def get_boundary_info(gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
    """
    Extract summary information about a boundary.
    
    Args:
        gdf: GeoDataFrame with boundary
        
    Returns:
        Dictionary with boundary metadata
    """
    if gdf is None or gdf.empty:
        return {}
    
    row = gdf.iloc[0]
    
    info = {
        'name': row.get('name', 'Unknown'),
        'state': row.get('state', 'Unknown'),
        'country': row.get('country', 'Unknown'),
        'osm_id': row.get('osm_id', 0),
        'area_km2': row.get('area_km2', 0.0),
        'bbox': row.geometry.bounds if hasattr(row.geometry, 'bounds') else None,
        'display_name': row.get('display_name', ''),
        'place_type': row.get('class', 'unknown')
    }
    
    return info

def get_boundary_center(gdf: gpd.GeoDataFrame) -> Optional[Tuple[float, float]]:
    """
    Get the center point (centroid) of a boundary.
    
    Args:
        gdf: GeoDataFrame with boundary
        
    Returns:
        Tuple of (latitude, longitude) or None if error
    """
    try:
        if gdf is None or gdf.empty:
            return None
        
        geom = gdf.geometry.iloc[0]
        
        # Type check for Shapely geometry
        if not isinstance(geom, (Polygon, MultiPolygon)):
            logger.error("Geometry must be Polygon or MultiPolygon")
            return None
        
        centroid = geom.centroid
        return (centroid.y, centroid.x)  # (lat, lon)
        
    except Exception as e:
        logger.error(f"Error calculating centroid: {e}")
        return None
    
def simplify_boundary(
    gdf: gpd.GeoDataFrame,
    tolerance: float = 0.001
) -> gpd.GeoDataFrame:
    """
    Simplify boundary geometry to reduce complexity.
    Useful for large cities with very detailed boundaries.
    
    Args:
        gdf: GeoDataFrame with boundary
        tolerance: Simplification tolerance in degrees (default: 0.001)
        
    Returns:
        GeoDataFrame with simplified geometry
    """
    try:
        if gdf is None or gdf.empty:
            return gdf
        
        gdf_simplified = gdf.copy()
        gdf_simplified.geometry = gdf_simplified.geometry.simplify(
            tolerance,
            preserve_topology=True
        )
        
        logger.info(f"Simplified boundary with tolerance {tolerance}")
        return gdf_simplified
        
    except Exception as e:
        logger.error(f"Error simplifying boundary: {e}")
        return gdf
    
def ensure_multipolygon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Ensure geometry is a MultiPolygon (required for database storage).
    
    Args:
        gdf: GeoDataFrame with boundary
        
    Returns:
        GeoDataFrame with MultiPolygon geometry
    """
    try:
        if gdf is None or gdf.empty:
            return gdf
        
        gdf_copy = gdf.copy()
        
        # Convert Polygon to MultiPolygon if needed
        def to_multipolygon(geom):
            if isinstance(geom, Polygon):
                return MultiPolygon([geom])
            elif isinstance(geom, MultiPolygon):
                return geom
            else:
                logger.warning(f"Unexpected geometry type: {type(geom)}")
                return geom
        
        # Apply to each geometry in the GeoSeries
        gdf_copy['geometry'] = gdf_copy.geometry.map(to_multipolygon)
        
        return gdf_copy
        
    except Exception as e:
        logger.error(f"Error converting to MultiPolygon: {e}")
        return gdf
    
# US States list for validation and dropdown
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "District of Columbia"
]

if __name__ == "__main__":
    """Test the city fetcher with example cities."""
    
    print("=" * 60)
    print("City Fetcher Test")
    print("=" * 60)
    
    # Test cities
    test_cities = [
        ("Philadelphia", "Pennsylvania", "USA"),
        ("San Francisco", "California", "USA"),
        ("Austin", "Texas", "USA")
    ]
    
    for city, state, country in test_cities:
        print(f"\nFetching boundary for {city}, {state}...")
        
        gdf = fetch_city_boundary(city, state, country)
        
        if gdf is not None:
            info = get_boundary_info(gdf)
            print(f"✓ Success!")
            print(f"  Area: {info['area_km2']} km²")
            print(f"  OSM ID: {info['osm_id']}")
            
            center = get_boundary_center(gdf)
            if center:
                print(f"  Center: {center[0]:.4f}, {center[1]:.4f}")
        else:
            print(f"✗ Failed to fetch boundary")