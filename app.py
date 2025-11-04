import streamlit as st
import folium
import logging
import os
from pathlib import Path
from streamlit_folium import st_folium

# Add scripts directory to path for importing city_fetcher
import sys
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from city_fetcher import fetch_city_boundary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    'weight': 2,
    'opacity': 0.7,
    'fillOpacity': 0.5
}

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

@st.cache_data
def load_boundary_data(city_name: str, country_name=None):
    """
    Load city boundary data with caching to improve performance.
    
    Parameters:
    city_name (str): Name of the city
    country_name (str, optional): Name of the country
    
    Returns:
    GeoDataFrame: The city boundary data
    """
    return fetch_city_boundary(city_name, country_name)


def get_cached_geojson_path(city_name: str) -> Path:
    """
    Get the path to a cached GeoJSON file.
    
    Parameters:
    city_name (str): Name of the city
    
    Returns:
    Path: Path to the GeoJSON file
    """
    safe_filename = city_name.replace(' ', '_').lower()
    return DATA_DIR / f"{safe_filename}_boundary.geojson"


def format_area(area: float) -> str:
    """
    Format area value with appropriate unit.
    
    Parameters:
    area (float): Area value in square units
    
    Returns:
    str: Formatted area string
    """
    if area >= 1e6:
        return f"{area / 1e6:.2f} million sq units"
    elif area >= 1e3:
        return f"{area / 1e3:.2f}K sq units"
    else:
        return f"{area:,.2f} sq units"


def get_boundary_area(city_gdf) -> float:
    """
    Calculate boundary area, handling geographic vs projected CRS.
    
    Parameters:
    city_gdf (GeoDataFrame): City boundary data
    
    Returns:
    float: Total area in appropriate units
    """
    # Check if CRS is geographic (lat/lon)
    if city_gdf.crs and city_gdf.crs.is_geographic:
        # Reproject to projected CRS for accurate area calculation
        city_gdf_projected = city_gdf.to_crs(epsg=3857)  # Web Mercator
        return city_gdf_projected.geometry.area.sum()
    else:
        return city_gdf.geometry.area.sum()


def create_city_map(city_gdf) -> folium.Map:
    """
    Create a folium map with city boundary visualization.
    
    Parameters:
    city_gdf (GeoDataFrame): City boundary data
    
    Returns:
    folium.Map: The created map object
    """
    # Calculate centroid for map centering (using modern union_all method)
    centroid = city_gdf.geometry.union_all().centroid
    
    # Create base map
    m = folium.Map(
        location=[centroid.y, centroid.x],
        zoom_start=MAP_CONFIG["zoom_start"],
        tiles=MAP_CONFIG["tiles"]
    )
    
    # Add GeoJSON layer with styling
    folium.GeoJson(
        city_gdf,
        style_function=lambda x: GEOJSON_STYLE,
        tooltip=folium.GeoJsonTooltip(
            fields=['name'] if 'name' in city_gdf.columns else []
        )
    ).add_to(m)
    
    return m


def display_boundary_metrics(city_gdf) -> None:
    """
    Display boundary metrics in columns.
    
    Parameters:
    city_gdf (GeoDataFrame): City boundary data
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Geometry Type", city_gdf.geometry.type.iloc[0])
    
    with col2:
        st.metric("Total Polygons", len(city_gdf))
    
    with col3:
        total_area = get_boundary_area(city_gdf)
        st.metric("Total Area", format_area(total_area))


def display_download_section(city_name) -> None:
    """
    Display GeoJSON download button.
    
    Parameters:
    city_name (str): Name of the city
    """
    geojson_path = get_cached_geojson_path(city_name)
    
    if geojson_path.exists():
        try:
            with open(geojson_path, 'r') as f:
                geojson_content = f.read()
            
            st.download_button(
                label="📥 Download GeoJSON",
                data=geojson_content,
                file_name=geojson_path.name,
                mime="application/geo+json",
                key=f"download_{city_name}"
            )
            logger.info(f"Download option provided for {city_name}")
        except Exception as e:
            logger.error(f"Error preparing GeoJSON download: {e}")
            st.warning("Could not prepare download file.")


# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Food Desert Mapper",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main {
        padding-top: 0rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize session state
if 'city_gdf' not in st.session_state:
    st.session_state.city_gdf = None
if 'current_city' not in st.session_state:
    st.session_state.current_city = None


# ============================================================================
# MAIN APPLICATION
# ============================================================================

# Header
st.title("🗺️ Food Desert Mapper")
st.markdown("""
This application helps you explore urban food deserts by visualizing city boundaries
and analyzing food availability across different neighborhoods.
""")

# Sidebar
st.sidebar.header("📍 City Boundary Fetcher")
st.sidebar.markdown("---")

# Input fields
city_name = st.sidebar.text_input(
    "Enter City Name",
    value="",
    placeholder="e.g., New York City, London, Tokyo",
    help="The name of the city you want to explore"
)

country_name = st.sidebar.text_input(
    "Enter Country Name (Optional)",
    value="",
    placeholder="e.g., USA, UK, Japan",
    help="Helps disambiguate cities with the same name"
)

# Load button
load_button = st.sidebar.button(
    "📥 Load City Boundary",
    width='stretch',
    key="load_city_btn"
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<small>💡 **Tip:** Adding a country name helps find the correct city if there are multiple matches.</small>",
    unsafe_allow_html=True
)


# ============================================================================
# MAIN CONTENT LOGIC
# ============================================================================

if load_button:
    # Input validation
    if not city_name or not city_name.strip():
        st.error("❌ Please enter a city name.")
        logger.warning("User attempted to load boundary with empty city name")
        st.stop()
    
    # Fetch and display data
    with st.spinner(f"🔍 Fetching boundary for {city_name}..."):
        try:
            logger.info(f"User requested city boundary: city='{city_name}', country='{country_name}'")
            
            # Fetch boundary data
            city_gdf = load_boundary_data(
                city_name,
                country_name.strip() if country_name.strip() else None
            )
            
            # Store in session state
            st.session_state.city_gdf = city_gdf
            st.session_state.current_city = city_name
            
            logger.info(f"Successfully fetched boundary for {city_name}")
            
        except ValueError as val_error:
            st.error(f"❌ Input Validation Error: {str(val_error)}")
            logger.error(f"Validation error: {val_error}")
            st.stop()
            
        except Exception as e:
            error_message = str(e)
            st.error(f"❌ Error loading city boundary: {error_message}")
            logger.error(f"Error fetching city boundary: {e}", exc_info=True)
            
            # Provide helpful suggestions
            st.info(
                "💡 **Troubleshooting Tips:**\n\n"
                "- Verify the spelling of the city name\n"
                "- Try adding the country name for disambiguation\n"
                "- Check your internet connection\n"
                "- OpenStreetMap may have limited data for very small cities"
            )
            st.stop()

# Display results if data is in session state
if st.session_state.city_gdf is not None:
    city_gdf = st.session_state.city_gdf
    current_city = st.session_state.current_city
    
    st.success(f"✅ Successfully loaded boundary for {current_city}")
    
    # Display metrics
    st.markdown("---")
    display_boundary_metrics(city_gdf)
    st.markdown("---")
    
    # Display map
    st.subheader("🗺️ City Boundary Map")
    try:
        city_map = create_city_map(city_gdf)
        st_folium(city_map, width=700, height=500)
        logger.info(f"Map displayed successfully for {current_city}")
    except Exception as map_error:
        st.error(f"❌ Error displaying map: {str(map_error)}")
        logger.error(f"Map display error: {map_error}", exc_info=True)
    
    # Display raw data
    with st.expander("📊 View Raw Boundary Data"):
        # Convert geometry to string for display to avoid Arrow serialization errors
        display_gdf = city_gdf.copy()
        display_gdf['geometry'] = display_gdf['geometry'].astype(str)
        st.dataframe(display_gdf, width='stretch')
        logger.info(f"User viewed raw data for {current_city}")
    
    # Download section
    st.markdown("---")
    st.subheader("📥 Download Data")
    display_download_section(current_city)

else:
    # Welcome message
    st.info(
        "👋 **Welcome to the Food Desert Mapper!**\n\n"
        "**How to use:**\n"
        "1. Enter a city name in the sidebar\n"
        "2. (Optional) Enter a country to disambiguate\n"
        "3. Click 'Load City Boundary' to fetch and visualize\n\n"
        "Boundary data will be saved and available for future analysis."
    )


# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "<small>Food Desert Mapper | Powered by OpenStreetMap & GeoPandas</small>"
    "</div>",
    unsafe_allow_html=True
)