import os
import subprocess


def test_date_only_statcast_dates_render_without_timezone_shift():
    script = """
global.window = { SWORDFINDER_CONFIG: { apiBaseUrl: 'https://example.test' } };
const mod = await import('./ui/assets/supabase-rest.js');
console.log(mod.formatDate('2026-05-06'));
"""
    env = {**os.environ, "TZ": "America/Chicago"}

    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        cwd=".",
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.stdout.strip() == "May 6, 2026"
