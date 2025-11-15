import os
import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from contextlib import contextmanager
from typing import Generator, Any, Optional, List, Tuple

# Configure logging
from .logger_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

# Load environment variables
from .utils import load_environment
load_environment()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'dbname': os.getenv('DB_NAME', 'food_desert_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASS')
}

@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager for database connections.
    
    Yields:
        psycopg2.extensions.connection: Database connection
    
    Example:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM table")
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        yield conn
    except psycopg2.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def execute_query(query: str, params: Optional[tuple] = None) -> Any:
    """
    Execute a single query and return results.
    
    Args:
        query (str): SQL query to execute
        params (tuple, optional): Query parameters
    
    Returns:
        Any: Query results
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            try:
                return cur.fetchall()
            except psycopg2.ProgrammingError:
                return None

def batch_insert(table: str, columns: list, values: list) -> None:
    """
    Perform a batch insert operation.
    
    Args:
        table (str): Table name
        columns (list): Column names
        values (list): List of value tuples to insert
    """
    if not values:
        return
    
    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, query, values)

    logger.info(f"Batch inserted {len(values)} rows into {table}")

def create_database():
    """
    Create the database if it doesn't exist.
    """
    temp_config = DB_CONFIG.copy()
    temp_config['dbname'] = 'postgres'
    
    @contextmanager
    def temp_connection():
        conn = None
        try:
            conn = psycopg2.connect(**temp_config)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            yield conn
        finally:
            if conn:
                conn.close()
    
    try:
        with temp_connection() as conn:
            with conn.cursor() as cur:
                # Check if database exists
                cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", 
                          (DB_CONFIG['dbname'],))
                exists = cur.fetchone()
                
                if not exists:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(DB_CONFIG['dbname'])
                    ))
                    logger.info(f"Database {DB_CONFIG['dbname']} created successfully")
    except psycopg2.Error as e:
        logger.error(f"Database creation error: {e}")
        raise

def create_tables():
    """
    Create necessary tables and extensions in the database.
    
    Schema:
    - grocery_stores: Stores individual grocery store locations
    - coverage_areas: Tracks which geographic areas have been fetched from OSM
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Create PostGIS extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                logger.info("PostGIS extension enabled")

                # Create table for grocery stores
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS grocery_stores (
                        id SERIAL PRIMARY KEY,
                        osm_id BIGINT UNIQUE,
                        store_name VARCHAR(255) NOT NULL,
                        shop_type VARCHAR(50),
                        location GEOMETRY(POINT, 4326) NOT NULL,
                        address TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Created grocery_stores table")

                # Create table to track coverage areas (to avoid re-fetching)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS coverage_areas (
                        id SERIAL PRIMARY KEY,
                        bbox GEOMETRY(POLYGON, 4326) NOT NULL,
                        fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        store_count INTEGER DEFAULT 0
                    );
                """)
                logger.info("Created coverage_areas table")

                # Create spatial indices for fast querying
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_store_location_gist 
                    ON grocery_stores USING GIST(location);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_coverage_bbox_gist 
                    ON coverage_areas USING GIST(bbox);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_store_osm_id 
                    ON grocery_stores(osm_id);
                """)
                
                logger.info("Created spatial indices")
        
        logger.info("Database tables and indices created successfully")
        
    except psycopg2.Error as e:
        logger.error(f"Error creating tables: {e}")
        raise

def init_database():
    """
    Initialize the complete database setup.
    """
    try:
        create_database()
        create_tables()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def validate_database_environment(required_tables: Optional[List[str]] = None) -> None:
    """
    Validates that the database environment is properly set up.
    
    Args:
        required_tables: Optional set of table names to check for existence
    
    Raises:
        RuntimeError: If database validation fails
    """
    try:
        # Default required tables
        if required_tables is None:
            required_tables = ['grocery_stores', 'coverage_areas']
            
        # Check if required tables exist
        tables_query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = ANY(%s);
        """
        result = execute_query(tables_query, (required_tables,))
        existing_tables = {row[0] for row in (result or [])}
        missing_tables = set(required_tables) - existing_tables
        
        if missing_tables:
            raise RuntimeError(
                f"Required tables {missing_tables} do not exist. "
                f"Run 'python -m scripts.db_setup' to initialize the database."
            )
        
        # Check if PostGIS extension is installed
        postgis_query = "SELECT postgis_version();"
        try:
            execute_query(postgis_query)
        except Exception:
            raise RuntimeError(
                "PostGIS extension is not installed. "
                "Run 'python -m scripts.db_setup' to initialize the database."
            )
            
        logger.info("Database environment validation passed")

    except Exception as e:
        logger.error(f"Database validation failed: {e}")
        raise

def check_coverage(bbox: Tuple[float, float, float, float]) -> bool:
    """
    Check if a bounding box area has already been fetched.
    
    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
    
    Returns:
        bool: True if area is already covered, False otherwise
    """
    try:
        min_lon, min_lat, max_lon, max_lat = bbox
        
        # Create polygon from bbox
        bbox_wkt = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
        
        # Check if this bbox is covered by existing coverage areas
        query = """
            SELECT EXISTS (
                SELECT 1 FROM coverage_areas
                WHERE ST_Contains(bbox, ST_GeomFromText(%s, 4326))
            );
        """
        
        result = execute_query(query, (bbox_wkt,))
        return bool(result and result[0][0])
        
    except Exception as e:
        logger.error(f"Error checking coverage: {e}")
        return False
    
def add_coverage(bbox: Tuple[float, float, float, float], store_count: int) -> None:
    """
    Record that a bounding box area has been fetched.
    
    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
        store_count: Number of stores found in this area
    """
    try:
        min_lon, min_lat, max_lon, max_lat = bbox
        
        # Create polygon from bbox
        bbox_wkt = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
        
        query = """
            INSERT INTO coverage_areas (bbox, store_count)
            VALUES (ST_GeomFromText(%s, 4326), %s);
        """
        
        execute_query(query, (bbox_wkt, store_count))
        logger.info(f"Added coverage for bbox with {store_count} stores")
        
    except Exception as e:
        logger.error(f"Error adding coverage: {e}")
        raise

def get_stores_in_bbox(bbox: Tuple[float, float, float, float]) -> List[Tuple]:
    """
    Get all stores within a bounding box.
    
    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
    
    Returns:
        List of tuples containing store data
    """
    try:
        min_lon, min_lat, max_lon, max_lat = bbox
        
        query = """
            SELECT 
                id,
                osm_id,
                store_name, 
                shop_type, 
                ST_X(location) as longitude,
                ST_Y(location) as latitude,
                address
            FROM grocery_stores
            WHERE location && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
            AND ST_Within(location, ST_MakeEnvelope(%s, %s, %s, %s, 4326));
        """
        
        params = (min_lon, min_lat, max_lon, max_lat, min_lon, min_lat, max_lon, max_lat)
        result = execute_query(query, params)
        
        return result or []
        
    except Exception as e:
        logger.error(f"Error getting stores in bbox: {e}")
        return []

if __name__ == "__main__":
    try:
        init_database()
        print("✓ Database initialized successfully!")
        print("✓ Ready to use the map-based food desert mapper")
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        print(f"✗ Database setup failed: {e}")