import osmnx as ox
import logging
from pathlib import Path
from db_setup import execute_query
from typing import Optional
from utils import (
    ensure_data_directory,
    validate_database_environment,
    validate_string_input,
    check_entity_exists
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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


def fetch_city_boundary(city_name: str, country_name: Optional[str] = None):
    """
    Fetches the boundary of a specified city using OpenStreetMap data via OSMnx.
    
    This function searches global OpenStreetMap data for the administrative boundary
    polygon of the specified city and country. The boundary is downloaded as a
    GeoDataFrame and saved to the database for geospatial analysis.
    
    Parameters:
        city_name (str): The name of the city to fetch (required).
        country_name (Optional[str]): The name of the country where the city is located.
                                    Improves accuracy for ambiguous city names.

    Returns:
        GeoDataFrame: A GeoDataFrame containing the city's boundary polygon(s).
    
    Raises:
        ValueError: If city_name or country_name are invalid.
        RuntimeError: If database environment is not properly set up.
        Exception: If the OSM query fails or the city is not found.
    """
    try:
        # Validate database environment first
        validate_database_environment({'city_boundaries'})
        
        # Validate inputs
        validate_inputs(city_name, country_name)
        
        # Ensure data directory exists
        ensure_data_directory()
        
        # Construct query
        query = city_name if not country_name else f"{city_name}, {country_name}"
        logger.info(f"Fetching boundary for: {query}")
        
        # Fetch boundary from OpenStreetMap
        try:
            gdf = ox.geocode_to_gdf(query)
            logger.info(f"Successfully fetched boundary for {query}")
        except Exception as e:
            logger.error(f"Failed to fetch boundary from OpenStreetMap for '{query}': {e}")
            raise Exception(f"Could not find city boundary for '{query}'. Please verify the city and country names.") from e
        
        # Save to database
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
            
            logger.info(f"City boundary fetcher completed successfully for {query}")
            print(f"✓ Boundary for {query} saved to database")
            
            return gdf
            
        except Exception as e:
            logger.error(f"Failed to save boundary: {e}")
            raise
        
    except ValueError as e:
        logger.error(f"Input validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fetch_city_boundary: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    try:
        city_boundary_gdf = fetch_city_boundary("New Brunswick", "USA")
    except Exception as e:
        logger.error(f"Error fetching city boundary: {e}")