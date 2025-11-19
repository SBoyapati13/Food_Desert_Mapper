"""
Food Desert Mapper - Streamlit Application

A web application to visualize areas in US cities with limited access
to fresh food sources by mapping grocery store locations.
"""

import streamlit as st
import logging
from datetime import datetime, timedelta

# Import modules
from config import Config
from city_fetcher import fetch_city_boundary, get_boundary_info, US_STATES
from grocery_fetcher import (
    fetch_grocery_stores,
    get_store_summary,
    get_unique_store_types,
    get_display_name,
    filter_stores_by_type
)
from db_setup import (
    check_city_exists,
    save_city_to_db,
    save_stores_to_db,
    get_city_from_db,
    get_stores_from_db,
    log_fetch_metadata
)
from utils.validation import validate_city_name, validate_state_name, sanitize_input
from utils.map_builder import create_full_map
from streamlit_folium import st_folium

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title=Config.APP_TITLE,
    page_icon=Config.APP_ICON,
    layout="wide",
    initial_sidebar_state=Config.SIDEBAR_STATE
)

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #2E86AB;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stat-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
        color: #2E86AB;
    }
    .stat-label {
        font-size: 0.9rem;
        color: #666;
    }
    </style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """Initialize session state variables."""
    if 'boundary_gdf' not in st.session_state:
        st.session_state.boundary_gdf = None
    if 'stores_gdf' not in st.session_state:
        st.session_state.stores_gdf = None
    if 'city_info' not in st.session_state:
        st.session_state.city_info = None
    if 'current_city' not in st.session_state:
        st.session_state.current_city = None
    if 'current_state' not in st.session_state:
        st.session_state.current_state = None
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'pending_city' not in st.session_state:
        st.session_state.pending_city = None
    if 'pending_state' not in st.session_state:
        st.session_state.pending_state = None
    if 'show_options' not in st.session_state:
        st.session_state.show_options = False
    if 'existing_city_id' not in st.session_state:
        st.session_state.existing_city_id = None

def render_header():
    """Render the application header."""
    st.markdown(f'<div class="main-header">{Config.APP_ICON} {Config.APP_TITLE}</div>', 
                unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{Config.APP_DESCRIPTION}</div>', 
                unsafe_allow_html=True)

def render_sidebar():
    """Render the sidebar with city selection."""
    st.sidebar.header("📍 Select a City")
    
    # City input
    city_input = st.sidebar.text_input(
        "City Name",
        value=st.session_state.current_city if st.session_state.current_city else "",
        placeholder="e.g., Philadelphia"
    )
    
    # State selection
    state_input = st.sidebar.selectbox(
        "State",
        options=[""] + US_STATES,
        index=US_STATES.index(st.session_state.current_state) + 1 
            if st.session_state.current_state in US_STATES else 0
    )
    
    # Fetch button
    fetch_clicked = st.sidebar.button("🔍 Fetch City Data", type="primary", use_container_width=True)
    
    # Process fetch request
    if fetch_clicked:
        if not city_input or not state_input:
            st.sidebar.error("Please enter both city and state")
        else:
            # Sanitize inputs
            city = sanitize_input(city_input)
            state = sanitize_input(state_input)
            
            # Validate inputs
            if not validate_city_name(city):
                st.sidebar.error("Invalid city name")
                return
            
            if not validate_state_name(state):
                st.sidebar.error("Invalid state name")
                return
            
            # Store pending city info
            st.session_state.pending_city = city
            st.session_state.pending_state = state
            
            # Check if city exists in database
            existing_city = check_city_exists(city, state, Config.DEFAULT_COUNTRY)
            
            if existing_city:
                # Show options
                st.session_state.show_options = True
                st.session_state.existing_city_id = existing_city['id']
                st.rerun()
            else:
                # Fetch new data directly
                st.session_state.show_options = False
                fetch_new_data(city, state)
                st.session_state.current_city = city
                st.session_state.current_state = state
                st.rerun()
    
    # Show options if city exists in database
    if st.session_state.show_options and st.session_state.existing_city_id:
        existing_city = check_city_exists(
            st.session_state.pending_city, 
            st.session_state.pending_state, 
            Config.DEFAULT_COUNTRY
        )
        
        if existing_city:
            st.sidebar.info(f"Found existing data from {existing_city['fetched_at'].strftime('%Y-%m-%d')}")
            
            col1, col2 = st.sidebar.columns(2)
            
            use_existing = col1.button("Use Existing", use_container_width=True, key="use_existing")
            re_fetch = col2.button("Re-fetch", use_container_width=True, key="re_fetch")
            
            if use_existing:
                logger.info(f"Use Existing clicked for city_id: {st.session_state.existing_city_id}")
                load_existing_data(st.session_state.existing_city_id)
                st.session_state.current_city = st.session_state.pending_city
                st.session_state.current_state = st.session_state.pending_state
                st.session_state.show_options = False
                st.session_state.existing_city_id = None
                st.session_state.pending_city = None
                st.session_state.pending_state = None
                st.rerun()
            
            if re_fetch:
                logger.info(f"Re-fetch clicked for: {st.session_state.pending_city}, {st.session_state.pending_state}")
                fetch_new_data(st.session_state.pending_city, st.session_state.pending_state)
                st.session_state.current_city = st.session_state.pending_city
                st.session_state.current_state = st.session_state.pending_state
                st.session_state.show_options = False
                st.session_state.existing_city_id = None
                st.session_state.pending_city = None
                st.session_state.pending_state = None
                st.rerun()
    
    # Display current data info if loaded
    if st.session_state.data_loaded and st.session_state.city_info:
        st.sidebar.divider()
        st.sidebar.subheader("📊 Current Data")
        
        info = st.session_state.city_info
        st.sidebar.markdown(f"**City:** {info['name']}, {info['state']}")
        st.sidebar.markdown(f"**Area:** {info['area_km2']:.2f} km²")
        
        if st.session_state.stores_gdf is not None:
            st.sidebar.markdown(f"**Stores:** {len(st.session_state.stores_gdf)}")
        
        # Clear data button
        if st.sidebar.button("🗑️ Clear Data", use_container_width=True):
            clear_session_state()
            st.rerun()

def load_existing_data(city_id: int):
    """
    Load existing data from database.
    
    Args:
        city_id: City ID in database
    """
    try:
        with st.spinner("Loading data from database..."):
            # Load boundary
            boundary_gdf = get_city_from_db(city_id)
            
            if boundary_gdf is None or boundary_gdf.empty:
                st.sidebar.error("Failed to load city boundary from database")
                logger.error(f"Failed to load boundary for city_id {city_id}")
                return
            
            # Load stores
            stores_gdf = get_stores_from_db(city_id)
            
            if stores_gdf is None:
                st.sidebar.error("Failed to load stores from database")
                logger.error(f"Failed to load stores for city_id {city_id}")
                return
            
            # Empty stores GeoDataFrame is OK (city might have no stores)
            if stores_gdf.empty:
                logger.info(f"No stores found for city_id {city_id}")
            
            # Update session state
            st.session_state.boundary_gdf = boundary_gdf
            st.session_state.stores_gdf = stores_gdf
            st.session_state.city_info = get_boundary_info(boundary_gdf)
            st.session_state.data_loaded = True
            
            st.sidebar.success("Data loaded successfully!")
            logger.info(f"Successfully loaded data for city_id {city_id}")
            
    except Exception as e:
        st.sidebar.error(f"Error loading data: {str(e)}")
        logger.error(f"Exception loading data for city_id {city_id}: {e}", exc_info=True)

def fetch_new_data(city: str, state: str):
    """
    Fetch new data from OpenStreetMap.
    
    Args:
        city: City name
        state: State name
    """
    start_time = datetime.now()
    
    # Fetch boundary
    with st.spinner(f"Fetching boundary for {city}, {state}..."):
        boundary_gdf = fetch_city_boundary(city, state, Config.DEFAULT_COUNTRY)
        
        if boundary_gdf is None or boundary_gdf.empty:
            st.sidebar.error(f"Could not find boundary for {city}, {state}")
            return
        
        st.sidebar.success("✓ Boundary fetched")
    
    # Fetch stores
    with st.spinner("Fetching grocery stores..."):
        stores_gdf = fetch_grocery_stores(boundary_gdf)
        
        if stores_gdf is None:
            st.sidebar.error("Failed to fetch grocery stores")
            return
        
        if stores_gdf.empty:
            st.sidebar.warning("No grocery stores found in this area")
        else:
            st.sidebar.success(f"✓ Found {len(stores_gdf)} stores")
    
    # Save to database
    with st.spinner("Saving to database..."):
        city_id = save_city_to_db(boundary_gdf)
        
        if city_id is None:
            st.sidebar.warning("Could not save city to database")
        else:
            stores_count = save_stores_to_db(stores_gdf, city_id)
            
            # Log metadata
            duration = (datetime.now() - start_time).total_seconds()
            log_fetch_metadata(
                city_id=city_id,
                status='success',
                stores_count=stores_count
            )
            
            st.sidebar.success("✓ Data saved to database")
    
    # Update session state
    st.session_state.boundary_gdf = boundary_gdf
    st.session_state.stores_gdf = stores_gdf
    st.session_state.city_info = get_boundary_info(boundary_gdf)
    st.session_state.data_loaded = True

def clear_session_state():
    """Clear all session state data."""
    st.session_state.boundary_gdf = None
    st.session_state.stores_gdf = None
    st.session_state.city_info = None
    st.session_state.current_city = None
    st.session_state.current_state = None
    st.session_state.data_loaded = False
    st.session_state.pending_city = None
    st.session_state.pending_state = None
    st.session_state.show_options = False
    st.session_state.existing_city_id = None

def render_statistics():
    """Render statistics about the current city."""
    if not st.session_state.data_loaded:
        return
    
    boundary_gdf = st.session_state.boundary_gdf
    stores_gdf = st.session_state.stores_gdf
    
    if boundary_gdf is None or boundary_gdf.empty:
        return
    
    # Get summary
    area = boundary_gdf['area_km2'].iloc[0]
    summary = get_store_summary(stores_gdf, area)
    
    # Display statistics
    st.subheader("📊 Statistics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(
            f"""
            <div class="stat-box">
                <div class="stat-number">{summary['total_stores']}</div>
                <div class="stat-label">Total Stores</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    with col2:
        st.markdown(
            f"""
            <div class="stat-box">
                <div class="stat-number">{area:.1f}</div>
                <div class="stat-label">Area (km²)</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    with col3:
        st.markdown(
            f"""
            <div class="stat-box">
                <div class="stat-number">{summary['stores_per_km2']:.2f}</div>
                <div class="stat-label">Stores per km²</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    # Store type breakdown
    if summary['store_types']:
        st.subheader("🏪 Store Types")
        
        # Create columns for store types
        store_types = summary['store_types']
        num_cols = min(3, len(store_types))
        cols = st.columns(num_cols)
        
        for idx, (store_type, count) in enumerate(store_types.items()):
            col_idx = idx % num_cols
            cols[col_idx].metric(
                label=get_display_name(store_type),
                value=count
            )

def render_map():
    """Render the interactive map."""
    if not st.session_state.data_loaded:
        st.info("👈 Select a city from the sidebar to get started")
        return
    
    boundary_gdf = st.session_state.boundary_gdf
    stores_gdf = st.session_state.stores_gdf
    
    if boundary_gdf is None or boundary_gdf.empty:
        st.warning("No boundary data available")
        return
    
    st.subheader("🗺️ Interactive Map")
    
    # Store type filter
    if stores_gdf is not None and not stores_gdf.empty:
        unique_types = get_unique_store_types(stores_gdf)
        
        if unique_types:
            st.write("**Filter by store type:**")
            
            # Create columns for checkboxes
            num_types = len(unique_types)
            num_cols = min(4, num_types)
            cols = st.columns(num_cols)
            
            selected_types = []
            for idx, store_type in enumerate(unique_types):
                col_idx = idx % num_cols
                if cols[col_idx].checkbox(
                    get_display_name(store_type),
                    value=True,
                    key=f"filter_{store_type}"
                ):
                    selected_types.append(store_type)
            
            # Filter stores
            if selected_types:
                filtered_stores = filter_stores_by_type(stores_gdf, selected_types)
            else:
                filtered_stores = stores_gdf
        else:
            filtered_stores = stores_gdf
    else:
        filtered_stores = stores_gdf
    
    # Create map
    with st.spinner("Creating map..."):
        m = create_full_map(
            boundary_gdf,
            filtered_stores,
            use_clusters=True,
            add_legend=True
        )
        
        # Display map
        st_folium(m, width=1200, height=600, returned_objects=[])

def main():
    """Main application function."""
    # Initialize
    initialize_session_state()
    
    # Render UI
    render_header()
    render_sidebar()
    
    # Main content
    if st.session_state.data_loaded:
        render_statistics()
        st.divider()
        render_map()
    else:
        # Welcome message
        st.info("""
        👋 **Welcome to the Food Desert Mapper!**
        
        This tool helps visualize areas in US cities with limited access to fresh food sources.
        
        **How to use:**
        1. Enter a city name and select a state from the sidebar
        2. Click "Fetch City Data" to load grocery store locations
        3. Explore the interactive map to see store distribution
        4. Use filters to view specific store types
        
        **Data Source:** OpenStreetMap
        """)

if __name__ == "__main__":
    main()