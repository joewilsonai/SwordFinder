from pathlib import Path


def test_homepage_has_date_picker_for_daily_slate():
    html = Path("ui/index.html").read_text()

    assert 'id="slate-date-input"' in html
    assert 'id="slate-refresh"' in html
    assert "Top 5 Daily Swords" in html


def test_homepage_loads_selected_date_top_five_swords():
    source = Path("ui/assets/index.js").read_text()

    assert "new URLSearchParams(window.location.search).get('date')" in source
    assert "refreshSlate" in source
    assert "limit: 5" in source
    assert "Sword #${idx + 1}" in source
