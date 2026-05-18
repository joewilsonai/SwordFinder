from pathlib import Path


def test_sword_detail_page_has_share_card_controls():
    html = Path("ui/sword/profile.html").read_text()
    alias_html = Path("ui/sword/[id].html").read_text()
    source = Path("ui/assets/sword-detail.js").read_text()

    for page in (html, alias_html):
        assert 'id="sword-share-card"' in page
        assert 'id="copy-sword-link"' in page
        assert 'id="open-sword-x"' in page
        assert 'id="share-sword-native"' in page
        assert 'id="sword-share-status"' in page
        assert "Share This Sword" in page

    assert "buildSwordShareText" in source
    assert "buildSwordShareUrl" in source
    assert "copySwordLink" in source
    assert "shareSwordNative" in source
    assert "x.com/intent/post" in source
    assert "navigator.clipboard.writeText" in source
    assert "navigator.share" in source
