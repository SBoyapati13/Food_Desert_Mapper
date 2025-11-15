import streamlit as st
import folium
from folium.plugins import MarkerCluster
import logging
from typing import Optional, Tuple, List, Dict
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Import from our package
from scripts.grocery_fetcher import fetch_stores_in_bbox, get_stores_at_point
from scripts.logger_config import setup_logging

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

# Default map center (you can change this to your preferred location)
DEFAULT_CENTER = [40.4862, -74.4518]  # New Brunswick, NJ
DEFAULT_ZOOM = 13

MAP_CONFIG = {
    "zoom_start": DEFAULT_ZOOM,
    "tiles": "OpenStreetMap",
    "width": "100%",
    "height": 600
}

# Store marker colors by shop type
STORE_COLORS = {
    'supermarket': 'red',
    'grocery': 'green',
    'convenience': 'orange',
    'greengrocer': 'lightgreen',
    'marketplace': 'blue',
    'unknown': 'gray'
}

# Initialize session state
DEFAULT_SESSION_STATE = {
    "map_center": DEFAULT_CENTER,
    "map_zoom": DEFAULT_ZOOM,
    "show_stores": True,
    "current_bounds": None,
    "stores_cache": {},
    "search_address": "",
}

for key, value in DEFAULT_SESSION_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Geocode an address to coordinates.
    
    Args:
        address: Address string to geocode
        
    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    if not address or not address.strip():
        return None
    
    try:
        geolocator = Nominatim(user_agent="food-desert-mapper")
        location = geolocator.geocode(address, timeout=10)
        
        if location and hasattr(location, 'latitude') and hasattr(location, 'longitude'):
            logger.info(f"Geocoded '{address}' to {location.latitude}, {location.longitude}")
            return (float(location.latitude), float(location.longitude))
        else:
            logger.warning(f"Could not geocode address: {address}")
            return None
            
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.error(f"Geocoding error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected geocoding error: {e}")
        return None

def calculate_bbox_from_bounds(bounds: Dict) -> Optional[Tuple[float, float, float, float]]:
    """
    Calculate bounding box from Folium map bounds.
    
    Args:
        bounds: Dictionary with '_southWest' and '_northEast' keys
        
    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat)
    """
    try:
        south_west = bounds['_southWest']
        north_east = bounds['_northEast']
        
        min_lat = south_west['lat']
        min_lon = south_west['lng']
        max_lat = north_east['lat']
        max_lon = north_east['lng']
        
        return (min_lon, min_lat, max_lon, max_lat)
    except (KeyError, TypeError) as e:
        logger.error(f"Error parsing bounds: {e}")
        return None

def bbox_to_string(bbox: Tuple[float, float, float, float]) -> str:
    """
    Convert bbox tuple to string for caching.
    
    Args:
        bbox: Tuple of (min_lon, min_lat, max_lon, max_lat)
        
    Returns:
        String representation
    """
    return f"{bbox[0]:.4f},{bbox[1]:.4f},{bbox[2]:.4f},{bbox[3]:.4f}"

# ============================================================================
# MAP CREATION AND MANAGEMENT
# ============================================================================

class MapManager:
    """Handles map creation and store marker management."""
    
    @staticmethod
    def create_base_map(center: List[float], zoom: int) -> folium.Map:
        """
        Create a base Folium map.
        
        Args:
            center: [latitude, longitude]
            zoom: Zoom level
            
        Returns:
            Folium Map object
        """
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=MAP_CONFIG["tiles"],
            control_scale=True
        )
        
        return m
    
    @staticmethod
    def add_store_markers(m: folium.Map, stores: List[Dict], use_clustering: bool = False) -> None:
        """
        Add store markers to the map.
        
        Args:
            m: Folium map object
            stores: List of store dictionaries
            use_clustering: Whether to use marker clustering
        """
        if not stores:
            return
        
        # Create marker cluster if requested
        if use_clustering and len(stores) > 50:
            marker_cluster = MarkerCluster(
                name="Grocery Stores",
                overlay=True,
                control=True
            ).add_to(m)
            add_to = marker_cluster
        else:
            add_to = m
        
        # Add markers
        for store in stores:
            try:
                lat = store['latitude']
                lon = store['longitude']
                name = store['name']
                shop_type = store['shop_type']
                address = store.get('address', 'Address not available')
                
                # Get color based on shop type
                color = STORE_COLORS.get(shop_type, STORE_COLORS['unknown'])
                
                # Create popup content
                popup_html = f"""
                    <div style='min-width: 200px; font-family: Arial, sans-serif;'>
                        <h4 style='margin-bottom: 8px; color: #2c3e50;'>{name}</h4>
                        <p style='margin: 4px 0;'><b>Type:</b> {shop_type}</p>
                        <p style='margin: 4px 0;'><b>Address:</b> {address or 'N/A'}</p>
                        <p style='margin: 4px 0; font-size: 11px; color: #7f8c8d;'>
                            📍 {lat:.4f}, {lon:.4f}
                        </p>
                    </div>
                """
                
                # Add marker
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=name,
                    icon=folium.Icon(color=color, icon='shopping-cart', prefix='fa')
                ).add_to(add_to)
                
            except Exception as e:
                logger.error(f"Error adding marker for store: {e}")
                continue
    
    @staticmethod
    def create_map_with_stores(
        center: List[float], 
        zoom: int, 
        stores: List[Dict],
        show_stores: bool = True
    ) -> folium.Map:
        """
        Create a map with store markers.
        
        Args:
            center: [latitude, longitude]
            zoom: Zoom level
            stores: List of store dictionaries
            show_stores: Whether to show store markers
            
        Returns:
            Folium Map object
        """
        m = MapManager.create_base_map(center, zoom)
        
        if show_stores and stores:
            MapManager.add_store_markers(m, stores, use_clustering=(len(stores) > 50))
        
        return m

# ============================================================================
# USER INTERFACE
# ============================================================================

class UserInterface:
    """Handles UI elements and user interactions."""
    
    @staticmethod
    def render_header():
        """Configure page and render header."""
        st.set_page_config(
            page_title="Food Desert Mapper",
            page_icon="🗺️",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        st.title("🗺️ Food Desert Mapper")
        st.markdown("""
            Explore grocery store locations interactively. Pan and zoom the map to discover 
            food access in different areas.
        """)
    
    @staticmethod
    def render_sidebar() -> Tuple[bool, str]:
        """
        Render sidebar controls.
        
        Returns:
            Tuple of (show_stores, search_address)
        """
        with st.sidebar:
            st.header("⚙️ Controls")
            
            # Toggle for showing stores
            show_stores = st.checkbox(
                "Show Grocery Stores",
                value=st.session_state.show_stores,
                help="Toggle visibility of grocery store markers"
            )
            
            st.markdown("---")
            
            # Address search
            st.subheader("📍 Search Location")
            search_address = st.text_input(
                "Enter an address:",
                placeholder="e.g., 123 Main St, New Brunswick, NJ",
                help="Search for an address to move the map"
            )
            
            search_button = st.button("🔍 Search", use_container_width=True)
            
            st.markdown("---")
            
            # Legend
            st.subheader("🎨 Store Types")
            st.markdown("""
                <div style='font-size: 14px;'>
                    🔴 <b>Supermarket</b><br>
                    🟢 <b>Grocery</b><br>
                    🟠 <b>Convenience</b><br>
                    🔵 <b>Marketplace</b><br>
                    ⚫ <b>Other</b>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Instructions
            with st.expander("ℹ️ How to Use"):
                st.markdown("""
                    1. **Pan the map** to explore different areas
                    2. **Zoom in/out** to adjust detail level
                    3. **Click markers** to see store details
                    4. **Search addresses** to jump to locations
                    5. **Toggle stores** to show/hide markers
                    
                    Store data loads automatically as you navigate!
                """)
            
            # Statistics
            if st.session_state.current_bounds:
                st.markdown("---")
                st.subheader("📊 Statistics")
                
                # Get current viewport stores
                bbox = calculate_bbox_from_bounds(st.session_state.current_bounds)
                
                if bbox:
                    bbox_str = bbox_to_string(bbox)
                    
                    if bbox_str in st.session_state.stores_cache:
                        store_count = len(st.session_state.stores_cache[bbox_str])
                        st.metric("Stores in View", store_count)
            
            return show_stores, search_address if search_button else ""
    
    @staticmethod
    def display_info_box(message: str, type: str = "info"):
        """
        Display an info box.
        
        Args:
            message: Message to display
            type: Type of message (info, success, warning, error)
        """
        if type == "info":
            st.info(message)
        elif type == "success":
            st.success(message)
        elif type == "warning":
            st.warning(message)
        elif type == "error":
            st.error(message)

# ============================================================================
# APPLICATION LOGIC
# ============================================================================

class AppLogic:
    """Handles main application logic."""
    
    @staticmethod
    def handle_address_search(address: str) -> Optional[Tuple[float, float]]:
        """
        Handle address search and update map center.
        
        Args:
            address: Address to search for
            
        Returns:
            Tuple of (latitude, longitude) or None
        """
        coords = geocode_address(address)
        
        if coords:
            st.session_state.map_center = list(coords)
            st.session_state.map_zoom = 15  # Zoom in when searching
            logger.info(f"Updated map center to {coords}")
            return coords
        
        return None
    
    @staticmethod
    def load_stores_for_bounds(bounds: Dict) -> List[Dict]:
        """
        Load stores for the current map bounds.
        
        Args:
            bounds: Map bounds dictionary
            
        Returns:
            List of store dictionaries
        """
        try:
            bbox = calculate_bbox_from_bounds(bounds)
            if not bbox:
                logger.warning("Could not calculate bbox from bounds")
                return []
            
            # Check cache first
            bbox_str = bbox_to_string(bbox)
            
            if bbox_str in st.session_state.stores_cache:
                logger.info(f"Using cached stores for {bbox_str}")
                return st.session_state.stores_cache[bbox_str]
            
            # Fetch from database/OSM
            logger.info(f"Fetching stores for bbox: {bbox}")
            stores = fetch_stores_in_bbox(bbox)
            
            # Cache the results
            st.session_state.stores_cache[bbox_str] = stores
            
            # Limit cache size to prevent memory issues
            if len(st.session_state.stores_cache) > 20:
                # Remove oldest entry
                oldest_key = next(iter(st.session_state.stores_cache))
                del st.session_state.stores_cache[oldest_key]
            
            logger.info(f"Loaded {len(stores)} stores for viewport")
            return stores
            
        except Exception as e:
            logger.error(f"Error loading stores: {e}")
            return []

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application function."""
    
    # Initialize UI
    UserInterface.render_header()
    
    try:
        # Render sidebar and get controls
        show_stores, search_address = UserInterface.render_sidebar()
        
        # Update session state
        st.session_state.show_stores = show_stores
        
        # Handle address search
        if search_address:
            coords = AppLogic.handle_address_search(search_address)
            if coords:
                st.success(f"✅ Found location: {coords[0]:.4f}, {coords[1]:.4f}")
                st.rerun()
            else:
                st.error("❌ Could not find address. Please try a different search.")
        
        # Create map
        stores = []
        if show_stores:
            # Use cached bounds or default
            if st.session_state.current_bounds:
                stores = AppLogic.load_stores_for_bounds(st.session_state.current_bounds)
            else:
                # Initial load - get stores around default center
                default_bbox = (
                    DEFAULT_CENTER[1] - 0.05,  # min_lon
                    DEFAULT_CENTER[0] - 0.05,  # min_lat
                    DEFAULT_CENTER[1] + 0.05,  # max_lon
                    DEFAULT_CENTER[0] + 0.05   # max_lat
                )
                stores = fetch_stores_in_bbox(default_bbox)
        
        # Create and display map
        m = MapManager.create_map_with_stores(
            st.session_state.map_center,
            st.session_state.map_zoom,
            stores,
            show_stores
        )
        
        # Display map and capture interactions
        map_data = st_folium(
            m,
            width=MAP_CONFIG["width"],
            height=MAP_CONFIG["height"],
            returned_objects=["bounds", "center", "zoom"]
        )
        
        # Update session state with new map position
        if map_data:
            if map_data.get("bounds"):
                st.session_state.current_bounds = map_data["bounds"]
                
                # Load stores for new bounds if they've changed significantly
                new_stores = AppLogic.load_stores_for_bounds(map_data["bounds"])
                
                # Only rerun if we got new stores and stores are being shown
                if show_stores and new_stores and len(new_stores) != len(stores):
                    logger.info("Bounds changed, reloading stores")
                    # Note: Automatic rerun might cause issues, so we'll let user navigate naturally
            
            if map_data.get("center"):
                st.session_state.map_center = [
                    map_data["center"]["lat"],
                    map_data["center"]["lng"]
                ]
            
            if map_data.get("zoom"):
                st.session_state.map_zoom = map_data["zoom"]
        
        # Display store count
        if show_stores and stores:
            st.info(f"📊 Showing {len(stores)} grocery stores in the current view")
        
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        st.error(f"❌ An error occurred: {str(e)}")
        
        with st.expander("🔧 Troubleshooting"):
            st.markdown("""
                - Check your internet connection
                - Verify database is running and accessible
                - Try refreshing the page
                - Check logs for detailed error information
            """)
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>"
        "<small>Food Desert Mapper | Powered by OpenStreetMap & GeoPandas</small>"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()