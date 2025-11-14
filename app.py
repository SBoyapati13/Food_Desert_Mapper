import streamlit as st
import folium
import logging
import geopandas as gpd
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List, Union, Dict
from streamlit_folium import st_folium

# Import from our package
from scripts.city_fetcher import fetch_city_boundary
from scripts.grocery_fetcher import GroceryStoreFetcher, update_stores_for_city
from scripts.logger_config import setup_logging

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================

MAP_CONFIG = {
    "zoom_start": 11,
    "tiles": "OpenStreetMap"
}

GEOJSON_STYLE = {
    'fillColor': '#3388ff',
    'color': '#003d99',
    'fillOpacity': 0.2,
    'weight': 2
}

# Initialize session state with default values
DEFAULT_SESSION_STATE = {
    "city_gdf": None,
    "current_city": None,
    "current_country": None,
    "stores_gdf": None,
    "stores_updated": False,
    "last_update_time": None,
    "total_stores": 0,
    "new_stores": 0,
    "available_matches": None,  # NEW: Store multiple city matches
    "selected_osm_id": None    # NEW: Store selected OSM ID
}

for key, value in DEFAULT_SESSION_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================================
# DATA MANAGEMENT (Base utilities for data fetching and caching)
# ============================================================================

class DataManager:
    """Handles data caching and retrieval for the application."""
    
    @staticmethod
    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def load_city_boundary(
        city_name: str, 
        country_name: Optional[str] = None,
        osm_id: Optional[int] = None
    ) -> Union[gpd.GeoDataFrame, Tuple[None, List[Dict]]]:
        """
        Load city boundary data.
        
        Returns:
            Either a GeoDataFrame (single match) or Tuple[None, List[Dict]] (multiple matches)
        """
        return fetch_city_boundary(city_name, country_name, osm_id)
    
    @staticmethod
    @st.cache_data(ttl=300)
    def get_all_city_stores(city_name: str, country_name: Optional[str] = None) -> gpd.GeoDataFrame:
        """Get all stores for a given city."""
        try:
            fetcher = GroceryStoreFetcher()
            city_id = fetcher._get_city_id(city_name, country_name)

            if not city_id:
                logger.warning(f"City {city_name} not found in database.")
                return gpd.GeoDataFrame()
            
            from scripts.db_setup import execute_query
            query = """
                SELECT store_name, shop_type, ST_AsText(location) as geometry
                FROM grocery_stores
                WHERE city_id = %s
            """
            rows = execute_query(query, (city_id,))

            if not rows:
                return gpd.GeoDataFrame()
            
            df = pd.DataFrame(rows, columns=['store_name', 'shop_type', 'geometry'])
            gdf = gpd.GeoDataFrame(
                df,
                geometry=gpd.GeoSeries.from_wkt(df['geometry']),
                crs="EPSG:4326"
            )

            return gdf
        
        except Exception as e:
            logger.error(f"Error getting city stores: {e}")
            return gpd.GeoDataFrame()

    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)
    def update_city_stores(city_name: str, country_name: Optional[str] = None) -> Tuple[int, int]:
        """
        Update store data for a city.
        
        Args:
            city_name: Name of the city to update stores for
            country_name: Optional country name for disambiguation
            
        Returns:
            Tuple containing:
            - total_stores: Total number of stores in the city
            - new_stores: Number of newly added stores
            
        Note:
            This method is cached for 5 minutes (300 seconds) to prevent
            too frequent updates to the database. Existing stores will
            be updated if their data has changed.
        """
        logger.info(f"Updating stores for {city_name} (cached for 5 minutes)")
        return update_stores_for_city(city_name, country_name)

# ============================================================================
# MAP MANAGEMENT (Core map creation and manipulation functions)
# ============================================================================

class MapManager:
    """Handles map creation and updates."""
    
    @staticmethod
    def create_base_map(center: List[float], zoom: int = MAP_CONFIG["zoom_start"]) -> folium.Map:
        """Create a base Folium map centered at the given coordinates."""
        return folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=MAP_CONFIG["tiles"]
        )

    @staticmethod
    def get_boundary_area(city_gdf: gpd.GeoDataFrame) -> float:
        """Calculate boundary area, handling geographic vs projected CRS."""
        if city_gdf.crs and city_gdf.crs.is_geographic:
            # Reproject to projected CRS for accurate area calculation
            city_gdf_projected = city_gdf.to_crs(epsg=3857)  # Web Mercator
            return city_gdf_projected.geometry.area.sum()
        return city_gdf.geometry.area.sum()

    @staticmethod
    def format_area(area: float) -> str:
        """Format area value with appropriate unit."""
        if area >= 1e6:
            return f"{area / 1e6:.2f} million sq units"
        elif area >= 1e3:
            return f"{area / 1e3:.2f}K sq units"
        return f"{area:,.2f} sq units"

    @staticmethod
    def add_city_boundary(m: folium.Map, city_gdf: gpd.GeoDataFrame) -> None:
        """Add city boundary to the map."""
        city_json = city_gdf.to_json()
        folium.GeoJson(
            city_json,
            style_function=lambda x: GEOJSON_STYLE
        ).add_to(m)

    @staticmethod
    def add_stores_to_map(m: folium.Map, stores_gdf: gpd.GeoDataFrame) -> None:
        """Add store markers to the map with detailed information."""
        if stores_gdf is None or stores_gdf.empty:
            return
            
        for idx, row in stores_gdf.iterrows():
            # Extract coordinates from point geometry
            coords = row.geometry.coords[0]
            
            # Get store details
            store_name = row.get('store_name', 'Unnamed Store')
            shop_type = row.get('shop_type', 'Unknown')
            
            # Format distance if available
            distance_text = ""
            if 'distance' in row:
                distance_meters = float(row['distance'])
                if distance_meters < 1000:
                    distance_text = f"<br>Distance: {distance_meters:.0f}m"
                else:
                    distance_text = f"<br>Distance: {distance_meters/1000:.1f}km"
            
            # Create detailed popup
            popup_text = f"""
                <div style='min-width: 200px'>
                    <h4>{store_name}</h4>
                    <b>Type:</b> {shop_type}
                    {distance_text}
                </div>
            """
            
            # Add marker with custom icon based on shop type
            icon_color = 'green'  # default
            if shop_type == 'supermarket':
                icon_color = 'red'
            elif shop_type == 'convenience':
                icon_color = 'orange'
            elif shop_type == 'marketplace':
                icon_color = 'blue'
                
            folium.Marker(
                location=[coords[1], coords[0]],  # [lat, lon]
                popup=folium.Popup(popup_text, max_width=300),
                icon=folium.Icon(color=icon_color, icon='info-sign')
            ).add_to(m)

    @staticmethod
    def display_map(
        city_gdf: gpd.GeoDataFrame, 
        stores_gdf: Optional[gpd.GeoDataFrame] = None,
        center: Optional[List[float]] = None
    ) -> folium.Map:
        """Create and return a map with city boundary and optional store markers."""
        if center is None:
            # Project to Web Mercator for accurate centroid calculation
            if city_gdf.crs and city_gdf.crs.is_geographic:
                # Convert to projected CRS for accurate centroid
                projected = city_gdf.to_crs(epsg=3857)
                # Calculate centroid and convert back to original CRS
                bounds = projected.geometry.total_bounds
                center_x = (bounds[0] + bounds[2]) / 2
                center_y = (bounds[1] + bounds[3]) / 2
                centroid_point = gpd.points_from_xy([center_x], [center_y], crs=3857)
                centroid_point = centroid_point.to_crs(city_gdf.crs)[0]
            else:
                # If already in projected CRS, calculate centroid directly
                bounds = city_gdf.geometry.total_bounds
                center_x = (bounds[0] + bounds[2]) / 2
                center_y = (bounds[1] + bounds[3]) / 2
                centroid_point = gpd.points_from_xy([center_x], [center_y], crs=city_gdf.crs)[0]
                
            # Extract coordinates from the centroid point
            center = [centroid_point.coords[0][1], centroid_point.coords[0][0]]  # [lat, lon]
        
        # Create and populate map
        m = MapManager.create_base_map(center)
        MapManager.add_city_boundary(m, city_gdf)
        
        if stores_gdf is not None and not stores_gdf.empty:
            MapManager.add_stores_to_map(m, stores_gdf)
        
        return m

    @staticmethod
    def display_metrics(city_gdf: gpd.GeoDataFrame) -> None:
        """Display boundary metrics in columns."""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Geometry Type", city_gdf.geometry.type.iloc[0])
        
        with col2:
            st.metric("Total Polygons", len(city_gdf))
        
        with col3:
            total_area = MapManager.get_boundary_area(city_gdf)
            st.metric("Total Area", MapManager.format_area(total_area))

# ============================================================================
# USER INTERFACE (UI rendering and display functions)
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
            This application helps you explore urban food deserts by visualizing city boundaries
            and analyzing food availability across different neighborhoods.
        """)

    @staticmethod
    def render_sidebar() -> Tuple[str, Optional[str]]:
        """Get user inputs from sidebar."""
        with st.sidebar:
            st.header("Search Parameters")
            
            city = st.text_input(
                "City Name:",
                placeholder="e.g., New York City, London, Tokyo",
                help="The name of the city you want to explore"
            )
            
            country = st.text_input(
                "Country (optional):",
                placeholder="e.g., USA, UK, Japan",
                help="Helps disambiguate cities with the same name"
            )
            
            # Add helpful tips
            st.markdown("---")
            st.markdown(
                "<small>💡 **Tip:** Adding a country name helps find the correct city "
                "if there are multiple matches.</small>",
                unsafe_allow_html=True
            )
            
            return city, country if country else None

    @staticmethod
    def display_city_selection(matches: List[Dict]) -> Optional[int]:
        """
        Display UI for selecting from multiple city matches.
        
        Args:
            matches: List of city match dictionaries
            
        Returns:
            Selected OSM ID or None
        """
        st.warning(f"⚠️ Found {len(matches)} possible matches. Please select the correct city:")
        
        options = []
        for i, match in enumerate(matches):
            display_name = match.get('display_name', 'Unknown')
            osm_type = match.get('osm_type', 'unknown')
            options.append(f"{i+1}. {display_name} (OSM Type: {osm_type})")
        
        selected = st.radio("Select a city:", options, key="city_selectior")
        
        if selected:
            selected_idx = int(selected.split(".")[0]) - 1
            selected_match = matches[selected_idx]

            with st.expander("📍 Selected City Details"):
                st.write(f"**Name:** {selected_match.get('name', 'Unknown')}")
                st.write(f"**Full Name:** {selected_match.get('display_name', 'Unknown')}")
                st.write(f"**Type:** {selected_match.get('osm_type', 'Unknown')}")
                st.write(f"**OSM ID:** {selected_match.get('osm_id', 'Unknown')}")

            if st.button("✅ Confirm Selection", type="primary"):
                return selected_match.get('osm_id')
        
        return None

    @staticmethod
    def display_welcome():
        """Display welcome message for new users."""
        st.info(
            "👋 **Welcome to the Food Desert Mapper!**\n\n"
            "**How to use:**\n"
            "1. Enter a city name in the sidebar\n"
            "2. (Optional) Enter a country to disambiguate\n"
            "3. Click 'Load City' to fetch and visualize the city boundary and grocery stores\n"
            "4. Click 'Update Stores' to refresh store data from OpenStreetMap\n\n"
            "All data will be saved to the database for future analysis."
        )
    
    @staticmethod
    def display_footer():
        """Display page footer."""
        st.markdown("---")
        st.markdown(
            "<div style='text-align: center; color: gray;'>"
            "<small>Food Desert Mapper | Powered by OpenStreetMap & GeoPandas</small>"
            "</div>",
            unsafe_allow_html=True
        )

# ============================================================================
# APPLICATION LOGIC (Core business logic and state management)
# ============================================================================

class AppLogic:
    """Handles main application logic and state management."""
    
    @staticmethod
    def update_stores(
        city_name: str, 
        country_name: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        Update store data for selected city.
        
        Args:
            city_name: Name of the city to update stores for
            country_name: Optional country name for disambiguation
            
        Returns:
            Tuple containing:
            - total_stores: Total number of stores in the city
            - new_stores: Number of newly added stores
            
        Note: Existing stores will be updated if their data has changed.
        """
        logger.info(f"Updating stores for {city_name}")
        try:
            total_stores, new_stores = DataManager.update_city_stores(city_name, country_name)
            
            # Update session state
            st.session_state.stores_updated = True
            st.session_state.last_update_time = pd.Timestamp.now()
            st.session_state.total_stores = total_stores
            st.session_state.new_stores = new_stores

            # Reload stores for display
            stores_gdf = DataManager.get_all_city_stores(city_name, country_name)
            st.session_state.stores_gdf = stores_gdf
            
            # Log results
            if new_stores > 0:
                logger.info(f"Added {new_stores} new stores")
            else:
                logger.info("No new stores added")
                
            return total_stores, new_stores
            
        except Exception as e:
            logger.error(f"Failed to update stores: {e}")
            st.session_state.stores_updated = False
            raise
    
    @staticmethod
    def process_city_selection(
        city_name: str, 
        country_name: Optional[str] = None,
        osm_id: Optional[int] = None
    ) -> Tuple[Optional[gpd.GeoDataFrame], Optional[List[Dict]]]:
        """
        Process city selection and return boundary data or matches.
        
        Returns:
            Tuple of (GeoDataFrame or None, List of matches or None)
        """
        logger.info(f"Processing city: '{city_name}', country: '{country_name}', osm_id: {osm_id}")
        
        # Input validation and cleaning
        if not isinstance(city_name, str):
            raise ValueError("City name must be a non-empty string.")
            
        city_name = city_name.strip()
        if not city_name:
            raise ValueError("City name cannot be empty or whitespace only.")
        
        country_name = country_name.strip() if country_name and isinstance(country_name, str) else None
        
        try:
            result = DataManager.load_city_boundary(city_name, country_name, osm_id)
            
            # Check if we got multiple matches
            if isinstance(result, tuple):
                # Multiple matches found
                _, matches = result
                logger.info(f"Found {len(matches)} matches for '{city_name}'")
                return None, matches
            
            # Single match found
            city_gdf = result
            
            if city_gdf is None or city_gdf.empty:
                raise RuntimeError(f"No boundary data found for '{city_name}'")

            # Update session state
            st.session_state.city_gdf = city_gdf
            st.session_state.current_city = city_name
            st.session_state.current_country = country_name
            st.session_state.available_matches = None

            logger.info(f"Successfully processed city selection for {city_name}")
            return city_gdf, None

        except Exception as e:
            logger.error(f"Failed to process city selection: {e}")
            raise

# ============================================================================
# MAIN APPLICATION (Entry point and main execution flow)
# ============================================================================

def main():
    """Main application function."""
    # Initialize UI
    UserInterface.render_header()
    
    try:
        # Get user inputs
        city_name, country_name = UserInterface.render_sidebar()

        # Add action buttons
        col1, col2 = st.sidebar.columns(2)
        load_button = col1.button("🔍 Load City", use_container_width=True)
        update_button = col2.button("🔄 Update Stores", use_container_width=True)

        # Handel city loading
        if load_button and city_name:
            with st.spinner(f"🔍 Fetching boundary for {city_name}..."):
                city_gdf, matches = AppLogic.process_city_selection(city_name, country_name)

                if matches:
                    # Store matches for selection
                    st.session_state.available_matches = matches
                    st.rerun()
                    
                elif city_gdf is not None:
                    st.success(f"✅ Successfully loaded {city_name}!")
                    st.rerun()

        # Handle multiple matches selection
        if st.session_state.available_matches:
            selected_osm_id = UserInterface.display_city_selection(st.session_state.available_matches)
            
            if selected_osm_id:
                with st.spinner("🔍 Loading selected city..."):
                    city_gdf, _ = AppLogic.process_city_selection(
                        city_name, 
                        country_name, 
                        osm_id=selected_osm_id
                    )
                    if city_gdf is not None:
                        st.success(f"✅ Successfully loaded {city_name}!")
                        st.session_state.available_matches = None
                        st.rerun()

        # Handle store updates
        if update_button and st.session_state.city_gdf is not None:
            with st.spinner("🔄 Updating store data..."):
                total_stores, new_stores = AppLogic.update_stores(
                    st.session_state.current_city,
                    st.session_state.current_country
                )
                
                if new_stores > 0:
                    st.success(f"✅ Added {new_stores} new stores!")

                else:
                    st.info(f"ℹ️ Database is up to date ({total_stores} stores)")
                st.rerun()

        # Display content based on state
        if st.session_state.city_gdf is not None and not st.session_state.available_matches:
            st.markdown("---")
            MapManager.display_metrics(st.session_state.city_gdf)
            st.markdown("---")

            st.subheader("🗺️ City Boundary & Grocery Stores")

            # Display store count if available
            if st.session_state.stores_gdf is not None and not st.session_state.stores_gdf.empty:
                st.info(f"📊 Showing {len(st.session_state.stores_gdf)} grocery stores")

            # Create and display map
            m = MapManager.display_map(
                st.session_state.city_gdf,
                st.session_state.stores_gdf
            )
            st_folium(m, width=700, height=500, key="main_map")

        elif not st.session_state.available_matches:
            UserInterface.display_welcome()

    except ValueError as val_error:
        st.error(f"❌ Input Error: {str(val_error)}")
        logger.error(f"Validation error: {val_error}")
        
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        logger.error(f"Application error: {e}", exc_info=True)
        
        # Show troubleshooting tips
        with st.expander("🔧 Troubleshooting Tips"):
            st.markdown("""
            - Verify the spelling of the city name
            - Try adding the country name for disambiguation
            - Check your internet connection
            - Ensure the database is properly configured
            - Check logs for detailed error information
            """)

    UserInterface.display_footer()

if __name__ == "__main__":
    main()