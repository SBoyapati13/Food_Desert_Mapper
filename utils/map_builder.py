"""
Map building utilities for the Food Desert Mapper.

Provides functions to create and customize Folium maps
for visualizing city boundaries and grocery store locations.
"""

import logging
import sys
from pathlib import Path
from typing import Optional, List, Tuple
import folium
from folium.plugins import MarkerCluster
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon

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
        
        # Convert to GeoJSON
        boundary_geojson = boundary_gdf.to_json()
        
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
                f"<b>{boundary_gdf['name'].iloc[0]}, {boundary_gdf['state'].iloc[0]}</b><br>"
                f"Area: {boundary_gdf['area_km2'].iloc[0]:.2f} km²"
            )
        ).add_to(map_obj)
        
        # Zoom to boundary
        if zoom_to_bounds:
            bounds = boundary_gdf.total_bounds
            map_obj.fit_bounds([
                [bounds[1], bounds[0]],  # Southwest
                [bounds[3], bounds[2]]   # Northeast
            ])
        
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding boundary to map: {e}")
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
        for idx, store in stores_gdf.iterrows():
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
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.7,
                weight=2
            ).add_to(parent)
        
        return map_obj
        
    except Exception as e:
        logger.error(f"Error adding stores to map: {e}")
        return map_obj
    
def create_legend(store_types: List[str]) -> str:
    """
    Create HTML legend for store types.
    
    Args:
        store_types: List of store types to include in legend
        
    Returns:
        HTML string for legend
    """
    legend_html = '''
    <div style="
        position: fixed;
        bottom: 50px;
        right: 50px;
        width: 200px;
        background-color: white;
        border: 2px solid grey;
        border-radius: 5px;
        padding: 10px;
        font-family: Arial, sans-serif;
        font-size: 12px;
        z-index: 9999;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
    ">
        <h4 style="margin: 0 0 10px 0;">Store Types</h4>
    '''
    
    for store_type in store_types:
        color = Config.get_store_color(store_type)
        display_name = store_type.replace('_', ' ').title()
        
        legend_html += f'''
        <div style="margin: 5px 0;">
            <span style="
                display: inline-block;
                width: 12px;
                height: 12px;
                background-color: {color};
                border-radius: 50%;
                margin-right: 5px;
                border: 1px solid #333;
            "></span>
            {display_name}
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
        legend_html = create_legend(store_types)
        map_obj.get_root().add_child(folium.Element(legend_html))
        return map_obj
    except Exception as e:
        logger.error(f"Error adding legend to map: {e}")
        return map_obj
    
def create_full_map(
    boundary_gdf: gpd.GeoDataFrame,
    stores_gdf: gpd.GeoDataFrame,
    use_clusters: bool = True,
    add_legend: bool = True
) -> folium.Map:
    """
    Create a complete map with boundary and stores.
    
    Args:
        boundary_gdf: GeoDataFrame with city boundary
        stores_gdf: GeoDataFrame with store locations
        use_clusters: Whether to use marker clustering
        add_legend: Whether to add a legend
        
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
        
        # Add stores
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