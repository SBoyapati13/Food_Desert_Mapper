"""
Food Desert Mapper - Streamlit Application (Enhanced with Accessibility Analysis)

A web application to visualize areas in US cities with limited access
to fresh food sources by mapping grocery store locations.
"""

import streamlit as st
import logging
from datetime import datetime

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
from utils.map_builder import create_full_map, add_analysis_point_to_map
from utils.geo_utils import find_nearest_store, count_stores_in_radius, buffer_geometry
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
    .accessibility-good {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .accessibility-limited {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .accessibility-desert {
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
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
    if 'analysis_point' not in st.session_state:
        st.session_state.analysis_point = None
    if 'show_analysis' not in st.session_state:
        st.session_state.show_analysis = False
    if 'analysis_radius' not in st.session_state:
        st.session_state.analysis_radius = 1.0
    if 'show_walkability_buffers' not in st.session_state:
        st.session_state.show_walkability_buffers = False
    if 'walkability_radius' not in st.session_state:
        st.session_state.walkability_radius = 1.0

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
    """Load existing data from database."""
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
    """Fetch new data from OpenStreetMap."""
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
    st.session_state.analysis_point = None
    st.session_state.show_analysis = False
    st.session_state.show_walkability_buffers = False
    st.session_state.walkability_radius = 1.0

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

def render_walkability_controls():
    """Render walkability buffer zone controls."""
    if not st.session_state.data_loaded:
        return
    
    stores_gdf = st.session_state.stores_gdf
    
    if stores_gdf is None or stores_gdf.empty:
        return
    
    st.subheader("🚶 Walkability Zones")
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        show_buffers = st.checkbox(
            "Show walkability zones",
            value=st.session_state.show_walkability_buffers,
            help="Display walking distance buffers around each store"
        )
        st.session_state.show_walkability_buffers = show_buffers
    
    with col2:
        if show_buffers:
            radius = st.select_slider(
                "Walking distance",
                options=[0.5, 0.8, 1.0, 1.5, 2.0],
                value=st.session_state.walkability_radius,
                format_func=lambda x: f"{x} km ({int(x/5*60)} min)",
                help="Distance people can walk to reach a store"
            )
            st.session_state.walkability_radius = radius
    
    with col3:
        if show_buffers:
            # Calculate coverage statistics
            boundary_gdf = st.session_state.boundary_gdf
            if boundary_gdf is not None and not boundary_gdf.empty:
                try:
                    # Create buffers around stores
                    buffered_stores = buffer_geometry(stores_gdf, st.session_state.walkability_radius * 1000)
                    
                    if buffered_stores is not None and not buffered_stores.empty:
                        # Calculate coverage area
                        from shapely.ops import unary_union
                        from shapely.geometry import Polygon, MultiPolygon
                        
                        # Merge all buffers into one geometry
                        merged_buffers = unary_union(buffered_stores.geometry)
                        
                        # Get city boundary as proper Shapely geometry
                        city_boundary_geom = boundary_gdf.geometry.iloc[0]
                        
                        # Ensure it's a valid geometry
                        if not isinstance(city_boundary_geom, (Polygon, MultiPolygon)):
                            st.warning("Invalid boundary geometry")
                            return
                        
                        # Calculate intersection (covered area within city)
                        covered_area_geom = merged_buffers.intersection(city_boundary_geom)
                        
                        # Calculate areas in projected CRS for accuracy
                        import geopandas as gpd
                        
                        # Create GeoDataFrames with proper geometry
                        covered_gdf = gpd.GeoDataFrame(
                            {'id': [1]},
                            geometry=gpd.GeoSeries([covered_area_geom]),
                            crs='EPSG:4326'
                        )
                        city_gdf = gpd.GeoDataFrame(
                            {'id': [1]},
                            geometry=gpd.GeoSeries([city_boundary_geom]),
                            crs='EPSG:4326'
                        )
                        
                        # Project to UTM for accurate area calculation
                        covered_projected = covered_gdf.to_crs(covered_gdf.estimate_utm_crs())
                        city_projected = city_gdf.to_crs(city_gdf.estimate_utm_crs())
                        
                        covered_area_km2 = covered_projected.geometry.area.iloc[0] / 1_000_000
                        city_area_km2 = city_projected.geometry.area.iloc[0] / 1_000_000
                        
                        coverage_pct = (covered_area_km2 / city_area_km2) * 100
                        
                        # Display coverage stats
                        st.markdown(f"""
                        **Coverage Statistics:**
                        - 🟢 Walkable area: **{covered_area_km2:.2f} km²** ({coverage_pct:.1f}% of city)
                        - 🔴 Not walkable: **{city_area_km2 - covered_area_km2:.2f} km²** ({100 - coverage_pct:.1f}% of city)
                        """)
                        
                except Exception as e:
                    logger.error(f"Error calculating coverage: {e}")
                    st.warning("Could not calculate coverage statistics")

def render_accessibility_analysis():
    """Render the accessibility analysis section."""
    if not st.session_state.data_loaded:
        return
    
    stores_gdf = st.session_state.stores_gdf
    
    if stores_gdf is None or stores_gdf.empty:
        return
    
    st.subheader("🎯 Accessibility Analysis")
    
    # Instructions
    st.info("👆 **Click anywhere on the map below** to analyze food access at that location")
    
    # Analysis controls
    col1, col2 = st.columns([1, 3])
    
    with col1:
        # Search radius slider
        radius = st.slider(
            "Search Radius (km)",
            min_value=0.5,
            max_value=5.0,
            value=st.session_state.analysis_radius,
            step=0.5,
            help="Distance to search for nearby stores"
        )
        st.session_state.analysis_radius = radius
    
    with col2:
        # Show analysis results if point is selected
        if st.session_state.analysis_point:
            lat, lon = st.session_state.analysis_point
            
            st.write(f"**Analyzing location:** {lat:.6f}, {lon:.6f}")
            
            # Find nearest store
            nearest = find_nearest_store((lat, lon), stores_gdf)
            
            # Count stores in radius
            count = count_stores_in_radius((lat, lon), stores_gdf, radius)
            
            # Display results in columns
            result_col1, result_col2, result_col3 = st.columns(3)
            
            with result_col1:
                if nearest:
                    store_idx, distance = nearest
                    store = stores_gdf.iloc[store_idx]
                    store_name = store['name'] if store['name'] else 'Unnamed Store'
                    
                    st.metric(
                        label="Nearest Store",
                        value=f"{distance:.2f} km",
                        help=f"{store_name} ({store['shop_type'].replace('_', ' ').title()})"
                    )
                else:
                    st.metric(label="Nearest Store", value="N/A")
            
            with result_col2:
                st.metric(
                    label=f"Stores within {radius} km",
                    value=count
                )
            
            with result_col3:
                # Calculate walking time to nearest store (assuming 5 km/h)
                if nearest:
                    _, distance = nearest  # Unpack again to ensure distance is in scope
                    walking_time = (distance / 5.0) * 60  # minutes
                    st.metric(
                        label="Walking Time",
                        value=f"{walking_time:.0f} min",
                        help="To nearest store at 5 km/h"
                    )
                else:
                    st.metric(
                        label="Walking Time",
                        value="N/A"
                    )
            
            # Accessibility classification
            st.divider()
            
            if count == 0:
                st.markdown(
                    """
                    <div class="accessibility-desert">
                        <h4>🔴 Food Desert</h4>
                        <p>No grocery stores found within the search radius. This area has severely limited access to fresh food.</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            elif count < 3:
                st.markdown(
                    """
                    <div class="accessibility-limited">
                        <h4>🟡 Limited Access</h4>
                        <p>Few grocery stores in the area. Residents may face challenges accessing fresh food options.</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    """
                    <div class="accessibility-good">
                        <h4>🟢 Good Access</h4>
                        <p>Multiple grocery stores available within walking or short driving distance.</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            # Detailed store list
            if count > 0:
                with st.expander(f"📋 View all {count} nearby stores"):
                    # Filter stores within radius
                    from shapely.geometry import Point
                    
                    point = Point(lon, lat)
                    radius_deg = radius / 111.0  # Rough conversion
                    
                    nearby_stores = []
                    for idx, store in stores_gdf.iterrows():
                        distance_deg = store.geometry.distance(point)
                        if distance_deg <= radius_deg:
                            distance_km = distance_deg * 111
                            nearby_stores.append({
                                'Name': store['name'] if store['name'] else 'Unnamed',
                                'Type': store['shop_type'].replace('_', ' ').title(),
                                'Distance (km)': round(distance_km, 2)
                            })
                    
                    # Sort by distance
                    nearby_stores.sort(key=lambda x: x['Distance (km)'])
                    
                    # Display as table
                    import pandas as pd
                    df = pd.DataFrame(nearby_stores)
                    st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.write("**Click on the map to analyze a location**")

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
        # Prepare walkability buffers if enabled
        walkability_gdf = None
        if st.session_state.show_walkability_buffers and filtered_stores is not None and not filtered_stores.empty:
            try:
                walkability_gdf = buffer_geometry(
                    filtered_stores, 
                    st.session_state.walkability_radius * 1000  # Convert km to meters
                )
            except Exception as e:
                logger.error(f"Error creating walkability buffers: {e}")
        
        m = create_full_map(
            boundary_gdf,
            filtered_stores,
            use_clusters=True,
            add_legend=True,
            analysis_point=st.session_state.analysis_point,
            analysis_radius=st.session_state.analysis_radius,
            walkability_gdf=walkability_gdf,
            walkability_radius=st.session_state.walkability_radius
        )
        
        # Display map and capture clicks
        map_data = st_folium(
            m, 
            width=1200, 
            height=600,
            returned_objects=["last_clicked"],
            key="main_map"  # Add key to prevent unnecessary reruns
        )
        
        # Store clicked location
        if map_data and map_data.get('last_clicked'):
            new_lat = map_data['last_clicked']['lat']
            new_lon = map_data['last_clicked']['lng']
            
            # Only update if coordinates changed significantly (to avoid re-runs on map panning)
            # Use a larger threshold to prevent infinite loops
            if (st.session_state.analysis_point is None or 
                abs(st.session_state.analysis_point[0] - new_lat) > 0.001 or
                abs(st.session_state.analysis_point[1] - new_lon) > 0.001):
                
                st.session_state.analysis_point = (new_lat, new_lon)
                st.session_state.show_analysis = True
                st.rerun()

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
        render_walkability_controls()
        st.divider()
        render_accessibility_analysis()
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
        4. **Click anywhere on the map** to analyze food accessibility at that location
        5. Use filters to view specific store types
        
        **Data Source:** OpenStreetMap
        """)

if __name__ == "__main__":
    main()