import logging
from pathlib import Path

def setup_logging() -> None:
    """Configure logging for the entire application."""
    # Create logs directory if it doesn't exist
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Console handler
            logging.StreamHandler(),
            # File handler
            logging.FileHandler(log_dir / "app.log")
        ]
    )
    
    # Reduce logging level for some third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("osmnx").setLevel(logging.WARNING)
    logging.getLogger("shapely").setLevel(logging.WARNING)
    logging.getLogger("fiona").setLevel(logging.WARNING)
    logging.getLogger("geopandas").setLevel(logging.WARNING)