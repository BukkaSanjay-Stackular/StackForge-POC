"""
SDLC Pipeline — Automate requirements → design → user stories.
"""

__version__ = "2.0.0"
__author__ = "Stackular AI"

from pipeline.utils.config import load_config, get_config
from pipeline.utils.llm_client import create_client