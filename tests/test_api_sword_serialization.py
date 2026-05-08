from api import normalize_sword_row


def test_normalize_sword_row_uses_batter_name_for_player_name():
    row = {
        "batter": 608369,
        "batter_name": "Corey Seager",
        "pitcher": 660787,
        "pitcher_name": "De los Santos, Yerry",
        "player_name": "De los Santos, Yerry",
    }

    normalized = normalize_sword_row(row)

    assert normalized["player_name"] == "Corey Seager"
    assert normalized["pitcher_name"] == "De los Santos, Yerry"
    assert normalized["source_player_name"] == "De los Santos, Yerry"


def test_normalize_sword_row_keeps_pitcher_fallback_when_pitcher_name_missing():
    row = {
        "batter": 123,
        "batter_name": "Example Hitter",
        "pitcher": 456,
        "pitcher_name": None,
        "player_name": "Example Pitcher",
    }

    normalized = normalize_sword_row(row)

    assert normalized["player_name"] == "Example Hitter"
    assert normalized["pitcher_name"] == "Example Pitcher"
