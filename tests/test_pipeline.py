import sys
import unittest
from datetime import date
from pathlib import Path

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


class ExistingClips(unittest.TestCase):
    def clip(self, blobs, **row):
        base = {"game_date": "2026-06-21", "pitcher_name": "Chase Silseth", "bat_speed": 24.2, "sword_score": 110.0}
        return update.existing_clip({**base, **row}, update.blobs_by_day(blobs), BASE)

    def test_matches_by_day_pitcher_and_speed(self):
        blob = "swords/2026-06-21/sword_2026-06-21_Silseth,_Chase_24.2mph.mp4"
        self.assertEqual(self.clip([blob]), f"{BASE}/swords/2026-06-21/sword_2026-06-21_Silseth%2C_Chase_24.2mph.mp4")

    def test_matches_older_score_names_and_accents(self):
        blob = "sword_videos/20260621/sword_20260621_Rodón,_Carlos_110.mp4"
        self.assertIn("sword_videos", self.clip([blob], pitcher_name="Carlos Rodón"))

    def test_suffixes_are_not_the_last_name(self):
        blob = "sword_videos/20260621/sword_20260621_Leiter_Jr.,_Mark_110.mp4"
        self.assertIsNotNone(self.clip([blob], pitcher_name="Mark Leiter Jr."))

    def test_other_pitcher_or_speed_does_not_match(self):
        blob = "swords/2026-06-21/sword_2026-06-21_Silseth,_Chase_24.2mph.mp4"
        self.assertIsNone(self.clip([blob], pitcher_name="Carlos Rodón"))
        self.assertIsNone(self.clip([blob], bat_speed=30.0))


if __name__ == "__main__":
    unittest.main()
