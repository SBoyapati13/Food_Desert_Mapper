import os
from pathlib import Path
import logging
from typing import Optional, Set, Any
from db_setup import execute_query

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def ensure_data_directory() -> Path:
    """
    Ensures the data directory and cache subdirectory exist at the project root. 
    Creates them if necessary.
    
    Returns:
        Path: The path to the data directory.
    """
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    cache_dir = data_dir / "cache"
    
    try:
        data_dir.mkdir(exist_ok=True)
        cache_dir.mkdir(exist_ok=True)
        logger.info(f"Data directory ensured at: {data_dir.resolve()}")
        logger.info(f"Cache directory ensured at: {cache_dir.resolve()}")
        return data_dir
    except OSError as e:
        logger.error(f"Failed to create data/cache directories: {e}")
        raise

def validate_database_environment(required_tables: Optional[Set[str]] = None) -> None:
    """
    Validates that the database environment is properly set up.
    
    Args:
        required_tables: Optional set of table names to check for existence
    
    Raises:
        RuntimeError: If database validation fails
    """
    try:
        if required_tables:
            # Check if required tables exist
            tables_query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = ANY(%s);
            """
            result = execute_query(tables_query, (list(required_tables),))
            existing_tables = {row[0] for row in (result or [])}
            missing_tables = required_tables - existing_tables
            
            if missing_tables:
                raise RuntimeError(f"Required tables {missing_tables} do not exist. Run db_setup.py first.")
        
        # Check if PostGIS extension is installed
        postgis_query = "SELECT postgis_version();"
        try:
            execute_query(postgis_query)
        except Exception:
            raise RuntimeError("PostGIS extension is not installed. Run db_setup.py first.")
            
        logger.info("Database environment validation passed")
    except Exception as e:
        logger.error(f"Database validation failed: {e}")
        raise

def get_entity_id(table: str, name_field: str, name: str, 
                  extra_field: Optional[str] = None, 
                  extra_value: Optional[str] = None) -> Optional[int]:
    """
    Get entity ID from database based on name and optional extra field.
    
    Args:
        table: Table name to query
        name_field: Name of the field containing the entity name
        name: Value to search for
        extra_field: Optional additional field for filtering
        extra_value: Value for the extra field
    
    Returns:
        Optional[int]: Entity ID if found, None otherwise
    """
    try:
        query = f"""
            SELECT id FROM {table} 
            WHERE {name_field} = %s AND {extra_field + ' = %s' if extra_field else 'TRUE'}
        """
        params = (name, extra_value) if extra_value else (name,)
        result = execute_query(query, params)
        return result[0][0] if result else None
    except Exception as e:
        logger.error(f"Database error getting entity ID: {e}")
        raise

def check_entity_exists(table: str, criteria: dict[str, Any]) -> bool:
    """
    Check if an entity exists in the database based on multiple criteria.
    
    Args:
        table: Table name to query
        criteria: Dictionary of field names and values to check
    
    Returns:
        bool: True if entity exists, False otherwise
    """
    try:
        conditions = " AND ".join(f"{k} = %s" for k in criteria.keys())
        query = f"""
            SELECT EXISTS (
                SELECT 1 FROM {table}
                WHERE {conditions}
            );
        """
        result = execute_query(query, tuple(criteria.values()))
        return bool(result and result[0][0])
    except Exception as e:
        logger.error(f"Database error checking entity existence: {e}")
        raise

def validate_string_input(value: str, field_name: str, allow_none: bool = False) -> None:
    """
    Validates a string input value.
    
    Args:
        value: The string value to validate
        field_name: Name of the field for error messages
        allow_none: Whether None is an acceptable value
    
    Raises:
        ValueError: If validation fails
    """
    if value is None and not allow_none:
        raise ValueError(f"{field_name} must not be None")
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field_name} must be a non-empty string")