from pathlib import Path


def test_shared_layout_mounts_first_visit_intro():
    source = Path("ui/assets/layout.js").read_text()

    assert "swordfinder:intro:v1" in source
    assert "mountFirstVisitIntro" in source
    assert "window.localStorage.getItem" in source
    assert "window.localStorage.setItem" in source
    assert "What's a Sword?" in source
    assert "Pitching Ninja popularized the term." in source
    assert "Bauer helped make the celebration iconic." in source
    assert "SwordFinder ranks the nastiest misses with real clips." in source
    assert "data-sword-intro-dismiss" in source
    assert "if (active !== 'ops')" in source


def test_homepage_keeps_intro_anchor_target():
    html = Path("ui/index.html").read_text()

    assert 'id="what-is-a-sword"' in html
    assert "What is a sword?" in html


def test_intro_has_mobile_friendly_styles():
    css = Path("ui/assets/styles.css").read_text()

    assert ".sword-intro" in css
    assert "align-items: flex-end" in css
    assert ".sword-intro-panel" in css
    assert "width: min(100%, 34rem)" in css
    assert "max-height: calc(100vh - 2rem)" in css
    assert ".sword-intro-close" in css
    assert "width: 48px" in css
    assert "height: 48px" in css
