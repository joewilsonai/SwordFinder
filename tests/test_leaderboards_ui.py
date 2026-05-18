from pathlib import Path


def test_leaderboards_has_pitch_type_search_control():
    html = Path("ui/leaderboards.html").read_text()

    assert 'id="pitch-type-filter"' in html
    assert "Search by pitch family or type" in html
    assert 'id="clear-pitch-filter"' in html
    assert 'id="pitch-family-rail"' in html
    assert 'data-pitch-filter="family:fastballs"' in html
    assert 'data-pitch-filter="family:breaking"' in html
    assert 'data-pitch-filter="family:offspeed"' in html
    assert 'id="pitch-type-chip-list"' in html
    assert 'id="leaderboard-heading"' in html
    assert 'id="leaderboard-cards" class="grid gap-6"' in html
    assert "Top 5 By Pitch Type" in html


def test_leaderboards_shows_top_five_sections_by_pitch_type():
    source = Path("ui/assets/leaderboards.js").read_text()

    assert "PITCH_FAMILIES" in source
    assert "Fastballs" in source
    assert "Breaking Balls" in source
    assert "Offspeed" in source
    assert "activePitchFilter" in source
    assert "normalizePitchType" in source
    assert "selectedPitchCodes" in source
    assert "fetchPitchTypeOptions" in source
    assert "fetchLeaderboardRows" in source
    assert "bindVideoHover" in source
    assert "renderLeaderboardVideo" in source
    assert "video_azure_blob_url" in source
    assert "videoPreviewUrl" in source
    assert "#t=${seconds}" in Path("ui/assets/supabase-rest.js").read_text()
    assert "leaderboard-pitch-grid" in source
    assert "leaderboard-feature-card" in source
    assert "select: 'pitch_type,pitch_name'" in source
    assert "pitch_type: 'not.is.null'" in source
    assert "params.pitch_type = `eq.${pitchType}`" in source
    assert "family.codes" in source
    assert "group.length < 5" in source
    assert "Top ${group.rows.length}" in source
    assert "new URLSearchParams(window.location.search)" in source
    assert "params.get('pitch_group')" in source
    assert "params.get('pitch_type') || params.get('pitch')" in source
    assert "url.searchParams.set('pitch_group', pitchFamily.id)" in source
    assert "pitchFamilyRail" in source
    assert "renderPitchTypeChips" in source
    assert "bindPitchExplorer" in source
    assert "data-pitch-filter" in source
