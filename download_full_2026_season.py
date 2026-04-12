#!/usr/bin/env python3
"""
Download full 2026 MLB season data.

Wrapper around the shared season downloader with 2026 defaults.
"""

import argparse
from datetime import datetime

from download_full_2025_season import download_full_season


def parse_args():
    parser = argparse.ArgumentParser(description="Download 2026 MLB Statcast season data.")
    parser.add_argument("--start-date", type=str, default="2026-03-25")
    parser.add_argument("--end-date", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--output-file", type=str, default="mlb_2026_full_season_complete.csv")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved settings only.")
    return parser.parse_args()


def main():
    args = parse_args()
    download_full_season(
        year=2026,
        start_date=args.start_date,
        end_date=args.end_date,
        output_file=args.output_file,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
