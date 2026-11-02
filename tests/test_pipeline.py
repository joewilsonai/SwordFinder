import sys
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import update  # noqa: E402

BASE = "https://x.blob.core.windows.net/swordfinder-videos"


def pitch(**changes):
    row = {
        "description": "swinging_strike", "strikes": "2", "events": "strikeout", "bat_speed": "30",
        "swing_path_tilt": "30", "swing_length": "5", "game_pk": "1", "at_bat_number": "2", "pitch_number": "3",
        "game_date": "2026-09-20", "batter": "10", "pitcher": "20", "release_speed": "90", "release_extension": "6",
        "plate_x": "0", "plate_z": "1", "sz_top": "3.5", "sz_bot": "1.5",
    }
    row.update(changes)
    return row


class SwordRules(unittest.TestCase):
    def test_no_k_no_sword(self):
        self.assertTrue(update.is_sword(pitch()))
        self.assertFalse(update.is_sword(pitch(events="")))

    def test_needs_two_strikes_a_miss_and_bat_tracking(self):
        self.assertFalse(update.is_sword(pitch(strikes="1")))
        self.assertFalse(update.is_sword(pitch(description="foul")))
        self.assertFalse(update.is_sword(pitch(bat_speed="")))
        self.assertFalse(update.is_sword(pitch(bat_speed="0")))
        self.assertFalse(update.is_sword(pitch(bat_speed="60")))

    def test_score_formula(self):
        self.assertEqual(update.sword_score(30, 30, 5), 50 + 25 + 12.5 + 12.5)
        self.assertEqual(update.sword_score(30, None, None), 75)
        self.assertEqual(update.sword_score(30, 600, 100), 125)

    def test_row_shape(self):
        row = update.to_row(pitch(pitch_type="SL", pitch_name="Slider", zone="14"))
        self.assertEqual(row["id"], "1-2-3")
        self.assertEqual(row["pitch_name"], "Slider")
        self.assertEqual(row["zone"], 14)
        self.assertEqual(row["batter"], 10)
        self.assertEqual(row["strike_zone_distance_inches"], 6.0)
        self.assertEqual(row["perceived_velocity"], 99.9)

    def test_season_rolls_over_on_march_first(self):
        self.assertEqual(update.default_season(date(2027, 2, 28)), 2026)
        self.assertEqual(update.default_season(date(2027, 3, 1)), 2027)


class LegacyClips(unittest.TestCase):
    def row(self, id="a", **changes):
        base = {"id": id, "game_date": "2026-06-21", "pitcher_name": "Chase Silseth", "bat_speed": 24.2, "sword_score": 110.0}
        return {**base, **changes}

    def match(self, blobs, *rows):
        update.match_legacy_clips(list(rows), update.blobs_by_day(blobs), BASE)
        return [r.get("video_azure_blob_url") for r in rows]

    def test_matches_by_day_pitcher_and_speed(self):
        blob = "swords/2026-06-21/sword_2026-06-21_Silseth,_Chase_24.2mph.mp4"
        self.assertEqual(self.match([blob], self.row()), [f"{BASE}/swords/2026-06-21/sword_2026-06-21_Silseth%2C_Chase_24.2mph.mp4"])

    def test_older_score_names_accents_and_suffixes(self):
        accent = "sword_videos/20260621/sword_20260621_Rodón,_Carlos_110.mp4"
        self.assertIn("sword_videos", self.match([accent], self.row(pitcher_name="Carlos Rodón"))[0])
        junior = "sword_videos/20260621/sword_20260621_Leiter_Jr.,_Mark_110.mp4"
        self.assertIsNotNone(self.match([junior], self.row(pitcher_name="Mark Leiter Jr."))[0])

    def test_other_pitcher_or_speed_does_not_match(self):
        blob = "swords/2026-06-21/sword_2026-06-21_Silseth,_Chase_24.2mph.mp4"
        self.assertEqual(self.match([blob], self.row(pitcher_name="Carlos Rodón")), [None])
        self.assertEqual(self.match([blob], self.row(bat_speed=30.0)), [None])

    def test_part_of_a_name_is_not_the_name(self):
        blob = "sword_videos/20260621/sword_20260621_Martinez,_Nick_110.mp4"
        self.assertEqual(self.match([blob], self.row(pitcher_name="Davis Martin")), [None])

    def test_two_swords_never_share_a_clip(self):
        blob = "sword_videos/20260621/sword_20260621_Silseth,_Chase_91.mp4"
        rows = [self.row("a", sword_score=90.2), self.row("b", sword_score=91.3)]
        self.assertEqual(self.match([blob], *rows), [None, None])

    def test_a_sword_fitting_two_clips_gets_neither(self):
        blobs = [f"sword_videos/20260621/sword_20260621_Silseth,_Chase_{n}.mp4" for n in (110, 111)]
        self.assertEqual(self.match(blobs, self.row()), [None])

    def test_an_old_loose_match_is_cleared_but_a_new_copy_stays(self):
        loose = self.row(video_azure_blob_url=f"{BASE}/sword_videos/20260621/x.mp4")
        kept = self.row("b", video_azure_blob_url=f"{BASE}/swords/2026-06-21/some-play-id.mp4")
        self.assertEqual(self.match([], loose, kept), [None, kept["video_azure_blob_url"]])


class MissingClips(unittest.TestCase):
    def run_fill(self, error):
        row = {"id": "a", "play_id": "p", "game_date": "2026-06-21", "sword_score": 100, "video_azure_blob_url": None}

        def fake_url(_):
            raise error

        with mock.patch.object(update, "mlb_clip_url", fake_url), mock.patch.dict(update.os.environ, {}, clear=False):
            failures = update.fill_clips([row], 5, BASE, 1)
        return row, failures

    def test_a_404_means_no_clip_not_an_error(self):
        row, failures = self.run_fill(urllib.error.HTTPError("u", 404, "x", None, None))
        self.assertEqual(failures, 0)
        self.assertTrue(row["clip_unavailable"])

    def test_an_outage_stays_an_error_and_retries(self):
        row, failures = self.run_fill(urllib.error.HTTPError("u", 503, "x", None, None))
        self.assertEqual(failures, 1)
        self.assertNotIn("clip_unavailable", row)


if __name__ == "__main__":
    unittest.main()
