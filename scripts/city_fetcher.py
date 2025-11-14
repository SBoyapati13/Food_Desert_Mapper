import osmnx as ox
import logging
from typing import Optional, Union, Tuple, List, Dict
import geopandas as gpd

from .db_setup import (
    execute_query,
    validate_database_environment,
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

# Get project root and set OSMnx cache directory to data folder
CACHE_DIR = ensure_data_directory() / "cache"
ox.settings.cache_folder = str(CACHE_DIR)

def validate_inputs(city_name: str, country_name: Optional[str] = None) -> None:
    """
    Validates the input parameters.
    
    Parameters:
        city_name (str): The name of the city to validate.
        country_name (Optional[str]): The name of the country to validate.
    
    Raises:
        ValueError: If inputs are invalid.
    """
    # Validate input strings
    validate_string_input(city_name, "city_name")
    validate_string_input(country_name, "country_name", allow_none=True)
    
    # Check if city exists
    criteria = {"city_name": city_name}
    if country_name:
        criteria["country_name"] = country_name
    
    if check_entity_exists("city_boundaries", criteria):
        result = execute_query(
            "SELECT last_updated FROM city_boundaries WHERE city_name = %s",
            (city_name,)
        )
        logger.info(f"City boundary for '{city_name}' already exists (last updated: {result[0][0]})")
    
    logger.info(f"Input validation passed for city_name='{city_name}', country_name='{country_name}'")

def fetch_city_boundary(
        city_name: str, 
        country_name: Optional[str] = None,
        osm_id: Optional[int] = None
    ) -> Union[gpd.GeoDataFrame, Tuple[None, List[Dict]]]:
    """
    Fetches the boundary of a specified city using OpenStreetMap data via OSMnx.
    
    This function searches global OpenStreetMap data for the administrative boundary
    polygon of the specified city and country. The boundary is downloaded as a
    GeoDataFrame and saved to the database for geospatial analysis.
    
    Parameters:
        city_name (str): The name of the city to fetch (required).
        country_name (Optional[str]): The name of the country where the city is located.
                                    Improves accuracy for ambiguous city names.
        osm_id (Optional[int]): Specific OSM ID to fetch (bypasses search).

    Returns:
        Union[GeoDataFrame, Tuple[None, List[Dict]]]: 
            - GeoDataFrame if single match found
            - Tuple of (None, list of matches) if multiple matches found
    
    Raises:
        ValueError: If city_name or country_name are invalid.
        RuntimeError: If database environment is not properly set up.
        Exception: If the OSM query fails or the city is not found.
    """
    try:
        # Validate database environment first
        validate_database_environment({'city_boundaries'})

        # If OSM id is provided, fetch directly
        if osm_id:
            logger.info(f"Fetching boundary for OSM ID: {osm_id}")
            try:
                gdf = ox.geocode_to_gdf(str(osm_id), by_osmid=True)
                logger.info(f"Successfully fetched boundary for OSM ID: {osm_id}")

                # Save to database
                _save_boundary_to_db(gdf, city_name, country_name)
                return gdf
            
            except Exception as e:
                logger.error(f"Failed to fetch boundary from OpenStreetMap for OSM ID '{osm_id}': {e}")
                raise Exception(f"Could not find city boundary for OSM ID '{osm_id}'. Please verify the ID.") from e

        # Validate inputs
        validate_inputs(city_name, country_name)
        
        # Ensure data directory exists
        ensure_data_directory()
        
        # Construct query
        query = city_name if not country_name else f"{city_name}, {country_name}"
        logger.info(f"Fetching boundary for: {query}")
        
        # Fetch boundary from OpenStreetMap
        try:
            gdf = ox.geocode_to_gdf(query, which_result=None) # Get all matches

            # Check if multiple matches found
            if len(gdf) > 1:
                logger.info(f"Found {len(gdf)} matches for query '{query}'")

                # Convert matches to a list of dicts for selection
                matches = []
                for idx, row in gdf.iterrows():
                    matches.append({
                        'display_name': row.get('display_name', 'Unknown'),
                        'osm_type': row.get('osm_type', 'Unknown'),
                        'osm_id': row.get('osm_id', 'Unknown'),
                        'name': row.get('name', city_name),
                        'place_rank': row.get('place_rank', 999)
                    })

                # Sort by place_rank (lower is more specific)
                matches.sort(key=lambda x: x.get('place_rank', 999))

                return None, matches
            
            # Single result
            logger.info(f"Successfully fetched boundary for {query}")

        except Exception as e:
            logger.error(f"Failed to fetch boundary from OpenStreetMap for '{query}': {e}")
            raise Exception(f"Could not find city boundary for '{query}'. Please verify the city and country names.") from e
        
        # Save to database
        _save_boundary_to_db(gdf, city_name, country_name)

        return gdf
        
    except ValueError as e:
        logger.error(f"Input validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fetch_city_boundary: {e}")
        raise

def _save_boundary_to_db(gdf: gpd.GeoDataFrame, city_name: str, country_name: Optional[str]) -> None:
    """
    Helper function to save boundary to database.
    
    Parameters:
        gdf: GeoDataFrame containing the boundary
        city_name: Name of the city
        country_name: Optional country name
    """
    try:
        geom_wkt = gdf.iloc[0].geometry.wkt

        query = """
            INSERT INTO city_boundaries (city_name, country_name, boundary)
            VALUES (%s, %s, ST_GeomFromText(%s, 4326))
            ON CONFLICT (city_name, country_name) DO UPDATE 
            SET boundary = ST_GeomFromText(%s, 4326),
                last_updated = CURRENT_TIMESTAMP;
        """

        params = (city_name, country_name, geom_wkt, geom_wkt)
        execute_query(query, params)

        query_str = city_name if not country_name else f"{city_name}, {country_name}"
        logger.info(f"City boundary for '{query_str}' saved to database successfully")
        print(f"✓ Boundary for {query_str} saved to database")

    except Exception as e:
        logger.error(f"Failed to save boundary: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    try:
        result = fetch_city_boundary("New Brunswick")
        if isinstance(result, tuple):
            _, matches = result
            print(f"Found {len(matches)} matches:")
            for i, match in enumerate(matches, 1):
                print(f"{i}. {match['display_name']}")
        else:
            print("Single match found and saved!")
    except Exception as e:
        logger.error(f"Error fetching city boundary: {e}")