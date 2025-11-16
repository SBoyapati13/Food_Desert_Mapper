"""
City boundary fetcher for the Food Desert Mapper.

This module handles:
- Fetching city administrative boundaries from OpenStreetMap
- Validating and processing boundary geometries
- Calculating city area metrics
- Handling multiple boundary results
"""

import logging
from typing import Optional, Dict, List, Tuple
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
    which_result: Optional[int] = None
) -> Optional[gpd.GeoDataFrame]:
    """
    Fetch city administrative boundary from OpenStreetMap.
    
    Args:
        city: City name (e.g., "Philadelphia")
        state: State name (e.g., "Pennsylvania")
        country: Country name (default: "USA")
        which_result: If multiple results, specify which one (1-indexed)
        
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
        
        logger.info(f"Successfully fetched boundary for {city}, {state}")
        logger.info(f"Area: {gdf['area_km2'].iloc[0]:.2f} km²")
        
        return gdf
        
    except Exception as e:
        logger.error(f"Error fetching city boundary: {e}")
        return None
    
def fetch_all_city_boundaries(
    city: str,
    state: str,
    country: str = "USA"
) -> Optional[List[gpd.GeoDataFrame]]:
    """
    Fetch all possible boundaries for a city (handles multiple results).
    
    Args:
        city: City name
        state: State name
        country: Country name
        
    Returns:
        List of GeoDataFrames with all matching boundaries, or None if error
    """
    # Validate inputs
    if not validate_inputs(city, state, country):
        return None
    
    try:
        query = build_query_string(city, state, country)
        logger.info(f"Fetching all boundaries for: {query}")
        
        # Fetch all results
        gdf = ox.geocode_to_gdf(query, which_result=None)
        
        if gdf is None or gdf.empty:
            logger.warning(f"No boundaries found for: {query}")
            return None
        
        # If single result, return as list
        if len(gdf) == 1:
            gdf['name'] = city.strip()
            gdf['state'] = state.strip()
            gdf['country'] = country.strip()
            gdf['area_km2'] = calculate_area(gdf)
            
            if 'osmid' in gdf.columns:
                gdf['osm_id'] = gdf['osmid']
            else:
                gdf['osm_id'] = 0
                
            if gdf.crs != 'EPSG:4326':
                gdf = gdf.to_crs('EPSG:4326')
                
            return [gdf]
        
        # Multiple results - split into separate GeoDataFrames
        results = []
        for idx in range(len(gdf)):
            single_gdf = gdf.iloc[[idx]].copy()
            single_gdf['name'] = city.strip()
            single_gdf['state'] = state.strip()
            single_gdf['country'] = country.strip()
            single_gdf['area_km2'] = calculate_area(single_gdf)
            
            if 'osmid' in single_gdf.columns:
                single_gdf['osm_id'] = single_gdf['osmid']
            else:
                single_gdf['osm_id'] = 0
                
            if single_gdf.crs != 'EPSG:4326':
                single_gdf = single_gdf.to_crs('EPSG:4326')
                
            results.append(single_gdf)
        
        logger.info(f"Found {len(results)} boundaries for {city}, {state}")
        return results
        
    except Exception as e:
        logger.error(f"Error fetching boundaries: {e}")
        return None
    
