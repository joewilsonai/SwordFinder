from pathlib import Path


def test_ops_status_page_is_wired_to_static_ui():
    html = Path("ui/ops.html").read_text()
    layout = Path("ui/assets/layout.js").read_text()

    assert '<script type="module" src="/assets/ops.js"></script>' in html
    assert 'mountNav(\'ops\')' in Path("ui/assets/ops.js").read_text()
    assert 'href="/ops.html">Ops</a>' in layout


def test_ops_ui_uses_backlog_endpoints_through_api_base():
    helpers = Path("ui/assets/supabase-rest.js").read_text()
    ops = Path("ui/assets/ops.js").read_text()

    assert "export async function fetchOpsJson" in helpers
    assert "/ops/video-backlog/status" in ops
    assert "/ops/video-backlog" in ops
