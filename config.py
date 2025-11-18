"""
Configuration settings for the Food Desert Mapper application.

Loads environment variables and provides centralized configuration
for database, OSM queries, and application settings.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Application configuration settings."""
    
    # ============================================================================
    # DATABASE CONFIGURATION
    # ============================================================================
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'food_desert_db')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    
    # ============================================================================
    # APPLICATION SETTINGS
    # ============================================================================
    APP_TITLE = "Food Desert Mapper"
    APP_ICON = "🏙️"
    APP_DESCRIPTION = "Visualize areas in US cities with limited access to fresh food"
    
    # Default country
    DEFAULT_COUNTRY = "USA"
    
    # ============================================================================
    # MAP SETTINGS
    # ============================================================================
    # Default map center (US center)
    DEFAULT_MAP_CENTER = (39.8283, -98.5795)
    DEFAULT_MAP_ZOOM = 4
    
    # City view zoom level
    CITY_ZOOM_LEVEL = 12
    
    # Map tile provider
    MAP_TILES = "OpenStreetMap"
    
    # City boundary style
    BOUNDARY_COLOR = "#2E86AB"
    BOUNDARY_WEIGHT = 3
    BOUNDARY_FILL_OPACITY = 0.1
    
    # Store marker colors by type
    STORE_COLORS = {
        'supermarket': '#28a745',      # Green
        'convenience': '#ffc107',      # Yellow
        'greengrocer': '#20c997',      # Teal
        'butcher': '#dc3545',          # Red
        'bakery': '#fd7e14',           # Orange
        'deli': '#e83e8c',             # Pink
        'farm': '#6f42c1',             # Purple
        'health_food': '#17a2b8',      # Cyan
        'organic': '#6610f2',          # Indigo
        'marketplace': '#28a745',      # Green
        'unknown': '#6c757d'           # Gray
    }
    
    # Default store marker color
    DEFAULT_STORE_COLOR = '#28a745'
    
    # Marker cluster settings
    USE_MARKER_CLUSTERS = True
    
    # ============================================================================
    # OSM QUERY SETTINGS
    # ============================================================================
    # OSMnx settings
    OSM_TIMEOUT = 180  # seconds
    OSM_MAX_QUERY_AREA_SIZE = 50000000  # square meters (50 km²)
    
    # ============================================================================
    # UI SETTINGS
    # ============================================================================
    # Sidebar width
    SIDEBAR_STATE = "expanded"
    
    # Max cities to show in recent list
    MAX_RECENT_CITIES = 10
    
    # ============================================================================
    # DATA SETTINGS
    # ============================================================================
    # Cache settings
    ENABLE_CACHE = True
    CACHE_TTL = 3600  # seconds (1 hour)
    
    # Data freshness threshold (days)
    DATA_FRESHNESS_DAYS = 30
    
    # ============================================================================
    # LOGGING SETTINGS
    # ============================================================================
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate that all required configuration is present.
        
        Returns:
            True if valid, False otherwise
        """
        if not cls.DB_USER or not cls.DB_PASSWORD:
            print("ERROR: DB_USER and DB_PASSWORD must be set in .env file")
            return False
        
        return True
    
    @classmethod
    def get_db_connection_string(cls) -> str:
        """
        Get database connection string for SQLAlchemy.
        
        Returns:
            Connection string
        """
        return f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
    
    @classmethod
    def get_store_color(cls, store_type: str) -> str:
        """
        Get color for a store type.
        
        Args:
            store_type: Type of store
            
        Returns:
            Hex color code
        """
        return cls.STORE_COLORS.get(store_type, cls.DEFAULT_STORE_COLOR)


# Create a singleton config instance
config = Config()


if __name__ == "__main__":
    """Test configuration loading."""
    print("=" * 60)
    print("Configuration Test")
    print("=" * 60)
    
    print("\nDatabase Configuration:")
    print(f"  Host: {Config.DB_HOST}")
    print(f"  Port: {Config.DB_PORT}")
    print(f"  Database: {Config.DB_NAME}")
    print(f"  User: {Config.DB_USER}")
    print(f"  Password: {'*' * len(Config.DB_PASSWORD) if Config.DB_PASSWORD else 'NOT SET'}")
    
    print("\nApplication Settings:")
    print(f"  Title: {Config.APP_TITLE}")
    print(f"  Default Country: {Config.DEFAULT_COUNTRY}")
    
    print("\nMap Settings:")
    print(f"  Default Center: {Config.DEFAULT_MAP_CENTER}")
    print(f"  City Zoom: {Config.CITY_ZOOM_LEVEL}")
    print(f"  Use Clusters: {Config.USE_MARKER_CLUSTERS}")
    
    print("\nValidation:")
    if Config.validate():
        print("  ✓ Configuration is valid")
    else:
        print("  ✗ Configuration is invalid")