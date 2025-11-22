"""
Map building utilities for the Food Desert Mapper.

Provides functions to create and customize Folium maps
for visualizing city boundaries and grocery store locations.
"""

import logging
import traceback
import sys
from pathlib import Path
from typing import Optional, List, Tuple
import folium
from folium.plugins import MarkerCluster
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from branca.element import MacroElement
from jinja2 import Template
import geopandas as gpd
from shapely.ops import unary_union

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config

logger = logging.getLogger(__name__)

def create_base_map(
    center: Optional[Tuple[float, float]] = None,
    zoom: Optional[int] = None
) -> folium.Map:
    """
    Create a base Folium map.
    
    Args:
        center: (latitude, longitude) tuple for map center
        zoom: Initial zoom level
        
    Returns:
        Folium Map object
    """
    if center is None:
        center = Config.DEFAULT_MAP_CENTER
    
    if zoom is None:
        zoom = Config.DEFAULT_MAP_ZOOM
    
    # Create map
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=Config.MAP_TILES,
        control_scale=True
    )
    
    return m

def add_boundary_to_map(
    map_obj: folium.Map,
    boundary_gdf: gpd.GeoDataFrame,
    zoom_to_bounds: bool = True
) -> folium.Map:
    """
    Add city boundary to a Folium map.
    
    Args:
        map_obj: Folium Map object
        boundary_gdf: GeoDataFrame with city boundary
        zoom_to_bounds: Whether to zoom map to boundary extent
        
    Returns:
        Updated Folium Map object
    """
    try:
        if boundary_gdf is None or boundary_gdf.empty:
            logger.warning("Empty boundary GeoDataFrame")
            return map_obj
        
        # Create a copy to avoid modifying the original
        boundary_copy = boundary_gdf.copy()

        # Convert any datetime/timestamp columns to strings for JSON serialization
        for col in boundary_copy.columns:
            if col != 'geometry' and boundary_copy[col].dtype == 'datetime64[ns]':
                boundary_copy[col] = boundary_copy[col].astype(str)
            elif col != 'geometry' and hasattr(boundary_copy[col].iloc[0], 'isoformat'):
                # Handle pandas Timestamp objects
                boundary_copy[col] = boundary_copy[col].apply(
                    lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x)
                )
        
        # Convert to GeoJSON
        boundary_geojson = boundary_copy.to_json()
        
        # Add boundary to map
        folium.GeoJson(
            boundary_geojson,
            name='City Boundary',
            style_function=lambda x: {
                'fillColor': Config.BOUNDARY_COLOR,
                'color': Config.BOUNDARY_COLOR,
                'weight': Config.BOUNDARY_WEIGHT,
                'fillOpacity': Config.BOUNDARY_FILL_OPACITY
            },
            tooltip=folium.Tooltip(
                f"<b>{boundary_copy['name'].iloc[0]}, {boundary_copy['state'].iloc[0]}</b><br>"
                f"Area: {boundary_copy['area_km2'].iloc[0]:.2f} km²"
            )
        ).add_to(map_obj)
        
        # Zoom to boundary
        if zoom_to_bounds:
            bounds = boundary_copy.total_bounds
            map_obj.fit_bounds([
                [bounds[1], bounds[0]],  # Southwest
                [bounds[3], bounds[2]]   # Northeast
            ])
        
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding boundary to map: {e}")
        logger.error(traceback.format_exc())
        return map_obj
    
def add_stores_to_map(
    map_obj: folium.Map,
    stores_gdf: gpd.GeoDataFrame,
    use_clusters: bool = True,
    color_by_type: bool = True
) -> folium.Map:
    """
    Add grocery stores to a Folium map.
    
    Args:
        map_obj: Folium Map object
        stores_gdf: GeoDataFrame with store locations
        use_clusters: Whether to use marker clustering
        color_by_type: Whether to color markers by store type
        
    Returns:
        Updated Folium Map object
    """
    try:
        if stores_gdf is None or stores_gdf.empty:
            logger.warning("Empty stores GeoDataFrame")
            return map_obj
        
        # Create a copy to avoid modifying the original
        stores_copy = stores_gdf.copy()
        
        # Convert any datetime/timestamp columns to strings for JSON serialization
        for col in stores_copy.columns:
            if col != 'geometry' and stores_copy[col].dtype == 'datetime64[ns]':
                stores_copy[col] = stores_copy[col].astype(str)
            elif col != 'geometry' and hasattr(stores_copy[col].iloc[0], 'isoformat'):
                # Handle pandas Timestamp objects
                try:
                    stores_copy[col] = stores_copy[col].apply(
                        lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x)
                    )
                except:
                    pass
        
        # Create marker cluster if enabled
        if use_clusters and Config.USE_MARKER_CLUSTERS:
            marker_cluster = MarkerCluster(
                name='Grocery Stores',
                overlay=True,
                control=True
            ).add_to(map_obj)
            parent = marker_cluster
        else:
            parent = map_obj
        
        # Add each store as a marker
        for idx, store in stores_copy.iterrows():
            # Get coordinates
            lat = store.geometry.y
            lon = store.geometry.x
            
            # Get store info
            name = store.get('name', 'Unnamed Store')
            shop_type = store.get('shop_type', 'unknown')
            
            # Get color
            if color_by_type:
                color = Config.get_store_color(shop_type)
            else:
                color = Config.DEFAULT_STORE_COLOR
            
            # Create popup content
            popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 150px;">
                <h4 style="margin: 0 0 10px 0;">{name if name else 'Unnamed Store'}</h4>
                <p style="margin: 5px 0;">
                    <b>Type:</b> {shop_type.replace('_', ' ').title()}
                </p>
            </div>
            """
            
            # Create marker
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=name if name else shop_type.title(),
                color="black",
                fill=True,
                fillColor=color,
                fillOpacity=0.7,
                weight=2
            ).add_to(parent)
        
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding stores to map: {e}")
        logger.error(traceback.format_exc())
        return map_obj
    
def add_walkability_buffers_to_map(
        map_obj: folium.Map,
        walkability_gdf: gpd.GeoDataFrame,
        radius_km: float
) -> folium.Map:
    """
    Add walkability buffer zones to map.
    
    Args:
        map_obj: Folium Map object
        walkability_gdf: GeoDataFrame with buffered store geometries
        radius_km: Buffer radius in kilometers (for labeling)
        
    Returns:
        Updated Folium Map object
    """
    try:
        if walkability_gdf is None or walkability_gdf.empty:
            logger.warning("Empty walkability GeoDataFrame")
            return map_obj
        
        # Create a copy to avoid modifying the original
        buffer_copy = walkability_gdf.copy()
        
        # Merge all buffers into a single geometry for cleaner visualization
        merged_geometry = unary_union(buffer_copy.geometry)
        
        # Create a GeoDataFrame with the merged geometry
        merged_gdf = gpd.GeoDataFrame(
            geometry=[merged_geometry], 
            crs=buffer_copy.crs
        )
        
        # Convert to GeoJSON
        buffer_geojson = merged_gdf.to_json()
        
        # Calculate walking time for tooltip
        walking_time = int((radius_km / 5.0) * 60)
        
        # Add to map with semi-transparent green
        folium.GeoJson(
            buffer_geojson,
            name=f'Walkability Zones ({radius_km} km / {walking_time} min)',
            style_function=lambda x: {
                'fillColor': '#28a745',
                'color': '#155724',
                'weight': 2,
                'fillOpacity': 0.2,
                'dashArray': '5, 5'
            },
            tooltip=folium.Tooltip(
                f"<b>Walkable Area</b><br>"
                f"Distance: {radius_km} km<br>"
                f"Walking time: ~{walking_time} min"
            )
        ).add_to(map_obj)
        
        logger.info(f"Added walkability buffers with {radius_km} km radius")
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding walkability buffers: {e}")
        logger.error(traceback.format_exc())
        return map_obj

def add_analysis_point_to_map(
    map_obj: folium.Map,
    point: Tuple[float, float],
    radius_km: float
) -> folium.Map:
    """
    Add accessibility analysis point and search radius to map.
    
    Args:
        map_obj: Folium Map object
        point: (latitude, longitude) tuple
        radius_km: Search radius in kilometers
        
    Returns:
        Updated Folium Map object
    """
    try:
        lat, lon = point

        # Add the analysis point marker
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(
                f"""
                <div style="font-family: Arial, sans-serif;">
                    <h4 style="margin: 0 0 5px 0;">Analysis Point</h4>
                    <p style="margin: 5px 0; font-size: 12px;">
                        <b>Lat:</b> {lat:.6f}<br>
                        <b>Lon:</b> {lon:.6f}<br>
                        <b>Radius:</b> {radius_km} km
                    </p>
                </div>
                """,
                max_width=200
            ),
            tooltip="Click location (analysis point)",
            icon=folium.Icon(
                color='red',
                icon='info-sign',
                prefix='glyphicon'
            )
        ).add_to(map_obj)

        # Add search radius circle
        # Convert km to meters for accurate circle
        radius_meters = radius_km * 1000
        
        folium.Circle(
            location=[lat, lon],
            radius=radius_meters,
            color='#FF4444',
            fill=True,
            fillColor='#FF4444',
            fillOpacity=0.1,
            weight=2,
            popup=f"Search radius: {radius_km} km",
            tooltip=f"{radius_km} km radius"
        ).add_to(map_obj)
        
        logger.info(f"Added analysis point at ({lat}, {lon}) with {radius_km} km radius")
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding analysis point to map: {e}")
        logger.error(traceback.format_exc())
        return map_obj

def create_legend(store_types: List[str]) -> str:
    """
    Create HTML legend for store types.
    
    Args:
        store_types: List of store types to include in legend
        
    Returns:
        HTML string for legend
    """
    # Use absolute positioning within the map container
    legend_html = '''
    <div id="map-legend" style="
        position: absolute;
        top: 10px;
        right: 10px;
        width: 220px;
        background-color: white;
        border: 2px solid #333;
        border-radius: 8px;
        padding: 15px;
        font-family: 'Arial', sans-serif;
        font-size: 13px;
        z-index: 1000;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        pointer-events: auto;
    ">
        <h4 style="
            margin: 0 0 12px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid #ddd;
            color: #333;
            font-size: 15px;
            font-weight: bold;
        ">Store Types</h4>
    '''
    
    for store_type in store_types:
        color = Config.get_store_color(store_type)
        display_name = store_type.replace('_', ' ').title()
        
        legend_html += f'''
        <div style="
            margin: 8px 0;
            display: flex;
            align-items: center;
        ">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                background-color: {color};
                border-radius: 50%;
                margin-right: 8px;
                border: 2px solid #333;
                flex-shrink: 0;
            "></span>
            <span style="color: #333;">{display_name}</span>
        </div>
        '''
    
    legend_html += '</div>'
    
    return legend_html

def add_legend_to_map(
    map_obj: folium.Map,
    store_types: List[str]
) -> folium.Map:
    """
    Add a legend to the map.
    
    Args:
        map_obj: Folium Map object
        store_types: List of store types to include in legend
        
    Returns:
        Updated Folium Map object
    """
    try:
        if not store_types:
            logger.warning("No store types provided for legend")
            return map_obj
        
        legend_html = create_legend(store_types)
        
        # Wrap the legend in a template
        template = """
        {% macro html(this, kwargs) %}
        """ + legend_html + """
        {% endmacro %}
        """
        
        macro = MacroElement()
        macro._template = Template(template)
        
        # Add to the map's HTML
        map_obj.get_root().add_child(macro)
        
        logger.info(f"Added legend with {len(store_types)} store types")
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding legend to map: {e}")
        logger.error(traceback.format_exc())
        return map_obj
    
def create_full_map(
    boundary_gdf: gpd.GeoDataFrame,
    stores_gdf: gpd.GeoDataFrame,
    use_clusters: bool = True,
    add_legend: bool = True,
    analysis_point: Optional[Tuple[float, float]] = None,
    analysis_radius: float = 1.0,
    walkability_gdf: Optional[gpd.GeoDataFrame] = None,
    walkability_radius: float = 1.0
) -> folium.Map:
    """
    Create a complete map with boundary, stores, and optional analysis point.
    
    Args:
        boundary_gdf: GeoDataFrame with city boundary
        stores_gdf: GeoDataFrame with store locations
        use_clusters: Whether to use marker clustering
        add_legend: Whether to add a legend
        analysis_point: Optional (lat, lon) tuple for accessibility analysis
        analysis_radius: Radius for accessibility analysis in km
        walkability_gdf: Optional GeoDataFrame with walkability buffer geometries
        walkability_radius: Radius used for walkability buffers in km
        
    Returns:
        Complete Folium Map object
    """
    try:
        # Get center from boundary
        if boundary_gdf is not None and not boundary_gdf.empty:
            geom = boundary_gdf.geometry.iloc[0]
        
            # Type check for Shapely geometry
            if not isinstance(geom, (Polygon, MultiPolygon)):
                logger.error("Geometry must be Polygon or MultiPolygon")
                raise TypeError("Geometry must be Polygon or MultiPolygon")

            centroid = geom.centroid
            center = (centroid.y, centroid.x)  # (lat, lon)
            zoom = Config.CITY_ZOOM_LEVEL
        else:
            center = None
            zoom = None
        
        # Create base map
        m = create_base_map(center=center, zoom=zoom)
        
        # Add boundary
        if boundary_gdf is not None and not boundary_gdf.empty:
            m = add_boundary_to_map(m, boundary_gdf)
        
        # Add walkability buffers FIRST (so they appear under everything else)
        if walkability_gdf is not None and not walkability_gdf.empty:
            m = add_walkability_buffers_to_map(m, walkability_gdf, walkability_radius)
        
        # Add analysis point (under stores but above buffers)
        if analysis_point is not None:
            m = add_analysis_point_to_map(m, analysis_point, analysis_radius)
        
        # Add stores (on top of analysis circle)
        if stores_gdf is not None and not stores_gdf.empty:
            m = add_stores_to_map(m, stores_gdf, use_clusters=use_clusters)
            
            # Add legend
            if add_legend:
                unique_types = sorted(stores_gdf['shop_type'].unique().tolist())
                m = add_legend_to_map(m, unique_types)
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        return m
        
    except Exception as e:
        logger.error(f"Error creating full map: {e}")
        # Return empty map on error
        return create_base_map()
    
if __name__ == "__main__":
    """Test map building."""
    print("=" * 60)
    print("Map Builder Test")
    print("=" * 60)
    
    # Create a simple test map
    print("\nCreating base map...")
    m = create_base_map()
    print("✓ Base map created")
    
    # Test would require actual GeoDataFrames
    print("\nNote: Full testing requires actual city and store data")
    print("Run the main application to see maps in action")