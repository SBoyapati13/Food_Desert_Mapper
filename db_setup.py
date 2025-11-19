"""
Database setup and operations for the Food Desert Mapper.

This module handles:
- Database schema creation with PostGIS support
- City and grocery store data persistence
- Spatial indexing for performance
- Data retrieval and validation
"""
import os
import logging
from typing import Optional, Dict
from contextlib import contextmanager

import psycopg2
from psycopg2 import sql, extras
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import geopandas as gpd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration manager."""
    
    def __init__(self):
        self.host: str = os.getenv('DB_HOST', 'localhost')
        self.port: str = os.getenv('DB_PORT', '5432')
        self.database: str = os.getenv('DB_NAME', 'food_desert_db')
        
        # These must be set and cannot be None
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        
        if not user or not password:
            raise ValueError("DB_USER and DB_PASSWORD must be set in .env file")
        
        self.user: str = user
        self.password: str = password
        
    def get_connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def get_psycopg2_params(self) -> Dict[str, str]:
        """Get psycopg2 connection parameters."""
        return {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'user': self.user,
            'password': self.password
        }
    
@contextmanager
def get_db_connection(autocommit: bool = False):
    """
    Context manager for database connections.
    
    Args:
        autocommit: If True, set connection to autocommit mode
        
    Yields:
        psycopg2 connection object
    """
    config = DatabaseConfig()
    params = config.get_psycopg2_params()
    conn = None

    try:
        conn = psycopg2.connect(
            host=params['host'],
            port=params['port'],
            database=params['database'],
            user=params['user'],
            password=params['password']
        )
        if autocommit:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        yield conn

    except psycopg2.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

    finally:
        if conn:
            conn.close()

def create_database():
    """
    Create the database if it doesn't exist.
    Must be run with a user that has database creation privileges.
    """
    config = DatabaseConfig()
    
    # Connect to default 'postgres' database to create our database
    temp_params = config.get_psycopg2_params()
    
    try:
        conn = psycopg2.connect(
            host=temp_params['host'],
            port=temp_params['port'],
            database='postgres',
            user=temp_params['user'],
            password=temp_params['password']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (config.database,)
        )
        
        if cursor.fetchone():
            logger.info(f"Database '{config.database}' already exists")
        else:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(config.database)
                )
            )
            logger.info(f"Database '{config.database}' created successfully")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        logger.error(f"Error creating database: {e}")
        raise

def enable_postgis():
    """Enable PostGIS extension in the database."""
    try:
        with get_db_connection(autocommit=True) as conn:
            cursor = conn.cursor()
            
            # Enable PostGIS extension
            cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            logger.info("PostGIS extension enabled")
            
            # Verify PostGIS is installed
            cursor.execute("SELECT PostGIS_Version();")
            result = cursor.fetchone()
            if result:
                version = result[0]
                logger.info(f"PostGIS version: {version}")
            else:
                logger.warning("Could not retrieve PostGIS version")

            cursor.close()
            
    except psycopg2.Error as e:
        logger.error(f"Error enabling PostGIS: {e}")
        raise

def create_schema():
    """Create all tables and indexes for the food desert mapper."""
    
    schema_sql = """
    -- ================================================================
    -- CITIES TABLE
    -- ================================================================
    CREATE TABLE IF NOT EXISTS cities (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        state VARCHAR(100),
        country VARCHAR(100) NOT NULL DEFAULT 'USA',
        osm_id BIGINT NOT NULL,
        boundary GEOMETRY(MULTIPOLYGON, 4326) NOT NULL,
        area_km2 FLOAT,
        fetched_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT unique_city UNIQUE(name, state, country)
    );
    
    -- Spatial index for boundary queries
    CREATE INDEX IF NOT EXISTS idx_cities_boundary 
        ON cities USING GIST(boundary);
    
    -- Index for city lookups
    CREATE INDEX IF NOT EXISTS idx_cities_name_state 
        ON cities(name, state);
    
    -- ================================================================
    -- GROCERY STORES TABLE
    -- ================================================================
    CREATE TABLE IF NOT EXISTS grocery_stores (
        id SERIAL PRIMARY KEY,
        city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
        osm_id BIGINT NOT NULL,
        name VARCHAR(255),
        shop_type VARCHAR(50) NOT NULL,
        location GEOMETRY(POINT, 4326) NOT NULL,
        fetched_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT unique_store UNIQUE(osm_id, city_id)
    );
    
    -- Spatial index for proximity queries
    CREATE INDEX IF NOT EXISTS idx_stores_location 
        ON grocery_stores USING GIST(location);
    
    -- Index for city lookups
    CREATE INDEX IF NOT EXISTS idx_stores_city_id 
        ON grocery_stores(city_id);
    
    -- Index for store type filtering
    CREATE INDEX IF NOT EXISTS idx_stores_type 
        ON grocery_stores(shop_type);
    
    -- ================================================================
    -- FETCH METADATA TABLE
    -- ================================================================
    CREATE TABLE IF NOT EXISTS fetch_metadata (
        id SERIAL PRIMARY KEY,
        city_id INTEGER REFERENCES cities(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL,
        stores_count INTEGER,
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    -- Index for metadata queries
    CREATE INDEX IF NOT EXISTS idx_metadata_city_id 
        ON fetch_metadata(city_id);
    """
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(schema_sql)
            conn.commit()
            cursor.close()
            logger.info("Database schema created successfully")
            
    except psycopg2.Error as e:
        logger.error(f"Error creating schema: {e}")
        raise

def save_city_to_db(city_gdf: gpd.GeoDataFrame) -> Optional[int]:
    """
    Save city boundary to database.
    
    Args:
        city_gdf: GeoDataFrame containing city boundary data
        
    Returns:
        City ID if successful, None otherwise
    """
    if city_gdf is None or city_gdf.empty:
        logger.error("Empty GeoDataFrame provided")
        return None
    
    try:
        # Extract city information
        row = city_gdf.iloc[0]
        
        # Convert geometry to WKT
        geometry_wkt = row.geometry.wkt

        # Convert numpy types to Python types
        osm_id = int(row.get('osm_id', 0))
        area_km2 = float(row.get('area_km2', 0.0)) if row.get('area_km2') is not None else None
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            insert_sql = """
                INSERT INTO cities (
                    name, state, country, osm_id, boundary, area_km2
                )
                VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                ON CONFLICT (name, state, country) 
                DO UPDATE SET
                    boundary = EXCLUDED.boundary,
                    area_km2 = EXCLUDED.area_km2,
                    fetched_at = NOW()
                RETURNING id;
            """

            cursor.execute(insert_sql, (
                row.get('name', ''),
                row.get('state', ''),
                row.get('country', 'USA'),
                osm_id,
                geometry_wkt,
                area_km2
            ))
            
            result = cursor.fetchone()
            if result is None:
                logger.error("Failed to insert city into database")
                return None
            
            city_id = result[0]
            conn.commit()
            cursor.close()
            
            logger.info(f"City saved to database with ID: {city_id}")
            return city_id
            
    except Exception as e:
        logger.error(f"Error saving city to database: {e}")
        return None
    
def save_stores_to_db(stores_gdf: gpd.GeoDataFrame, city_id: int) -> int:
    """
    Save grocery stores to database.
    
    Args:
        stores_gdf: GeoDataFrame containing store locations
        city_id: ID of the parent city
        
    Returns:
        Number of stores successfully saved
    """
    if stores_gdf is None or stores_gdf.empty:
        logger.warning("Empty stores GeoDataFrame provided")
        return 0
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            insert_sql = """
                INSERT INTO grocery_stores (
                    city_id, osm_id, name, shop_type, location
                )
                VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326))
                ON CONFLICT (osm_id, city_id) DO NOTHING;
            """
            
            inserted_count = 0
            
            for idx, row in stores_gdf.iterrows():
                try:
                    geometry_wkt = row.geometry.wkt

                    # Convert numpy types to Python types
                    osm_id = int(row.get('osm_id', 0))
                    name = str(row.get('name', ''))
                    shop_type = str(row.get('shop_type', 'unknown'))
                    
                    cursor.execute(insert_sql, (
                        city_id,
                        osm_id,
                        name,
                        shop_type,
                        geometry_wkt
                    ))
                    
                    if cursor.rowcount > 0:
                        inserted_count += 1
                        
                except Exception as e:
                    logger.warning(f"Error inserting store {idx}: {e}")
                    continue
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Saved {inserted_count} stores to database")
            return inserted_count
            
    except Exception as e:
        logger.error(f"Error saving stores to database: {e}")
        return 0
    
def check_city_exists(city: str, state: str, country: str = 'USA') -> Optional[Dict]:
    """
    Check if a city exists in the database.
    
    Args:
        city: City name
        state: State name
        country: Country name (default: USA)
        
    Returns:
        Dictionary with city info if exists, None otherwise
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(cursor_factory=extras.RealDictCursor)
            
            query = """
                SELECT 
                    id, name, state, country, osm_id,
                    area_km2, fetched_at,
                    (SELECT COUNT(*) FROM grocery_stores WHERE city_id = cities.id) as store_count
                FROM cities
                WHERE LOWER(name) = LOWER(%s) 
                    AND LOWER(state) = LOWER(%s)
                    AND LOWER(country) = LOWER(%s)
                ORDER BY fetched_at DESC
                LIMIT 1;
            """
            
            cursor.execute(query, (city, state, country))
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return dict(result)
            return None
            
    except Exception as e:
        logger.error(f"Error checking city existence: {e}")
        return None
    
def get_city_from_db(city_id: int) -> Optional[gpd.GeoDataFrame]:
    """
    Retrieve city boundary from database.
    
    Args:
        city_id: City ID
        
    Returns:
        GeoDataFrame with city boundary
    """
    try:
        config = DatabaseConfig()
        connection_string = config.get_connection_string()
        
        logger.info(f"Connecting to database for city_id {city_id}")
        logger.debug(f"Connection string (masked): postgresql://{config.user}:****@{config.host}:{config.port}/{config.database}")
        
        engine = create_engine(connection_string)
        
        query = """
            SELECT 
                id, name, state, country, osm_id, 
                area_km2, fetched_at,
                ST_AsText(boundary) as geometry
            FROM cities
            WHERE id = %s;
        """
        
        gdf = gpd.read_postgis(
            query,
            engine,
            geom_col='geometry',
            params=(city_id,)
        )
        
        if gdf.empty:
            logger.warning(f"No city found with id {city_id}")
            return None
        
        logger.info(f"Successfully retrieved city_id {city_id}")
        return gdf
        
    except Exception as e:
        logger.error(f"Error retrieving city from database: {e}")
        return None
    
def get_stores_from_db(city_id: int) -> Optional[gpd.GeoDataFrame]:
    """
    Retrieve grocery stores from database.
    
    Args:
        city_id: City ID
        
    Returns:
        GeoDataFrame with store locations
    """
    try:
        config = DatabaseConfig()
        connection_string = config.get_connection_string()
        
        logger.info(f"Connecting to database for city_id {city_id}")
        logger.debug(f"Connection string (masked): postgresql://{config.user}:****@{config.host}:{config.port}/{config.database}")
        
        engine = create_engine(connection_string)
        
        query = """
            SELECT 
                id, city_id, osm_id, name, shop_type, fetched_at,
                ST_AsText(location) as geometry
            FROM grocery_stores
            WHERE city_id = %s;
        """
        
        gdf = gpd.read_postgis(
            query,
            engine,
            geom_col='geometry',
            params=(city_id,)
        )
        
        return gdf if not gdf.empty else None
        
    except Exception as e:
        logger.error(f"Error retrieving stores from database: {e}")
        return None
    
def log_fetch_metadata(
    city_id: int,
    status: str,
    stores_count: Optional[int] = None
):
    """
    Log metadata about a fetch operation.
    
    Args:
        city_id: City ID
        status: Status ('success', 'partial', 'failed')
        stores_count: Number of stores fetched
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            insert_sql = """
                INSERT INTO fetch_metadata (
                    city_id, status, stores_count
                )
                VALUES (%s, %s, %s);
            """
            
            cursor.execute(insert_sql, (
                city_id,
                status,
                stores_count
            ))
            
            conn.commit()
            cursor.close()
            
    except Exception as e:
        logger.error(f"Error logging fetch metadata: {e}")

def initialize_database():
    """
    Complete database initialization workflow.
    Run this once to set up the entire database.
    """
    try:
        logger.info("Starting database initialization...")
        
        # Step 1: Create database
        create_database()
        
        # Step 2: Enable PostGIS
        enable_postgis()
        
        # Step 3: Create schema
        create_schema()
        
        logger.info("Database initialization completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False
    
if __name__ == "__main__":
    """Run database setup when executed directly."""
    print("=" * 60)
    print("Food Desert Mapper - Database Setup")
    print("=" * 60)
    
    success = initialize_database()
    
    if success:
        print("\n✓ Database setup completed successfully!")
        print("\nNext steps:")
        print("1. Verify your .env file contains correct credentials")
        print("2. Run the Streamlit app: streamlit run app.py")
    else:
        print("\n✗ Database setup failed. Check logs for details.")
        print("\nTroubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Verify credentials in .env file")
        print("3. Ensure user has CREATE DATABASE privileges")