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
    assert "Watch the lore clips" in source
    assert "/index.html#sword-lore" in source
    assert "if (active !== 'ops')" in source


def test_homepage_keeps_intro_anchor_target():
    html = Path("ui/index.html").read_text()

    assert 'id="what-is-a-sword"' in html
    assert "What is a sword?" in html
    assert 'id="sword-lore"' in html
    assert "Sword Lore" in html
    assert "https://www.youtube.com/watch?v=ixfVMhdIO8s" in html
    assert "https://x.com/PitchingNinja/status/1382299579266240513?s=20" in html
    assert "https://x.com/PitchingNinja/status/1386150807431745537?s=20" in html
    assert "https://www.youtube.com/shorts/SvFqq9fm2ac" in html
    assert "https://www.youtube.com/shorts/9PyeRAIlhYU" in html
    assert "https://www.youtube.com/shorts/HPX17vAjNvA" in html
    assert "https://www.youtube.com/shorts/e_LYlEdGhtk" in html
    assert "https://www.youtube-nocookie.com/embed/ixfVMhdIO8s?rel=0" in html
    assert "https://www.youtube-nocookie.com/embed/SvFqq9fm2ac?rel=0" in html
    assert "https://www.youtube-nocookie.com/embed/9PyeRAIlhYU?rel=0" in html
    assert "https://www.youtube-nocookie.com/embed/HPX17vAjNvA?rel=0" in html
    assert "https://www.youtube-nocookie.com/embed/e_LYlEdGhtk?rel=0" in html
    assert html.count('loading="lazy"') >= 5
    assert html.count("allowfullscreen") >= 5
    assert "Trevor Bauer" in html
    assert "Momentum" in html


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
    assert ".sword-lore" in css
    assert ".lore-grid" in css
    assert ".lore-card" in css
    assert ".lore-video" in css
    assert ".lore-video-short" in css
    assert ".lore-video-wide" in css
    assert "aspect-ratio: 9 / 16" in css
    assert "aspect-ratio: 16 / 9" in css
