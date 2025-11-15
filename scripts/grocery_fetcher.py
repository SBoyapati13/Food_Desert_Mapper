import osmnx as ox
import geopandas as gpd
import pandas as pd
import logging
from typing import Dict, Union, List, Optional, Tuple
from shapely.geometry import Point, box

from .db_setup import (
    execute_query,
    batch_insert,
    validate_database_environment,
    check_coverage,
    add_coverage,
    get_stores_in_bbox
)
from .utils import (
    ensure_data_directory
)

# Configure logging
from .logger_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

# Set up OSMnx cache directory
CACHE_DIR = ensure_data_directory() / "cache"
ox.settings.cache_folder = str(CACHE_DIR)

# Constants
STORE_TAGS: Dict[str, Union[str, List[str], bool]] = {
    'shop': ['supermarket', 'grocery', 'convenience', 'greengrocer'],
    'amenity': ['marketplace']
}

class GroceryStoreFetcher:
    """
    Handles fetching and storing grocery store data based on geographic bounding boxes.
    """
    def __init__(self) -> None:
        """Initialize the grocery store fetcher."""
        validate_database_environment(['grocery_stores', 'coverage_areas'])

    def _store_exists(self, osm_id: int) -> bool:
        """
        Check if a store already exists in the database by OSM ID.
        
        Args:
            osm_id: OpenStreetMap ID of the store
            
        Returns:
            bool: True if store exists, False otherwise
        """
        query = "SELECT EXISTS(SELECT 1 FROM grocery_stores WHERE osm_id = %s);"
        result = execute_query(query, (osm_id,))
        return bool(result and result[0][0])
    
    def _upsert_store(
        self, 
        osm_id: int,
        store_name: str, 
        shop_type: str, 
        longitude: float,
        latitude: float,
        address: Optional[str] = None
    ) -> None:
        """
        Insert or update a store in the database.
        
        Args:
            osm_id: OpenStreetMap ID
            store_name: Name of the store
            shop_type: Type of shop (supermarket, convenience, etc.)
            longitude: Longitude coordinate
            latitude: Latitude coordinate
            address: Optional address string
        """
        query = """
            INSERT INTO grocery_stores (osm_id, store_name, shop_type, location, address)
            VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)
            ON CONFLICT (osm_id) DO UPDATE
            SET store_name = EXCLUDED.store_name,
                shop_type = EXCLUDED.shop_type,
                location = EXCLUDED.location,
                address = EXCLUDED.address,
                last_updated = CURRENT_TIMESTAMP;
        """
        
        execute_query(query, (osm_id, store_name, shop_type, longitude, latitude, address))

    def fetch_from_osm(self, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
        """
        Fetch grocery stores from OpenStreetMap for a given bounding box.
        
        Args:
            bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
            
        Returns:
            GeoDataFrame containing the fetched stores
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        logger.info(f"Fetching stores from OSM for bbox: {bbox}")
        
        try:
            # Create bbox polygon
            bbox_polygon = box(min_lon, min_lat, max_lon, max_lat)
            
            # Fetch features from OSM
            stores_gdf = ox.features_from_polygon(bbox_polygon, STORE_TAGS)
            
            if stores_gdf.empty:
                logger.info("No stores found in this area")
                return gpd.GeoDataFrame()
            
            # Filter for points only
            stores = stores_gdf[stores_gdf.geometry.type == 'Point'].copy()
            
            if stores.empty:
                logger.info("No point-type stores found in this area")
                return gpd.GeoDataFrame()
            
            # Extract relevant columns
            stores['store_name'] = stores.get('name', 'Unnamed Store')
            stores['shop_type'] = stores.get('shop', 'unknown')
            
            # Get OSM ID from index or osmid column
            if 'osmid' in stores.columns:
                stores['osm_id'] = stores['osmid']
            elif hasattr(stores.index, 'get_level_values'):
                # Multi-index case
                try:
                    stores['osm_id'] = stores.index.get_level_values('osmid')
                except KeyError:
                    stores['osm_id'] = range(len(stores))  # Fallback
            else:
                stores['osm_id'] = stores.index
            
            # Fill missing values
            stores['store_name'].fillna('Unnamed Store', inplace=True)
            stores['shop_type'].fillna('unknown', inplace=True)
            
            # Build address from tags if available
            if 'addr:street' in stores.columns and 'addr:housenumber' in stores.columns:
                stores['address'] = (
                    stores['addr:housenumber'].fillna('').astype(str) + ' ' + 
                    stores['addr:street'].fillna('').astype(str)
                ).str.strip()
            else:
                stores['address'] = None
            
            logger.info(f"Found {len(stores)} stores in OSM")
            return stores
            
        except Exception as e:
            logger.error(f"Error fetching from OSM: {e}")
            return gpd.GeoDataFrame()
        
    def save_stores(self, stores_gdf: gpd.GeoDataFrame) -> int:
        """
        Save stores to the database.
        
        Args:
            stores_gdf: GeoDataFrame containing stores to save
            
        Returns:
            int: Number of stores saved/updated
        """
        if stores_gdf.empty:
            return 0
        
        saved_count = 0
        updated_count = 0
        
        for idx, row in stores_gdf.iterrows():
            try:
                osm_id = int(row['osm_id'])
                store_name = str(row['store_name'])
                shop_type = str(row['shop_type'])
                
                # Get coordinates
                geom = row.geometry
                longitude = geom.x
                latitude = geom.y
                
                address = row.get('address')
                
                # Check if exists
                exists = self._store_exists(osm_id)
                
                # Upsert the store
                self._upsert_store(osm_id, store_name, shop_type, longitude, latitude, address)
                
                if exists:
                    updated_count += 1
                else:
                    saved_count += 1
                    
            except Exception as e:
                logger.error(f"Error saving store {idx}: {e}")
                continue
        
        total = saved_count + updated_count
        logger.info(f"Saved/updated {total} stores ({saved_count} new, {updated_count} updated)")
        return total
    
    def fetch_and_save(self, bbox: Tuple[float, float, float, float]) -> int:
        """
        Fetch stores from OSM for a bounding box and save to database.
        
        Args:
            bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
            
        Returns:
            int: Number of stores saved
        """
        # Check if area already covered
        if check_coverage(bbox):
            logger.info("Area already covered, skipping fetch")
            return 0
        
        # Fetch from OSM
        stores_gdf = self.fetch_from_osm(bbox)
        
        # Save to database
        store_count = self.save_stores(stores_gdf)
        
        # Record coverage
        add_coverage(bbox, store_count)
        
        return store_count
    
def fetch_stores_in_bbox(bbox: Tuple[float, float, float, float]) -> List[Dict]:
    """
    Get all stores in a bounding box, fetching from OSM if not in database.
    
    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
        
    Returns:
        List of dictionaries containing store data
    """
    try:
        # First, check if we need to fetch from OSM
        fetcher = GroceryStoreFetcher()
        fetcher.fetch_and_save(bbox)
        
        # Now get stores from database
        stores_data = get_stores_in_bbox(bbox)
        
        # Convert to list of dicts
        stores = []
        for row in stores_data:
            stores.append({
                'id': row[0],
                'osm_id': row[1],
                'name': row[2],
                'shop_type': row[3],
                'longitude': row[4],
                'latitude': row[5],
                'address': row[6]
            })
        
        logger.info(f"Returning {len(stores)} stores for bbox")
        return stores
        
    except Exception as e:
        logger.error(f"Error in fetch_stores_in_bbox: {e}")
        return []

def get_stores_at_point(
    latitude: float, 
    longitude: float, 
    radius_km: float = 1.0
) -> List[Dict]:
    """
    Get stores within a radius of a point.
    
    Args:
        latitude: Latitude of center point
        longitude: Longitude of center point
        radius_km: Radius in kilometers
        
    Returns:
        List of dictionaries containing store data with distances
    """
    try:
        query = """
            SELECT 
                id,
                osm_id,
                store_name,
                shop_type,
                ST_X(location) as longitude,
                ST_Y(location) as latitude,
                address,
                ST_Distance(
                    location::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) / 1000.0 as distance_km
            FROM grocery_stores
            WHERE ST_DWithin(
                location::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
            )
            ORDER BY distance_km;
        """
        
        radius_meters = radius_km * 1000
        params = (longitude, latitude, longitude, latitude, radius_meters)
        
        result = execute_query(query, params)
        
        stores = []
        for row in result or []:
            stores.append({
                'id': row[0],
                'osm_id': row[1],
                'name': row[2],
                'shop_type': row[3],
                'longitude': row[4],
                'latitude': row[5],
                'address': row[6],
                'distance_km': float(row[7])
            })
        
        return stores
        
    except Exception as e:
        logger.error(f"Error getting stores at point: {e}")
        return []
    
if __name__ == "__main__":
    # Example usage
    try:
        # Example: Fetch stores in New Brunswick, NJ area
        bbox = (-74.47, 40.48, -74.42, 40.52)  # (min_lon, min_lat, max_lon, max_lat)
        
        stores = fetch_stores_in_bbox(bbox)
        print(f"Found {len(stores)} stores in the area")
        
        for store in stores[:5]:  # Print first 5
            print(f"- {store['name']} ({store['shop_type']}) at {store['latitude']}, {store['longitude']}")
            
    except Exception as e:
        logger.error(f"Example failed: {e}")