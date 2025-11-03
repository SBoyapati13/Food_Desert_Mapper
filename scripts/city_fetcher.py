import osmnx as ox
import logging
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get project root and set OSMnx cache directory to data folder
PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
ox.settings.cache_folder = str(CACHE_DIR)


def ensure_data_directory():
    """
    Ensures the data directory and cache subdirectory exist at the project root. 
    Creates them if necessary.
    
    Returns:
    str: The path to the data directory.
    """
    # Get the project root by going up one level from the scripts directory
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    cache_dir = data_dir / "cache"
    
    try:
        data_dir.mkdir(exist_ok=True)
        cache_dir.mkdir(exist_ok=True)
        logger.info(f"Data directory ensured at: {data_dir.resolve()}")
        logger.info(f"Cache directory ensured at: {cache_dir.resolve()}")
        return str(data_dir)
    except OSError as e:
        logger.error(f"Failed to create data/cache directories: {e}")
        raise


def validate_inputs(city_name, country_name=None):
    """
    Validates the input parameters.
    
    Parameters:
    city_name (str): The name of the city to validate.
    country_name (str, optional): The name of the country to validate.
    
    Raises:
    ValueError: If inputs are invalid.
    """
    if not isinstance(city_name, str) or not city_name.strip():
        raise ValueError("city_name must be a non-empty string")
    
    if country_name is not None:
        if not isinstance(country_name, str) or not country_name.strip():
            raise ValueError("country_name must be a non-empty string or None")
    
    logger.info(f"Input validation passed for city_name='{city_name}', country_name='{country_name}'")


def fetch_city_boundary(city_name, country_name=None):
    """
    Fetches the boundary of a specified city using OpenStreetMap data via OSMnx.
    
    This function searches global OpenStreetMap data for the administrative boundary
    polygon of the specified city and country. The boundary is downloaded as a
    GeoDataFrame and saved as GeoJSON for visualization and geospatial analysis.
    
    Parameters:
    city_name (str): The name of the city to fetch (required).
    country_name (str, optional): The name of the country where the city is located.
                                  Improves accuracy for ambiguous city names.

    Returns:
    GeoDataFrame: A GeoDataFrame containing the city's boundary polygon(s).
    
    Raises:
    ValueError: If city_name or country_name are invalid.
    OSError: If the data directory cannot be created.
    Exception: If the OSM query fails or the city is not found.
    """
    try:
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
        
        # Get data directory path and generate output file path
        data_dir = ensure_data_directory()
        safe_filename = city_name.replace(' ', '_').lower()
        output_file = os.path.join(data_dir, f"{safe_filename}_boundary.geojson")
        
        # Save to GeoJSON
        try:
            gdf.to_file(output_file, driver='GeoJSON')
            logger.info(f"Boundary saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save boundary to {output_file}: {e}")
            raise Exception(f"Failed to save boundary file to {output_file}.") from e
        
        logger.info(f"City boundary fetcher completed successfully for {query}")
        print(f"✓ Boundary for {query} saved to {output_file}")
        
        return gdf
        
    except ValueError as e:
        logger.error(f"Input validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fetch_city_boundary: {e}")
        raise

if __name__ == "__main__":
    # Example usage
    try:
        city_boundary_gdf = fetch_city_boundary("New York City", "USA")
    except Exception as e:
        logger.error(f"Error fetching city boundary: {e}")