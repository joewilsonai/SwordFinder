"""Shared row-normalization helpers for SwordFinder API responses."""

def normalize_sword_row(row: dict) -> dict:
    """Present legacy sword rows from the hitter perspective."""
    normalized = dict(row)
    source_player_name = row.get("player_name")
    batter_name = row.get("batter_name")
    pitcher_name = row.get("pitcher_name") or source_player_name

    if batter_name:
        normalized["source_player_name"] = source_player_name
        normalized["player_name"] = batter_name
    normalized["pitcher_name"] = pitcher_name

    return normalized


def normalize_sword_rows(rows: list) -> list:
    return [normalize_sword_row(row) for row in rows]
