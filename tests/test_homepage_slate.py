from pathlib import Path


def test_homepage_has_date_picker_for_daily_slate():
    html = Path("ui/index.html").read_text()

    assert 'id="slate-date-input"' in html
    assert 'id="slate-refresh"' not in html
    assert ">Load</button>" not in html
    assert "Selected Date" in html
    assert "Top Sword Score" in html
    assert "Biggest Miss" in html
    assert "Clips Ready" in html
    assert 'id="draft-x-post"' in html
    assert 'id="x-draft-panel"' in html
    assert "Season Swords" not in html
    assert "Slowest Bat Today" not in html
    assert "Top 5 Daily Swords" in html


def test_homepage_loads_selected_date_top_five_swords():
    source = Path("ui/assets/index.js").read_text()

    assert "new URLSearchParams(window.location.search).get('date')" in source
    assert "refreshSlate" in source
    assert "dateInput.addEventListener('input'" in source
    assert "isCompleteDate" in source
    assert "refreshButton" not in source
    assert "/daily-slate" in source
    assert "ensure_videos: 'true'" in source
    assert "updateHeroMetricsFromSlate" in source
    assert "metric-clips-ready" in source
    assert "Pitch Stats" in source
    assert "Pitch Speed" in source
    assert "Effective" in source
    assert "Perceived" in source
    assert "Spin Rate" in source
    assert "release_spin_rate" in source
    assert "perceived_velocity" in source
    assert "/share/x/draft" in source
    assert "draftXPostButton" in source
    assert "copyXDraftButton" in source
    assert "fetchCount" not in source
    assert "Sword #${idx + 1}" in source
