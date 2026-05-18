from pathlib import Path


def test_leaderboards_has_pitch_type_search_control():
    html = Path("ui/leaderboards.html").read_text()

    assert 'id="pitch-type-filter"' in html
    assert "Search by pitch type" in html
    assert 'id="clear-pitch-filter"' in html
    assert 'id="leaderboard-heading"' in html


def test_leaderboards_filters_season_swords_by_pitch_type():
    source = Path("ui/assets/leaderboards.js").read_text()

    assert "activePitchType" in source
    assert "normalizePitchType" in source
    assert "fetchPitchTypeOptions" in source
    assert "select: 'pitch_type,pitch_name'" in source
    assert "pitch_type: 'not.is.null'" in source
    assert "params.pitch_type = `eq.${activePitchType}`" in source
    assert "if (activePitchType) setActiveRange('season')" in source
    assert "new URLSearchParams(window.location.search)" in source
    assert "params.get('pitch_type') || params.get('pitch')" in source
    assert "Top ${activePitchType} Sword Events" in source
