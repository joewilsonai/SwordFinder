from get_play_ids_on_demand import get_play_id_for_pitch


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_get_play_id_for_pitch_normalizes_db_bottom_half(monkeypatch):
    payload = {
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {"inning": 6, "halfInning": "bottom"},
                        "matchup": {
                            "pitcher": {"id": 657424},
                            "batter": {"id": 676356},
                        },
                        "playEvents": [
                            {"playId": "earlier-pitch"},
                            {"playId": "final-pitch"},
                        ],
                    }
                ]
            }
        }
    }

    def fake_get(url, timeout):
        return FakeResponse(payload)

    monkeypatch.setattr("get_play_ids_on_demand.requests.get", fake_get)

    play_id = get_play_id_for_pitch(
        game_pk=822987,
        pitcher_id=657424,
        batter_id=676356,
        inning=6,
        inning_topbot="Bot",
    )

    assert play_id == "final-pitch"
