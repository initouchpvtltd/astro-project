"""Astrological Formula Search API.

The .env file is loaded here, before any other module reads its settings.
"""

from .config import load_env

load_env()
