"""
Utility functions for the Food Desert Mapper.

This package contains helper modules for:
- Input validation
- Geometry processing
- Map building and visualization
"""

from .validation import (
    validate_city_name,
    validate_state_name,
    sanitize_input
)

from .geo_utils import (
    calculate_distance,
    get_bbox_from_gdf,
    simplify_geometry
)

from .map_builder import (
    create_base_map,
    add_boundary_to_map,
    add_stores_to_map
)

__all__ = [
    # Validation
    'validate_city_name',
    'validate_state_name',
    'sanitize_input',
    
    # Geo utilities
    'calculate_distance',
    'get_bbox_from_gdf',
    'simplify_geometry',
    
    # Map building
    'create_base_map',
    'add_boundary_to_map',
    'add_stores_to_map',
]