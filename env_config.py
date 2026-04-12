#!/usr/bin/env python3
"""
Environment helpers for SwordFinder.

Some historical `.env` files contain malformed lines where multiple variables
were accidentally concatenated. `get_env()` defensively returns only the first
token, which is sufficient for URL/key style values used by this project.
"""

import os
from typing import Optional


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch an environment variable with defensive whitespace/token cleanup."""
    value = os.getenv(name)
    if value is None:
        return default

    value = value.strip()
    if not value:
        return default

    return value.split()[0]
