import pytest

from update_percentiles_daily import DailyPercentileUpdater


PERCENTILE_ROW = {
    "p1": 1,
    "p5": 5,
    "p10": 10,
    "p25": 25,
    "p50": 50,
    "p75": 75,
    "p90": 90,
    "p95": 95,
    "p99": 99,
    "count": 1000,
    "mean": 50,
    "stddev": 10,
}


class FakeRpcResult:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


SAMPLE_DISTRIBUTION_ROWS = [
    {
        "id": 1,
        "pitch_type": "FF",
        "release_speed": 95.0,
        "release_spin_rate": 2400,
        "pfx_x": 0.2,
        "pfx_z": 1.1,
        "bat_speed": None,
        "sword_score": None,
        "release_extension": 6.5,
        "perceived_velocity": 106.5,
    },
    {
        "id": 2,
        "pitch_type": "SL",
        "release_speed": 84.0,
        "release_spin_rate": 2600,
        "pfx_x": -0.6,
        "pfx_z": 0.2,
        "bat_speed": 32.0,
        "sword_score": 102.0,
        "release_extension": 6.1,
        "perceived_velocity": 93.4,
    },
]


class FakeTableQuery:
    def __init__(self, rows, calls=None):
        self.rows = rows
        self.calls = calls if calls is not None else []

    def select(self, fields):
        return self

    def order(self, field):
        return self

    def gt(self, field, value):
        self.calls.append(("gt", field, value))
        self.rows = [row for row in self.rows if row[field] > value]
        return self

    def gte(self, field, value):
        self.calls.append(("gte", field, value))
        return self

    def lt(self, field, value):
        self.calls.append(("lt", field, value))
        return self

    def range(self, start, end):
        self.rows = self.rows[start : end + 1]
        return self

    def execute(self):
        return FakeRpcResult(self.rows)


class MissingRpcSupabase:
    def __init__(self):
        self.calls = []
        self.table_calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload["query"]))
        if name == "execute_sql_query":
            raise RuntimeError(
                "Could not find the function public.execute_sql_query(query). "
                "Perhaps you meant to call the function public.execute_sql."
            )
        return FakeRpcResult([PERCENTILE_ROW])

    def table(self, name):
        assert name == "mlb_pitches_enhanced"
        return FakeTableQuery(list(SAMPLE_DISTRIBUTION_ROWS), self.table_calls)


class CaptureSupabase:
    def __init__(self):
        self.calls = []

    def rpc(self, name, payload):
        query = payload["query"]
        self.calls.append((name, query))
        if "GROUP BY pitch_type" in query:
            return FakeRpcResult([{**PERCENTILE_ROW, "pitch_type": "FF"}])
        return FakeRpcResult([PERCENTILE_ROW])


def test_distribution_cache_falls_back_to_table_scan_when_query_rpc_is_missing():
    supabase = MissingRpcSupabase()
    updater = DailyPercentileUpdater(supabase)

    updater.build_distribution_cache()

    called_names = [name for name, _ in supabase.calls]
    assert "execute_sql_query" in called_names
    assert "execute_sql" not in called_names
    assert updater.distribution_stats["movement_overall"]["count"] == 2
    assert updater.distribution_stats["velo_overall"]["count"] == 2
    assert updater.distribution_stats["bat_speed_sword"]["count"] == 1


def test_table_scan_distribution_cache_can_be_limited_to_one_season():
    supabase = MissingRpcSupabase()
    updater = DailyPercentileUpdater(supabase)

    updater.build_distribution_cache(year=2026)

    assert ("gte", "game_date", "2026-01-01") in supabase.table_calls
    assert ("lt", "game_date", "2027-01-01") in supabase.table_calls


def test_distribution_cache_executes_pitch_type_queries_for_each_metric():
    supabase = CaptureSupabase()
    updater = DailyPercentileUpdater(supabase)

    updater.build_distribution_cache()

    queries = [query for _, query in supabase.calls]
    for field in [
        "release_speed",
        "release_spin_rate",
        "release_extension",
        "perceived_velocity",
    ]:
        assert any(
            f"ORDER BY {field}" in query and "GROUP BY pitch_type" in query
            for query in queries
        ), f"missing pitch-type distribution query for {field}"


def test_distribution_cache_raises_unexpected_rpc_errors():
    class BrokenSupabase:
        def rpc(self, name, payload):
            raise RuntimeError("permission denied")

    updater = DailyPercentileUpdater(BrokenSupabase())

    with pytest.raises(RuntimeError, match="permission denied"):
        updater.build_distribution_cache()


def test_sword_distribution_falls_back_to_table_scan_when_query_rpc_is_missing():
    supabase = MissingRpcSupabase()
    updater = DailyPercentileUpdater(supabase)

    updater.build_sword_distribution()

    assert updater.distribution_stats["bat_speed_sword"]["count"] == 1
