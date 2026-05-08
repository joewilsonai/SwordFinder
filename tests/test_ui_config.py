from pathlib import Path


def test_supabase_config_warning_is_suppressed_when_api_base_url_is_configured():
    source = Path("ui/assets/supabase-rest.js").read_text()

    assert "if (!API_BASE_URL && (!SUPABASE_URL || !SUPABASE_ANON_KEY))" in source
