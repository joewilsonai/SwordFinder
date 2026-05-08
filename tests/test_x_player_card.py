import json
import subprocess
from pathlib import Path


MODULE_PATH = Path("ui/api/watch/top-sword.js")


def run_node_helper(function_name, payload):
    script = f"""
const mod = require('./{MODULE_PATH.as_posix()}');
const result = mod.{function_name}({json.dumps(payload)});
console.log(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_top_sword_player_card_meta_uses_video_player_tags():
    row = {
        "batter_name": "Corey Seager",
        "pitcher_name": "De Los Santos, Yerry",
        "pitch_name": "Changeup",
        "release_speed": 88.9,
        "sword_score": 105.253,
        "bat_speed": 32.0,
        "strike_zone_distance_inches": 11.8,
        "video_azure_blob_url": "https://example.test/seager.mp4",
    }

    html = run_node_helper(
        "buildCardHtml",
        {
            "date": "2026-05-06",
            "rank": 1,
            "row": row,
            "baseUrl": "https://swordfinder.com",
        },
    )

    assert 'name="twitter:card" content="player"' in html
    assert 'name="twitter:player"' in html
    assert 'mode=player' in html
    assert 'name="twitter:player:stream" content="https://example.test/seager.mp4"' in html
    assert 'property="og:video" content="https://example.test/seager.mp4"' in html
    assert "Corey Seager" in html
    assert "Score 105.3" in html


def test_top_sword_player_page_renders_html5_video():
    row = {
        "batter_name": "Corey Seager",
        "pitcher_name": "De Los Santos, Yerry",
        "pitch_name": "Changeup",
        "release_speed": 88.9,
        "sword_score": 105.253,
        "video_azure_blob_url": "https://example.test/seager.mp4",
    }

    html = run_node_helper(
        "buildPlayerHtml",
        {
            "date": "2026-05-06",
            "rank": 1,
            "row": row,
            "baseUrl": "https://swordfinder.com",
        },
    )

    assert "<video" in html
    assert 'src="https://example.test/seager.mp4"' in html
    assert "playsinline" in html
    assert "SwordFinder" in html
