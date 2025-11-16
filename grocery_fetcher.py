"""
Grocery store fetcher for the Food Desert Mapper.

This module handles:
- Fetching grocery stores and food retailers from OpenStreetMap
- Filtering and categorizing store types
- Processing store locations within city boundaries
- Deduplicating and validating store data
"""

import logging
from typing import Optional, Dict, List, Any, Union
import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure osmnx settings
ox.settings.log_console = False
ox.settings.use_cache = True

# Define grocery store tags to query from OSM
# Type hint to satisfy type checker for OSMnx
GROCERY_TAGS: Dict[str, Union[bool, str, List[str]]] = {
    'shop': [
        'supermarket',      # Large grocery stores
        'convenience',      # Convenience stores
        'greengrocer',      # Produce/fruit & vegetable stores
        'butcher',          # Meat shops
        'bakery',           # Bakeries
        'deli',             # Delis
        'farm',             # Farm shops
        'health_food',      # Health food stores
        'organic',          # Organic stores
    ],
    'amenity': [
        'marketplace',      # Farmers markets
    ]
}

def fetch_grocery_stores(boundary_gdf: gpd.GeoDataFrame) -> Optional[gpd.GeoDataFrame]:
    """
    Fetch all grocery stores within a city boundary from OpenStreetMap.
    
    Args:
        boundary_gdf: GeoDataFrame containing city boundary polygon
        
    Returns:
        GeoDataFrame with grocery store locations, or None if error
    """
    if boundary_gdf is None or boundary_gdf.empty:
        logger.error("Boundary GeoDataFrame is None or empty")
        return None
    
    try:
        # Get the boundary geometry
        boundary_geom = boundary_gdf.geometry.iloc[0]
        
        if not isinstance(boundary_geom, (Polygon, MultiPolygon)):
            logger.error("Boundary must be a Polygon or MultiPolygon")
            return None
        
        logger.info("Fetching grocery stores from OpenStreetMap...")
        
        # Fetch features from OSM using the boundary polygon
        # Cast to Dict[str, Union[bool, str, List[str]]] to satisfy type checker
        tags: Dict[str, Union[bool, str, List[str]]] = GROCERY_TAGS
        
        stores_gdf = ox.features_from_polygon(
            boundary_geom,
            tags=tags
        )
        
        if stores_gdf is None or stores_gdf.empty:
            logger.warning("No grocery stores found in the boundary")
            return gpd.GeoDataFrame()  # Return empty GeoDataFrame instead of None
        
        logger.info(f"Found {len(stores_gdf)} features from OSM")
        
        # Process the stores
        stores_gdf = process_stores(stores_gdf, boundary_geom)
        
        if stores_gdf is None or stores_gdf.empty:
            logger.warning("No valid grocery stores after processing")
            return gpd.GeoDataFrame()
        
        logger.info(f"Processed {len(stores_gdf)} grocery stores")
        
        return stores_gdf
        
    except Exception as e:
        logger.error(f"Error fetching grocery stores: {e}")
        return None
    
def process_stores(
    stores_gdf: gpd.GeoDataFrame,
    boundary: Union[Polygon, MultiPolygon]
) -> gpd.GeoDataFrame:
    """
    Process raw OSM store data into clean format.
    
    Args:
        stores_gdf: Raw GeoDataFrame from OSM
        boundary: City boundary for filtering
        
    Returns:
        Processed GeoDataFrame with store data
    """
    try:
        # Reset index to make osmid a column
        stores_gdf = stores_gdf.reset_index()
        
        # Extract point geometries (convert ways/polygons to centroids)
        stores_gdf = extract_point_geometries(stores_gdf)
        
        # Filter to only stores within boundary
        stores_gdf = filter_within_boundary(stores_gdf, boundary)
        
        # Standardize shop types
        stores_gdf = standardize_store_types(stores_gdf)
        
        # Extract relevant columns
        stores_gdf = extract_store_info(stores_gdf)
        
        # Deduplicate stores
        stores_gdf = deduplicate_stores(stores_gdf)
        
        # Ensure correct CRS
        if stores_gdf.crs != 'EPSG:4326':
            stores_gdf = stores_gdf.to_crs('EPSG:4326')
        
        return stores_gdf
        
    except Exception as e:
        logger.error(f"Error processing stores: {e}")
        return gpd.GeoDataFrame()
    
def extract_point_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Convert all geometries to points (use centroids for polygons).
    
    Args:
        gdf: GeoDataFrame with mixed geometry types
        
    Returns:
        GeoDataFrame with only Point geometries
    """
    try:
        gdf = gdf.copy()
        
        def to_point(geom):
            if isinstance(geom, Point):
                return geom
            else:
                # For polygons (building footprints), use centroid
                return geom.centroid
        
        gdf['geometry'] = gdf.geometry.map(to_point)
        
        return gdf
        
    except Exception as e:
        logger.error(f"Error extracting point geometries: {e}")
        return gdf
    
def filter_within_boundary(gdf: gpd.GeoDataFrame, boundary: Union[Polygon, MultiPolygon]) -> gpd.GeoDataFrame:
    """
    Filter stores to only those within the city boundary.
    
    Args:
        gdf: GeoDataFrame with store locations
        boundary: City boundary polygon
        
    Returns:
        Filtered GeoDataFrame
    """
    try:
        # Check which points are within the boundary
        within_mask = gdf.geometry.within(boundary)
        
        filtered_gdf = gdf[within_mask].copy()
        
        logger.info(f"Filtered to {len(filtered_gdf)} stores within boundary")
        
        return filtered_gdf
        
    except Exception as e:
        logger.error(f"Error filtering stores: {e}")
        return gdf
    
def standardize_store_types(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Standardize shop type labels from OSM tags.
    
    Args:
        gdf: GeoDataFrame with OSM tags
        
    Returns:
        GeoDataFrame with standardized shop_type column
    """
    try:
        gdf = gdf.copy()
        
        def get_shop_type(row):
            # Check 'shop' tag first
            if 'shop' in row and pd.notna(row['shop']):
                return str(row['shop']).lower()
            # Check 'amenity' tag
            elif 'amenity' in row and pd.notna(row['amenity']):
                return str(row['amenity']).lower()
            else:
                return 'unknown'
        
        gdf['shop_type'] = gdf.apply(get_shop_type, axis=1)
        
        return gdf
        
    except Exception as e:
        logger.error(f"Error standardizing store types: {e}")
        return gdf
    
def extract_store_info(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Extract relevant store information into clean columns.
    
    Args:
        gdf: GeoDataFrame with OSM data
        
    Returns:
        GeoDataFrame with clean columns
    """
    try:
        # Define columns we want to keep
        columns_to_keep = ['osmid', 'name', 'shop_type', 'geometry']
        
        # Create clean dataframe
        clean_data = {}
        
        # OSM ID
        if 'osmid' in gdf.columns:
            clean_data['osm_id'] = gdf['osmid']
        else:
            clean_data['osm_id'] = range(len(gdf))
        
        # Name
        if 'name' in gdf.columns:
            clean_data['name'] = gdf['name'].fillna('')
        else:
            clean_data['name'] = ''
        
        # Shop type (already created)
        clean_data['shop_type'] = gdf['shop_type']
        
        # Geometry
        clean_data['geometry'] = gdf['geometry']
        
        # Create new GeoDataFrame
        clean_gdf = gpd.GeoDataFrame(clean_data, crs=gdf.crs)
        
        return clean_gdf
        
    except Exception as e:
        logger.error(f"Error extracting store info: {e}")
        return gdf
    
def deduplicate_stores(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Remove duplicate stores based on OSM ID.
    
    Args:
        gdf: GeoDataFrame with potential duplicates
        
    Returns:
        Deduplicated GeoDataFrame
    """
    try:
        initial_count = len(gdf)
        
        # Remove duplicates based on osm_id
        gdf = gdf.drop_duplicates(subset=['osm_id'], keep='first')
        
        removed_count = initial_count - len(gdf)
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} duplicate stores")
        
        return gdf
        
    except Exception as e:
        logger.error(f"Error deduplicating stores: {e}")
        return gdf
    
def get_store_counts_by_type(stores_gdf: gpd.GeoDataFrame) -> Dict[str, int]:
    """
    Get count of stores by type.
    
    Args:
        stores_gdf: GeoDataFrame with store data
        
    Returns:
        Dictionary mapping store type to count
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            return {}
        
        counts = stores_gdf['shop_type'].value_counts().to_dict()
        
        return counts
        
    except Exception as e:
        logger.error(f"Error counting stores by type: {e}")
        return {}
    
def filter_stores_by_type(
    stores_gdf: gpd.GeoDataFrame,
    store_types: List[str]
) -> gpd.GeoDataFrame:
    """
    Filter stores to only specified types.
    
    Args:
        stores_gdf: GeoDataFrame with all stores
        store_types: List of store types to keep
        
    Returns:
        Filtered GeoDataFrame
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            return stores_gdf
        
        if not store_types:
            return stores_gdf
        
        filtered = stores_gdf[stores_gdf['shop_type'].isin(store_types)].copy()
        
        logger.info(f"Filtered to {len(filtered)} stores of types: {store_types}")
        
        return filtered
        
    except Exception as e:
        logger.error(f"Error filtering stores by type: {e}")
        return stores_gdf
    
def get_store_summary(stores_gdf: gpd.GeoDataFrame, city_area_km2: float) -> Dict[str, Any]:
    """
    Get summary statistics about stores.
    
    Args:
        stores_gdf: GeoDataFrame with store data
        city_area_km2: City area in square kilometers
        
    Returns:
        Dictionary with summary statistics
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            return {
                'total_stores': 0,
                'stores_per_km2': 0.0,
                'store_types': {},
                'has_data': False
            }
        
        total_stores = len(stores_gdf)
        stores_per_km2 = total_stores / city_area_km2 if city_area_km2 > 0 else 0
        store_types = get_store_counts_by_type(stores_gdf)
        
        summary = {
            'total_stores': total_stores,
            'stores_per_km2': round(stores_per_km2, 2),
            'store_types': store_types,
            'has_data': True
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Error creating store summary: {e}")
        return {
            'total_stores': 0,
            'stores_per_km2': 0.0,
            'store_types': {},
            'has_data': False
        }
    
def validate_stores(stores_gdf: gpd.GeoDataFrame) -> bool:
    """
    Validate that stores GeoDataFrame is valid.
    
    Args:
        stores_gdf: GeoDataFrame with store data
        
    Returns:
        True if valid, False otherwise
    """
    if stores_gdf is None:
        logger.error("Stores GeoDataFrame is None")
        return False
    
    if stores_gdf.empty:
        logger.warning("Stores GeoDataFrame is empty")
        return True  # Empty is valid, just no data
    
    # Check required columns
    required_columns = ['osm_id', 'name', 'shop_type', 'geometry']
    
    for col in required_columns:
        if col not in stores_gdf.columns:
            logger.error(f"Missing required column: {col}")
            return False
    
    # Check geometry column
    if not all(isinstance(geom, Point) for geom in stores_gdf.geometry):
        logger.error("All geometries must be Point objects")
        return False
    
    return True

def get_unique_store_types(stores_gdf: gpd.GeoDataFrame) -> List[str]:
    """
    Get list of unique store types in the dataset.
    
    Args:
        stores_gdf: GeoDataFrame with store data
        
    Returns:
        Sorted list of unique store types
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            return []
        
        unique_types = sorted(stores_gdf['shop_type'].unique().tolist())
        
        return unique_types
        
    except Exception as e:
        logger.error(f"Error getting unique store types: {e}")
        return []
    
# Store type display names for UI
STORE_TYPE_DISPLAY_NAMES = {
    'supermarket': 'Supermarkets',
    'convenience': 'Convenience Stores',
    'greengrocer': 'Produce Stores',
    'butcher': 'Butcher Shops',
    'bakery': 'Bakeries',
    'deli': 'Delis',
    'farm': 'Farm Shops',
    'health_food': 'Health Food Stores',
    'organic': 'Organic Stores',
    'marketplace': 'Farmers Markets',
    'unknown': 'Other'
}

def get_display_name(store_type: str) -> str:
    """
    Get user-friendly display name for a store type.
    
    Args:
        store_type: Internal store type identifier
        
    Returns:
        Display name for UI
    """
    return STORE_TYPE_DISPLAY_NAMES.get(store_type, store_type.title())

if __name__ == "__main__":
    """Test the grocery fetcher with a sample boundary."""
    
    print("=" * 60)
    print("Grocery Fetcher Test")
    print("=" * 60)
    
    # Import city fetcher for testing
    from city_fetcher import fetch_city_boundary
    
    # Fetch a small city for testing
    print("\nFetching boundary for Trenton, New Jersey...")
    boundary_gdf = fetch_city_boundary("Trenton", "New Jersey", "USA")
    
    if boundary_gdf is not None and not boundary_gdf.empty:
        print(f"✓ Boundary fetched successfully")
        
        # Fetch grocery stores
        print("\nFetching grocery stores...")
        stores_gdf = fetch_grocery_stores(boundary_gdf)
        
        if stores_gdf is not None and not stores_gdf.empty:
            print(f"✓ Found {len(stores_gdf)} grocery stores")
            
            # Get summary
            area = boundary_gdf['area_km2'].iloc[0]
            summary = get_store_summary(stores_gdf, area)
            
            print(f"\nSummary:")
            print(f"  Total stores: {summary['total_stores']}")
            print(f"  Density: {summary['stores_per_km2']} stores/km²")
            print(f"\nStore types:")
            for store_type, count in summary['store_types'].items():
                print(f"  {get_display_name(store_type)}: {count}")
        else:
            print("✗ No stores found")
    else:
        print("✗ Failed to fetch boundary")