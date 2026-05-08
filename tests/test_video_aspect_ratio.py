from pathlib import Path


def test_video_shell_preserves_baseball_clip_aspect_ratio():
    css = Path("ui/assets/styles.css").read_text()

    assert "aspect-ratio: 16 / 9" in css
    assert ".video-shell video" in css
    assert "height: 100%" in css
    assert "height: 230px" not in css


def test_homepage_pending_video_placeholder_uses_video_shell_ratio():
    source = Path("ui/assets/index.js").read_text()

    assert "video-placeholder" in source
    assert "h-[230px]" not in source
