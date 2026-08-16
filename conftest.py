"""Root conftest — project-level sys.path setup for local packages."""

import sys
from pathlib import Path

# Add local packages to sys.path so tests can import them
_project_root = Path(__file__).parent
_ft_client_dir = str(_project_root / "ft_client")

if _ft_client_dir not in sys.path:
    sys.path.insert(0, _ft_client_dir)