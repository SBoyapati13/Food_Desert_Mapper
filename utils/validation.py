"""
Input validation utilities for the Food Desert Mapper.

Provides functions to validate and sanitize user inputs
for city names, states, and other text fields.
"""

import re
from typing import Any

def validate_city_name(city: str) -> bool:
    """
    Validate that a city name is acceptable.
    
    Args:
        city: City name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not city or not isinstance(city, str):
        return False
    
    # Remove whitespace
    city = city.strip()
    
    # Check if empty after stripping
    if not city:
        return False
    
    # Check minimum length
    if len(city) < 2:
        return False
    
    # Check maximum length
    if len(city) > 100:
        return False
    
    # City names should contain at least one letter
    if not any(c.isalpha() for c in city):
        return False
    
    # Allow letters, spaces, hyphens, apostrophes, and periods
    # This covers most city names like "St. Louis", "O'Fallon", "Winston-Salem"
    pattern = r"^[a-zA-Z\s\-'.]+$"
    
    if not re.match(pattern, city):
        return False
    
    return True

def validate_state_name(state: str) -> bool:
    """
    Validate that a state name is acceptable.
    
    Args:
        state: State name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not state or not isinstance(state, str):
        return False
    
    # Remove whitespace
    state = state.strip()
    
    # Check if empty after stripping
    if not state:
        return False
    
    # Check minimum length
    if len(state) < 2:
        return False
    
    # Check maximum length
    if len(state) > 50:
        return False
    
    # State names should contain at least one letter
    if not any(c.isalpha() for c in state):
        return False
    
    # Allow letters, spaces, hyphens, and periods
    pattern = r"^[a-zA-Z\s\-.]+$"
    
    if not re.match(pattern, state):
        return False
    
    return True

def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing extra whitespace and normalizing.
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Title case for proper formatting (e.g., "new york" -> "New York")
    text = text.title()
    
    return text

def validate_coordinates(lat: float, lon: float) -> bool:
    """
    Validate that latitude and longitude are valid coordinates.
    
    Args:
        lat: Latitude
        lon: Longitude
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False
    
    # Check latitude range
    if lat < -90 or lat > 90:
        return False
    
    # Check longitude range
    if lon < -180 or lon > 180:
        return False
    
    return True

def is_valid_osm_id(osm_id: Any) -> bool:
    """
    Validate that an OSM ID is valid.
    
    Args:
        osm_id: OpenStreetMap ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        # OSM IDs should be positive integers
        osm_id_int = int(osm_id)
        return osm_id_int > 0
    except (ValueError, TypeError):
        return False
    
def validate_store_type(store_type: str) -> bool:
    """
    Validate that a store type is acceptable.
    
    Args:
        store_type: Store type to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not store_type or not isinstance(store_type, str):
        return False
    
    # Remove whitespace
    store_type = store_type.strip()
    
    # Check if empty
    if not store_type:
        return False
    
    # Check length
    if len(store_type) > 50:
        return False
    
    # Allow letters, numbers, underscores
    pattern = r"^[a-zA-Z0-9_]+$"
    
    if not re.match(pattern, store_type):
        return False
    
    return True

def format_error_message(field: str, error_type: str) -> str:
    """
    Format a user-friendly error message.
    
    Args:
        field: Field name that has an error
        error_type: Type of error
        
    Returns:
        Formatted error message
    """
    error_messages = {
        'empty': f"{field} cannot be empty",
        'invalid_chars': f"{field} contains invalid characters",
        'too_short': f"{field} is too short",
        'too_long': f"{field} is too long",
        'no_letters': f"{field} must contain at least one letter",
        'not_found': f"{field} not found"
    }
    
    return error_messages.get(error_type, f"Invalid {field}")

if __name__ == "__main__":
    """Test validation functions."""
    print("=" * 60)
    print("Validation Tests")
    print("=" * 60)
    
    # Test city names
    print("\nCity Name Validation:")
    test_cities = [
        ("Philadelphia", True),
        ("St. Louis", True),
        ("O'Fallon", True),
        ("Winston-Salem", True),
        ("", False),
        ("  ", False),
        ("A", False),
        ("City123", False),
        ("City@Name", False),
    ]
    
    for city, expected in test_cities:
        result = validate_city_name(city)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{city}': {result}")
    
    # Test state names
    print("\nState Name Validation:")
    test_states = [
        ("Pennsylvania", True),
        ("New York", True),
        ("N.Y.", True),
        ("", False),
        ("A", False),
        ("State123", False),
    ]
    
    for state, expected in test_states:
        result = validate_state_name(state)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{state}': {result}")
    
    # Test sanitization
    print("\nInput Sanitization:")
    test_inputs = [
        "  new   york  ",
        "philadelphia",
        "CHICAGO",
    ]
    
    for text in test_inputs:
        sanitized = sanitize_input(text)
        print(f"  '{text}' -> '{sanitized}'")