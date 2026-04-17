"""Backfill batter_name column by looking up MLB Stats API for each unique batter ID.

Inputs:  batter IDs from mlb_pitches_enhanced (fetched from Supabase)
Outputs: UPDATE SQL statements printed to stdout (or run directly via psycopg2 if DATABASE_URL works)
Side effects: HTTPS calls to statsapi.mlb.com (free, no auth)
Failure behavior: skips IDs the API can't resolve; prints how many failed at end.
"""

import json
import os
import sys
import warnings

import requests
from urllib3.exceptions import NotOpenSSLWarning

warnings.simplefilter('ignore', NotOpenSSLWarning)

MLB_API = "https://statsapi.mlb.com/api/v1/people"
BATCH_SIZE = 50


def lookup_names(ids):
    """Return {id: fullName} dict using MLB Stats API bulk lookup."""
    out = {}
    failed = []
    for i in range(0, len(ids), BATCH_SIZE):
        chunk = ids[i:i + BATCH_SIZE]
        try:
            r = requests.get(
                MLB_API,
                params={"personIds": ",".join(str(x) for x in chunk)},
                timeout=30,
            )
            r.raise_for_status()
            for person in r.json().get("people", []):
                pid = person.get("id")
                name = person.get("fullName") or person.get("nameFirstLast")
                if pid and name:
                    out[pid] = name
            returned = {p["id"] for p in r.json().get("people", [])}
            missing = [x for x in chunk if x not in returned]
            failed.extend(missing)
            print(f"  batch {i//BATCH_SIZE + 1}/{(len(ids) + BATCH_SIZE - 1)//BATCH_SIZE}: got {len(r.json().get('people', []))}/{len(chunk)}", file=sys.stderr)
        except Exception as e:
            print(f"  batch {i//BATCH_SIZE + 1} error: {e}", file=sys.stderr)
            failed.extend(chunk)
    return out, failed


def main():
    # Read ids from stdin or arg
    if len(sys.argv) > 1:
        ids = json.loads(open(sys.argv[1]).read())
    else:
        ids = json.loads(sys.stdin.read())
    ids = [int(x) for x in ids]
    print(f"Looking up {len(ids)} batter IDs via MLB Stats API...", file=sys.stderr)
    names, failed = lookup_names(ids)
    print(f"Resolved: {len(names)}  Failed: {len(failed)}", file=sys.stderr)
    if failed:
        print(f"  Unresolved IDs: {failed[:20]}{' ...' if len(failed) > 20 else ''}", file=sys.stderr)
    json.dump(names, sys.stdout)


if __name__ == "__main__":
    main()
