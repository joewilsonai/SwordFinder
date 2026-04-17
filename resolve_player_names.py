"""Resolve MLB player IDs to full names via MLB Stats API, with local caching.

Used by ingest scripts to populate batter_name / pitcher_name columns on insert.

Inputs:  list of MLB person IDs
Outputs: dict {id: fullName}
Side effects: reads/writes player_name_cache.json in this directory
Failure: unresolved IDs are omitted from the returned dict (not raised)
"""

import json
import os
from pathlib import Path
from typing import Iterable

import requests

_CACHE_PATH = Path(__file__).parent / "player_name_cache.json"
_MLB_API = "https://statsapi.mlb.com/api/v1/people"
_BATCH_SIZE = 50


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            with _CACHE_PATH.open() as f:
                return {int(k): v for k, v in json.load(f).items()}
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_PATH.open("w") as f:
        json.dump({str(k): v for k, v in cache.items()}, f)


def resolve_names(ids: Iterable[int], timeout: int = 30) -> dict:
    """Return {id: fullName} for all resolvable IDs. Caches results to disk."""
    ids = [int(x) for x in ids if x]
    cache = _load_cache()
    missing = [x for x in set(ids) if x not in cache]

    if not missing:
        return {x: cache[x] for x in ids if x in cache}

    for i in range(0, len(missing), _BATCH_SIZE):
        chunk = missing[i:i + _BATCH_SIZE]
        try:
            r = requests.get(
                _MLB_API,
                params={"personIds": ",".join(str(x) for x in chunk)},
                timeout=timeout,
            )
            r.raise_for_status()
            for p in r.json().get("people", []):
                pid = p.get("id")
                name = p.get("fullName") or p.get("nameFirstLast")
                if pid and name:
                    cache[pid] = name
        except Exception as e:
            print(f"  [resolve_names] batch {i // _BATCH_SIZE + 1} failed: {e}")

    _save_cache(cache)
    return {x: cache[x] for x in ids if x in cache}


if __name__ == "__main__":
    import sys
    ids = json.loads(sys.stdin.read()) if not sys.argv[1:] else [int(x) for x in sys.argv[1:]]
    print(json.dumps(resolve_names(ids), indent=2))
