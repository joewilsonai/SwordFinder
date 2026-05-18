from pathlib import Path


def test_shared_layout_mounts_first_visit_intro():
    source = Path("ui/assets/layout.js").read_text()

    assert "swordfinder:intro:v3" in source
    assert "mountFirstVisitIntro" in source
    assert "window.localStorage.getItem" in source
    assert "window.localStorage.setItem" in source
    assert "get('intro') === '1'" in source
    assert "options.force" in source
    assert "What's a Sword?" in source
    assert "Spot the shape" in source
    assert "Read the score" in source
    assert "Finish the at-bat" in source
    assert "data-sword-intro-dismiss" in source
    assert "Open Sword Info" in source
    assert 'href="/sword-info.html"' in source
    assert "Skip to leaderboards" in source
    assert "active === 'info'" in source
    assert "nav-label-short" in source
    assert "if (active !== 'ops')" in source


def test_homepage_links_to_sword_info_without_embedding_lore():
    html = Path("ui/index.html").read_text()

    assert 'id="what-is-a-sword"' in html
    assert "What is a sword?" in html
    assert "/sword-info.html" in html
    assert 'id="sword-lore"' not in html
    assert "youtube-nocookie.com/embed" not in html


def test_sword_info_page_contains_lore_embeds():
    html = Path("ui/sword-info.html").read_text()
    source = Path("ui/assets/sword-info.js").read_text()

    assert "Sword Info" in html
    assert "Sword Lore" in html
    assert 'id="replay-intro"' in html
    assert "Replay Walkthrough" in html
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
    assert "Creator Angle" in html
    assert "Built for the shoutout" in html
    assert 'id="copy-creator-pitch"' in html
    assert "copyCreatorPitch" in source
    assert "mountNav('info')" in source
    assert "mountFirstVisitIntro({ force: true })" in source
    assert "window.localStorage.removeItem('swordfinder:intro:v3')" in source
    assert "setFooter()" in source


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
    assert ".info-hero" in css
    assert ".info-steps" in css
    assert ".info-cta" in css
    assert ".nav-label-short" in css
