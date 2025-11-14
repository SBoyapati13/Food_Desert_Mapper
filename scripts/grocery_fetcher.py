import osmnx as ox
import geopandas as gpd
import pandas as pd
import logging
from typing import Dict, Union, List, Optional, Tuple

from .db_setup import (
    execute_query,
    batch_insert,
    validate_database_environment,
    get_entity_id,
    check_entity_exists
)
from .utils import (
    ensure_data_directory,
    validate_string_input
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
    def _get_city_id(self, city_name: str, country_name: Optional[str] = None) -> Optional[int]:
        """
        Get city ID from database.
        
        Args:
            city_name: Name of the city
            country_name: Optional name of the country
            
        Returns:
            Optional[int]: City ID if found, None otherwise
            
        Raises:
            ValueError: If city_name is invalid
        """
        validate_string_input(city_name, "city_name")
        validate_string_input(country_name, "country_name", allow_none=True)
        
        return get_entity_id(
            table='city_boundaries',
            name_field='city_name',
            name=city_name,
            extra_field='country_name' if country_name else None,
            extra_value=country_name
        )

    def _get_store_id(self, store_name: str, location: str, city_id: int) -> Optional[int]:
        """
        Get store ID if it exists in database.
        
        Args:
            store_name: Name of the store
            location: WKT representation of store location
            city_id: ID of the city where the store is located
            
        Returns:
            Optional[int]: Store ID if exists, None otherwise
        """
        validate_string_input(store_name, "store_name")
        validate_string_input(location, "location")

        if not isinstance(city_id, int) or city_id <= 0:
            raise ValueError("city_id must be a positive integer")
            
        query = """
            SELECT id FROM grocery_stores 
            WHERE store_name = %s 
            AND ST_Equals(location, ST_GeomFromText(%s, 4326))
            AND city_id = %s
        """
        result = execute_query(query, (store_name, location, city_id))
        return result[0][0] if result else None
        
    def _store_needs_update(self, store_id: int, store_name: str, shop_type: str, location: str) -> bool:
        """
        Check if store data needs to be updated.
        
        Args:
            store_id: ID of the store
            store_name: Current store name
            shop_type: Current shop type
            location: Current WKT location
            
        Returns:
            bool: True if store needs update, False otherwise
        """
        query = """
            SELECT store_name, shop_type, ST_AsText(location) as location
            FROM grocery_stores 
            WHERE id = %s
        """
        result = execute_query(query, (store_id,))
        if not result:
            return False
            
        db_name, db_type, db_location = result[0]
        return (
            db_name != store_name or
            db_type != shop_type or
            not db_location == location  # Compare WKT strings
        )
        
    def _update_store(self, store_id: int, store_name: str, shop_type: str, location: str) -> None:
        """
        Update store data in database.
        
        Args:
            store_id: ID of the store to update
            store_name: New store name
            shop_type: New shop type
            location: New WKT location
        """
        query = """
            UPDATE grocery_stores 
            SET store_name = %s,
                shop_type = %s,
                location = ST_GeomFromText(%s, 4326),
                last_updated = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        execute_query(query, (store_name, shop_type, location, store_id))
        logger.info(f"Updated store {store_id} ({store_name})")
        
    def _touch_store(self, store_id: int) -> None:
        """
        Update last_updated timestamp for a store.
        
        Args:
            store_id: ID of the store to update
        """
        query = """
            UPDATE grocery_stores 
            SET last_updated = CURRENT_TIMESTAMP
            WHERE id = %s
        """
        execute_query(query, (store_id,))
        
    def _store_exists(self, store_name: str, location: str, city_id: int) -> bool:
        """
        Check if store already exists in database.
        
        Args:
            store_name: Name of the store
            location: WKT representation of store location
            city_id: ID of the city where the store is located
            
        Returns:
            bool: True if store exists, False otherwise
            
        Raises:
            ValueError: If store_name or location is invalid
        """
        return self._get_store_id(store_name, location, city_id) is not None

    def fetch_and_save_stores(self, city_gdf: gpd.GeoDataFrame, 
                            city_name: str, 
                            country_name: Optional[str] = None) -> gpd.GeoDataFrame:
        """
        Fetch grocery stores within a city boundary and save to database.
        
        Args:
            city_gdf (GeoDataFrame): City boundary as a GeoDataFrame.
            city_name (str): Name of the city.
            country_name (Optional[str]): Name of the country.
        
        Returns:
            GeoDataFrame: Grocery stores data.
            
        Raises:
            RuntimeError: If database environment is not properly set up
            ValueError: If city is not found in database
        """
        try:
            # Validate database environment
            validate_database_environment({'city_boundaries', 'grocery_stores'})
            
            # Get city ID
            city_id = self._get_city_id(city_name, country_name)
            if not city_id:
                raise ValueError(f"City {city_name} not found in database")
            
            # Fetch stores from OSM
            logger.info(f"Fetching stores for {city_name}...")
            city_polygon = city_gdf.iloc[0].geometry
            stores_gdf = ox.features_from_polygon(city_polygon, STORE_TAGS)
            
            # Filter and clean data
            stores = stores_gdf[stores_gdf.geometry.type == 'Point'].copy()
            required_cols = ['geometry', 'name', 'shop']
            stores = stores.reindex(columns=required_cols).fillna({'name': 'Unnamed Store'})
            stores = stores.reset_index(drop=True)
            
            # Prepare data for database
            new_stores = []
            updated_stores = []
            
            for _, row in stores.iterrows():
                store_name = row.get('name', 'Unnamed Store')
                shop_type = row.get('shop', 'unknown')
                wkt = row.geometry.wkt
                
                # Check if store exists and needs update
                store_id = self._get_store_id(store_name, wkt, city_id)
                
                if store_id is None:
                    # New store
                    new_stores.append((
                        store_name,
                        shop_type,
                        wkt,
                        city_id
                    ))
                else:
                    # Existing store - check if needs update
                    if self._store_needs_update(store_id, store_name, shop_type, wkt):
                        self._update_store(store_id, store_name, shop_type, wkt)
                        updated_stores.append(store_id)
                    else:
                        # Just update last_updated timestamp
                        self._touch_store(store_id)
            
            # Batch insert new stores
            if new_stores:
                batch_insert('grocery_stores',
                           ['store_name', 'shop_type', 'location', 'city_id'],
                           new_stores)
                logger.info(f"Added {len(new_stores)} new stores to database")
                
            if updated_stores:
                logger.info(f"Updated {len(updated_stores)} existing stores")
            
            total_processed = len(new_stores) + len(updated_stores)
            logger.info(f"Total stores processed: {total_processed}")
            
            return stores
            
        except Exception as e:
            logger.error(f"Error fetching/saving stores: {e}")
            raise
    
    def get_stores_in_radius(self, lat: float, lon: float, radius_meters: float = 1000) -> gpd.GeoDataFrame:
        """
        Get all stores within a radius of a point.
        
        Args:
            lat: Latitude of center point (-90 to 90)
            lon: Longitude of center point (-180 to 180)
            radius_meters: Search radius in meters (positive number)
        
        Returns:
            GeoDataFrame: Stores within radius
            
        Raises:
            ValueError: If input parameters are invalid
        """
        # Validate coordinates
        if not -90 <= lat <= 90:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not -180 <= lon <= 180:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        if radius_meters <= 0:
            raise ValueError("Radius must be a positive number")
        
        try:
            query = """
                SELECT store_name, shop_type, ST_AsText(location) as geometry,
                       ST_Distance(
                           location::geography,
                           ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                       ) as distance
                FROM grocery_stores
                WHERE ST_DWithin(
                    location::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY distance;
            """
            
            rows = execute_query(query, (lon, lat, lon, lat, radius_meters))
            
            if not rows:
                return gpd.GeoDataFrame()
            
            # Convert to GeoDataFrame
            df = pd.DataFrame(rows, columns=['store_name', 'shop_type', 'geometry', 'distance'])
            gdf = gpd.GeoDataFrame(
                df,
                geometry=gpd.GeoSeries.from_wkt(df['geometry']),
                crs="EPSG:4326"
            )
            return gdf
            
        except Exception as e:
            logger.error(f"Database error fetching stores in radius: {e}")
            raise

def update_stores_for_city(city_name: str, country_name: Optional[str] = None) -> Tuple[int, int]:
    """
    Update grocery store data for a specific city.
    
    Args:
        city_name: Name of the city to update stores for
        country_name: Optional name of the country for disambiguation
    
    Returns:
        Tuple[int, int]: (total_stores, new_stores)
        total_stores: Total number of stores in the city
        new_stores: Number of newly added stores
        
    Raises:
        ValueError: If city_name is invalid
        RuntimeError: If database environment is not properly set up
    """
    validate_string_input(city_name, "city_name")
    validate_string_input(country_name, "country_name", allow_none=True)
    
    from .city_fetcher import fetch_city_boundary
    
    try:
        result = fetch_city_boundary(city_name, country_name)

        if isinstance(result, tuple):
            _, matches = result
            raise ValueError(
                f"Multiple matches found for '{city_name}'. "
                f"Please use the UI to select the correct city first, or provide a country name. "
                f"Found {len(matches)} matches."
            )
        
        # Single match - it's a GeoDataFrame
        city_gdf = result
        if city_gdf is None or city_gdf.empty:
            raise ValueError(f"No boundary data found for '{city_name}'")
        
        # Get existing store count
        city_id = get_entity_id(
            'city_boundaries',
            'city_name',
            city_name,
            'country_name' if country_name else None,
            country_name
        )
        
        if city_id:
            existing_count = execute_query(
                "SELECT COUNT(*) FROM grocery_stores WHERE city_id = %s",
                (city_id,)
            )[0][0]
        else:
            existing_count = 0
            
        # Fetch and save stores
        fetcher = GroceryStoreFetcher()
        fetcher.fetch_and_save_stores(
            city_gdf,
            city_name,
            country_name
        )
        
        # Get new total count
        new_total = execute_query(
            "SELECT COUNT(*) FROM grocery_stores WHERE city_id = %s",
            (city_id,)
        )[0][0]
        
        # Calculate new stores (difference in total)
        new_stores = new_total - existing_count
            
        return new_total, max(0, new_stores)  # Ensure non-negative new store count
        
    except Exception as e:
        logger.error(f"Error updating stores for {city_name}: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    try:
        total, new = update_stores_for_city("New Brunswick", "USA")
        logger.info(f"Updated stores: {total} total, {new} new")
    except Exception as e:
        logger.error(f"Failed to update stores: {e}")
        raise
