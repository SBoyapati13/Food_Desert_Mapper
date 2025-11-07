import os
from pathlib import Path
import logging
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from contextlib import contextmanager
from typing import Generator, Any, Optional, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

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
    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, query, values)

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
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Create PostGIS extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                logger.info("PostGIS extension enabled")

                # Create table for city boundaries
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS city_boundaries (
                        id SERIAL PRIMARY KEY,
                        city_name VARCHAR(100) NOT NULL,
                        country_name VARCHAR(100),
                        boundary GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(city_name, country_name)
                    );
                """)

                # Create table for grocery stores
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS grocery_stores (
                        id SERIAL PRIMARY KEY,
                        store_name VARCHAR(100) NOT NULL,
                        shop_type VARCHAR(50),
                        location GEOMETRY(POINT, 4326) NOT NULL,
                        city_id INTEGER REFERENCES city_boundaries(id),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # Create spatial index on geometries
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_city_boundary_geom ON city_boundaries USING GIST(boundary);
                    CREATE INDEX IF NOT EXISTS idx_store_location_geom ON grocery_stores USING GIST(location);
                """)
        
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

if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        logger.error(f"Setup failed: {e}")