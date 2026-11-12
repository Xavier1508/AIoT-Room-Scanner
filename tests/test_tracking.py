import sys
import unittest
from pathlib import Path

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))

from tracking import (BackgroundMap, TrackSmoother, estimate_track)  # noqa: E402


def make_background():
    boxes = [{
        "label": "wall", "cx_m": 2.0, "cy_m": 0.0, "angle_deg": 90.0,
        "length_m": 4.0, "width_m": 0.10, "z_bottom_m": 0.0, "z_top_m": 2.5,
    }]
    polygon = [(-1.0, -1.0), (3.0, -1.0), (3.0, 1.0), (-1.0, 1.0)]
    return BackgroundMap("test", boxes, polygon, (0.0, 0.0), 0.77,
                         0.0, False, {})


class TrackingTests(unittest.TestCase):
    def test_raycast_hits_front_wall(self):
        background = make_background()
        self.assertAlmostEqual(background.raycast_cm(0.0, 800), 195.0, places=1)
        self.assertTrue(background.inside_room(1.0, 0.0))
        self.assertFalse(background.inside_room(5.0, 0.0))

    def test_confirmed_track_requires_tof_and_hlk_consistency(self):
        background = make_background()
        samples = [
            {"yaw_deg": 0.0, "tilt_us": 800, "range_cm": 100.0,
             "background_cm": 195.0, "hlk_cm": 105.0, "hlk_energy": 90},
            {"yaw_deg": 5.0, "tilt_us": 800, "range_cm": 102.0,
             "background_cm": 195.0, "hlk_cm": 110.0, "hlk_energy": 90},
        ]
        estimate = estimate_track(samples, background)
        self.assertEqual(estimate["state"], "confirmed")
        self.assertTrue(estimate["confirmed"])
        self.assertAlmostEqual(estimate["x_m"], 1.0, places=1)
        self.assertAlmostEqual(estimate["y_m"], 0.0, places=1)

    def test_hlk_mismatch_is_not_confirmed(self):
        background = make_background()
        samples = [
            {"yaw_deg": 0.0, "tilt_us": 800, "range_cm": 100.0,
             "background_cm": 195.0, "hlk_cm": 300.0, "hlk_energy": 90},
            {"yaw_deg": 5.0, "tilt_us": 800, "range_cm": 102.0,
             "background_cm": 195.0, "hlk_cm": 300.0, "hlk_energy": 90},
        ]
        estimate = estimate_track(samples, background)
        self.assertNotEqual(estimate["state"], "confirmed")
        self.assertFalse(estimate["confirmed"])

    def test_behind_wall_is_rejected(self):
        background = make_background()
        samples = [
            {"yaw_deg": 0.0, "tilt_us": 800, "range_cm": 300.0,
             "background_cm": 195.0, "hlk_cm": 300.0, "hlk_energy": 100},
            {"yaw_deg": 5.0, "tilt_us": 800, "range_cm": 305.0,
             "background_cm": 195.0, "hlk_cm": 300.0, "hlk_energy": 100},
        ]
        estimate = estimate_track(samples, background)
        self.assertNotEqual(estimate["state"], "confirmed")
        self.assertFalse(estimate["confirmed"])

    def test_smoother_marks_stale(self):
        smoother = TrackSmoother(stale_s=3.0)
        track = smoother.update({"state": "confirmed", "confirmed": True,
                                 "x_m": 1.0, "y_m": 0.5,
                                 "distance_cm": 100.0, "confidence": 0.9}, 10.0)
        self.assertEqual(track["state"], "confirmed")
        stale = smoother.update({"state": "radar", "confirmed": False}, 15.0)
        self.assertEqual(stale["state"], "stale")
        self.assertFalse(stale["confirmed"])


if __name__ == "__main__":
    unittest.main()
