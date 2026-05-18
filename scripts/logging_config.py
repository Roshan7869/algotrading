"""Logging Configuration - Structured logging for all components"""

import logging
import logging.handlers
from pathlib import Path


def setup_logging():
    """Configure logging for all components."""

    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Define formatters
    detailed_formatter = logging.Formatter(
        "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(console_handler)

    # File handlers for each component
    components = ["orchestrator", "telegram", "health_monitor", "process_manager"]

    for component in components:
        logger = logging.getLogger(component)

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{component}.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
