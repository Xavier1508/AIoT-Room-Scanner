import importlib.util
from pathlib import Path
import sys
import unittest

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))
source = MAPPING / "presence.py"
spec = importlib.util.spec_from_file_location("presence", source)
presence = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = presence
spec.loader.exec_module(presence)


def positive(distance_cm=120, energy=80, target_state=1):
    return {
        "valid": True,
        "stale": False,
        "distance_cm": distance_cm,
        "energy": energy,
        "target_state": target_state,
    }


class PresenceTrackerTest(unittest.TestCase):
    def test_confirmation_and_hold(self):
        tracker = presence.PresenceTracker(confirm_frames=3, hold_s=6.0)
        first = tracker.update(positive(), now=0.0)
        self.assertEqual(first["state"], "confirming")
        self.assertEqual(first["class"], "unknown")
        tracker.update(positive(), now=1.0)
        third = tracker.update(positive(), now=2.0)
        self.assertEqual(third["state"], "present")
        self.assertEqual(third["class"], "human")
        self.assertGreater(third["confidence"], 0.5)

        held = tracker.update({"valid": False}, now=3.0)
        self.assertEqual(held["state"], "holding")
        expired = tracker.update({"valid": False}, now=10.0)
        self.assertEqual(expired["state"], "empty")
        self.assertEqual(expired["class"], "empty")

    def test_scan_mode_suppresses(self):
        tracker = presence.PresenceTracker(confirm_frames=3)
        result = tracker.update(positive(), now=0.0, scanning=True)
        self.assertEqual(result["state"], "scanning")
        self.assertEqual(result["class"], "unknown")
        self.assertEqual(result["confidence"], 0.0)

    def test_energy_threshold_and_range(self):
        tracker = presence.PresenceTracker(confirm_frames=1, energy_threshold=40)
        low = tracker.update(positive(energy=10), now=0.0)
        self.assertEqual(low["state"], "empty")
        far = tracker.update(positive(distance_cm=700), now=1.0)
        self.assertEqual(far["state"], "empty")
        near = tracker.update(positive(distance_cm=10), now=2.0)
        self.assertEqual(near["state"], "empty")
        valid = tracker.update(positive(), now=3.0)
        self.assertEqual(valid["state"], "present")

    def test_history_is_bounded(self):
        tracker = presence.PresenceTracker(confirm_frames=1, history_limit=10)
        for index in range(25):
            tracker.update(positive(), now=float(index))
        snapshot = tracker.snapshot()
        self.assertEqual(len(snapshot["history"]), 10)
        self.assertEqual(snapshot["history"][-1]["state"], "present")

    def test_beyond_wall_clears_immediately(self):
        tracker = presence.PresenceTracker(confirm_frames=1, hold_s=6.0)
        present = tracker.update(positive(distance_cm=120), now=0.0)
        self.assertEqual(present["state"], "present")
        gated = tracker.update(positive(distance_cm=356), now=1.0,
                               max_range_cm=240)
        self.assertEqual(gated["state"], "empty")
        self.assertEqual(gated["gate"], "beyond_wall")
        self.assertEqual(gated["class"], "empty")

    def test_no_target_hold_is_short(self):
        tracker = presence.PresenceTracker(
            confirm_frames=1, hold_s=6.0, no_target_hold_s=2.5)
        tracker.update(positive(), now=0.0)
        holding = tracker.update(positive(target_state=0, energy=100), now=1.0)
        self.assertEqual(holding["state"], "holding")
        expired = tracker.update(positive(target_state=0, energy=100), now=4.0)
        self.assertEqual(expired["state"], "empty")
        self.assertEqual(expired["gate"], "no_target")

    def test_distance_unstable_does_not_confirm(self):
        tracker = presence.PresenceTracker(
            confirm_frames=1, distance_spread_cm=20.0)
        tracker.update(positive(distance_cm=120), now=0.0)
        tracker.update(positive(distance_cm=130), now=1.0)
        unstable = tracker.update(positive(distance_cm=180), now=2.0)
        self.assertNotEqual(unstable["state"], "present")
        self.assertEqual(unstable["gate"], "distance_unstable")

    def test_reset(self):
        tracker = presence.PresenceTracker(confirm_frames=1)
        tracker.update(positive(), now=0.0)
        tracker.reset()
        snapshot = tracker.snapshot()
        self.assertEqual(snapshot["state"], "empty")
        self.assertEqual(snapshot["class"], "empty")


if __name__ == "__main__":
    unittest.main()
