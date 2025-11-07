import osmnx as ox
import geopandas as gpd
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, Union, List, Optional, Tuple
from datetime import datetime
from db_setup import execute_query, batch_insert
from utils import (
    validate_database_environment,
    validate_string_input,
    get_entity_id,
    check_entity_exists
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
STORE_TAGS: Dict[str, Union[str, List[str], bool]] = {
    'shop': ['supermarket', 'grocery', 'convenience', 'greengrocer'],
    'amenity': ['marketplace']
}

class GroceryStoreFetcher:
    def _get_city_id(self, city_name: str, country_name: Optional[str] = None) -> Optional[int]:
        """Get city ID from database."""
        return get_entity_id(
            table='city_boundaries',
            name_field='city_name',
            name=city_name,
            extra_field='country_name' if country_name else None,
            extra_value=country_name
        )

    def _store_exists(self, store_name: str, location: str, city_id: int) -> bool:
        """Check if store already exists in database."""
        return check_entity_exists(
            'grocery_stores',
            {
                'store_name': store_name,
                'location': location,
                'city_id': city_id
            }
        )

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
            stores_data = []
            for _, row in stores.iterrows():
                store_name = row.get('name', 'Unnamed Store')
                shop_type = row.get('shop', 'unknown')
                wkt = row.geometry.wkt
                
                if not self._store_exists(store_name, wkt, city_id):
                    stores_data.append((
                        store_name,
                        shop_type,
                        wkt,
                        city_id
                    ))
            
            # Batch insert new stores
            if stores_data:
                batch_insert('grocery_stores',
                           ['store_name', 'shop_type', 'location', 'city_id'],
                           stores_data)
                logger.info(f"Added {len(stores_data)} new stores to database")
            
            return stores
            
        except Exception as e:
            logger.error(f"Error fetching/saving stores: {e}")
            raise
    
    def get_stores_in_radius(self, lat: float, lon: float, radius_meters: float = 1000) -> gpd.GeoDataFrame:
        """
        Get all stores within a radius of a point.
        
        Args:
            lat (float): Latitude of center point
            lon (float): Longitude of center point
            radius_meters (float): Search radius in meters
        
        Returns:
            GeoDataFrame: Stores within radius
        """
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
        city_name (str): Name of the city
        country_name (Optional[str]): Name of the country
    
    Returns:
        Tuple[int, int]: (total_stores, new_stores)
    """
    from city_fetcher import fetch_city_boundary
    
    try:
        # Fetch city boundary
        city_gdf = fetch_city_boundary(city_name, country_name)
        
        # Fetch and save stores
        fetcher = GroceryStoreFetcher()
        stores = fetcher.fetch_and_save_stores(
            city_gdf,
            city_name,
            country_name
        )
            
        return len(stores), len(stores)  # In this version, all stores are new
        
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
