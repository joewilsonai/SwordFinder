#!/usr/bin/env python3
"""Test imports for the video processing workflow"""

print("Testing imports...")

try:
    import os
    print("✓ os")
except Exception as e:
    print(f"✗ os: {e}")

try:
    import sys
    print("✓ sys")
except Exception as e:
    print(f"✗ sys: {e}")

try:
    from datetime import datetime, timedelta
    print("✓ datetime")
except Exception as e:
    print(f"✗ datetime: {e}")

try:
    import pandas as pd
    print("✓ pandas")
except Exception as e:
    print(f"✗ pandas: {e}")

try:
    from supabase import create_client
    print("✓ supabase")
except Exception as e:
    print(f"✗ supabase: {e}")

try:
    from dotenv import load_dotenv
    print("✓ dotenv")
except Exception as e:
    print(f"✗ dotenv: {e}")

try:
    import logging
    print("✓ logging")
except Exception as e:
    print(f"✗ logging: {e}")

try:
    from get_play_ids_on_demand import get_play_ids_for_pitches
    print("✓ get_play_ids_on_demand")
except Exception as e:
    print(f"✗ get_play_ids_on_demand: {e}")

try:
    from clean_video_processor import EnhancedSwordVideoProcessor
    print("✓ clean_video_processor")
except Exception as e:
    print(f"✗ clean_video_processor: {e}")

print("\nAll imports tested!") 