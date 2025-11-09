import os
from pathlib import Path
import logging
from typing import Optional
from dotenv import load_dotenv

# Configure logging
from .logger_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def load_environment() -> None:
    """
    Load environment variables from .env file.
    
    This function looks for a .env file in the project root directory
    and loads its contents into environment variables.
    
    Raises:
        FileNotFoundError: If .env file doesn't exist
        EnvironmentError: If required environment variables are missing
    """
    env_path = Path(__file__).parent.parent / '.env'
    if not env_path.exists():
        raise FileNotFoundError(f".env file not found at {env_path}")
    
    load_dotenv(dotenv_path=env_path)
    logger.info(f"Loaded environment variables from {env_path}")
    
    # Check for required environment variables
    required_vars = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASS']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

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

def validate_string_input(value: Optional[str], field_name: str, allow_none: bool = False) -> None:
    """
    Validates a string input value.
    
    Args:
        value: The string value to validate, can be None if allow_none is True
        field_name: Name of the field for error messages
        allow_none: Whether None is an acceptable value
    
    Raises:
        ValueError: If validation fails (None when not allowed, empty string, or non-string value)
        
    Examples:
        >>> validate_string_input("test", "name")  # OK
        >>> validate_string_input(None, "name", allow_none=True)  # OK
        >>> validate_string_input("", "name")  # Raises ValueError
        >>> validate_string_input(None, "name")  # Raises ValueError
    """
    if value is None:
        if not allow_none:
            raise ValueError(f"{field_name} must not be None")
        return
        
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string, got {type(value).__name__}")
        
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty or whitespace only")