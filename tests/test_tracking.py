import sys
import unittest
from pathlib import Path

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))

from tracking import (BackgroundMap, ScanRangeMap, TrackSmoother,  # noqa: E402
                      _provisional_candidate, estimate_track)


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

    def test_scan_range_overrides_approximate_boxes(self):
        background = make_background()
        rows = [
            {"yaw_deg": "0.0", "servo_us": "800", "range_mm": "2350",
             "range_source": "tof"},
            {"yaw_deg": "45.0", "servo_us": "800", "range_mm": "1200",
             "range_source": "tof"},
        ]
        scan_range = ScanRangeMap("test", rows)
        measured = BackgroundMap("test", background.boxes, background.polygon,
                                 background.origin, background.sensor_z,
                                 0.0, False, {}, scan_range=scan_range)
        self.assertAlmostEqual(measured.background_cm(0.0, 800), 235.0, places=1)
        self.assertAlmostEqual(measured.background_cm(2.0, 800), 235.0, places=1)
        self.assertAlmostEqual(measured.background_cm(45.0, 800), 120.0, places=1)
        self.assertAlmostEqual(measured.raycast_cm(0.0, 800), 195.0, places=1)

    def test_clusters_do_not_average_separate_targets(self):
        background = make_background()
        samples = [
            {"yaw_deg": 0.0, "tilt_us": 800, "range_cm": 100.0,
             "background_cm": 238.0, "hlk_cm": 105.0, "hlk_energy": 90,
             "source": "tof"},
            {"yaw_deg": 30.0, "tilt_us": 800, "range_cm": 100.0,
             "background_cm": 238.0, "hlk_cm": 105.0, "hlk_energy": 90,
             "source": "tof"},
            {"yaw_deg": 35.0, "tilt_us": 800, "range_cm": 102.0,
             "background_cm": 238.0, "hlk_cm": 108.0, "hlk_energy": 90,
             "source": "tof"},
        ]
        estimate = estimate_track(samples, background)
        self.assertTrue(estimate["confirmed"])
        self.assertEqual(estimate["candidates"], 2)
        self.assertGreaterEqual(estimate["scan_yaw_deg"], 30.0)
        self.assertLessEqual(estimate["scan_yaw_deg"], 35.0)
        self.assertGreater(estimate["bearing_deg"], 20.0)

    def test_hc_only_cluster_is_not_confirmed(self):
        background = make_background()
        samples = [
            {"yaw_deg": 20.0, "tilt_us": 800, "range_cm": 100.0,
             "background_cm": 238.0, "hlk_cm": 105.0, "hlk_energy": 90,
             "source": "hc"},
            {"yaw_deg": 25.0, "tilt_us": 800, "range_cm": 102.0,
             "background_cm": 238.0, "hlk_cm": 108.0, "hlk_energy": 90,
             "source": "hc"},
        ]
        estimate = estimate_track(samples, background)
        self.assertFalse(estimate["confirmed"])
        self.assertEqual(estimate["reason"], "hc_only")

    def test_stale_track_expires(self):
        smoother = TrackSmoother(stale_s=3.0, expire_s=10.0)
        smoother.update({"state": "confirmed", "confirmed": True,
                         "x_m": 1.0, "y_m": 0.5,
                         "distance_cm": 100.0, "confidence": 0.9}, 10.0)
        stale = smoother.update({"state": "radar", "confirmed": False}, 15.0)
        self.assertEqual(stale["state"], "stale")
        self.assertAlmostEqual(stale["x_m"], 1.0, places=3)
        expired = smoother.update({"state": "radar", "confirmed": False}, 25.0)
        self.assertEqual(expired["state"], "radar")

    def test_single_tof_sample_can_be_verified(self):
        self.assertTrue(_provisional_candidate({
            "state": "radar", "reason": "single_sample",
            "candidates": 1, "tof_count": 1, "scan_yaw_deg": 20.0,
        }))
        self.assertFalse(_provisional_candidate({
            "state": "radar", "reason": "hc_only",
            "candidates": 2, "tof_count": 0, "scan_yaw_deg": 20.0,
        }))
        self.assertFalse(_provisional_candidate({
            "state": "radar", "reason": "outside_room",
            "candidates": 1, "tof_count": 1, "scan_yaw_deg": 60.0,
        }))


if __name__ == "__main__":
    unittest.main()
