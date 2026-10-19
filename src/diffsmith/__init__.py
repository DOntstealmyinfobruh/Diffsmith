"""Diffsmith: turn a plain-English request into a tested Git commit."""

from .agent import Diffsmith, EditResult
from .config import Config

__all__ = ["Diffsmith", "EditResult", "Config"]
__version__ = "0.2.0"
