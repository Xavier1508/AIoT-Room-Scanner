import importlib.util
from pathlib import Path
import sys
import unittest

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))
source = MAPPING / "scan.py"
spec = importlib.util.spec_from_file_location("scan", source)
scan = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scan
spec.loader.exec_module(scan)


class ScanTargets(unittest.TestCase):
    def test_full_scan_targets(self):
        self.assertEqual(scan._yaw_targets(5, 45), list(range(-513, 514, 57)))
        self.assertEqual(scan._tilt_targets(25, 500, 950), list(range(500, 951, 25)))

    def test_small_yaw_limit_fine_step(self):
        self.assertEqual(scan._yaw_targets(5, 10), [-114, -57, 0, 57, 114])

    def test_small_yaw_limit_coarse_step(self):
        self.assertEqual(scan._yaw_targets(10, 10), [-114, 0, 114])

    def test_full_coarse_includes_center_and_endpoints(self):
        self.assertEqual(scan._yaw_targets(10, 45),
                         [-513, -456, -342, -228, -114, 0, 114, 228, 342, 456, 513])

    def test_yaw_limits_are_stepper_aligned(self):
        for limit in (5, 10, 15, 20, 30, 45):
            for step in (5, 10):
                if limit < step:
                    continue
                for target in scan._yaw_targets(step, limit):
                    self.assertEqual(target % 57, 0, (step, limit, target))

    def test_bounded_tilt_range(self):
        self.assertEqual(scan._tilt_targets(50, 600, 700), [600, 650, 700])

    def test_yaw_limit_below_step_rejected(self):
        with self.assertRaises(ValueError):
            scan._yaw_targets(10, 5)

    def test_invalid_tilt_range_rejected(self):
        with self.assertRaises(ValueError):
            scan._tilt_targets(25, 950, 500)


if __name__ == "__main__":
    unittest.main()
