import importlib.util
from pathlib import Path
import sys
import unittest

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))
source = MAPPING / "reconstruct.py"
spec = importlib.util.spec_from_file_location("reconstruct", source)
reconstruct = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reconstruct
spec.loader.exec_module(reconstruct)


class Reconstruction(unittest.TestCase):
    def test_wall_and_object_boxes(self):
        rows = []
        for index in range(20):
            rows.append({"x_mm": 2000, "y_mm": index * 100 - 1000, "z_mm": 1500, "range_mm": 2000})
        for index in range(10):
            rows.append({"x_mm": 500, "y_mm": 0, "z_mm": 300, "range_mm": 500})
        result = reconstruct.reconstruct_points(rows, cell_m=0.1, eps_m=0.45, min_points=5)
        labels = [box["label"] for box in result["boxes"]]
        self.assertIn("wall", labels)
        self.assertIn("object", labels)

    def test_near_mount_filtered(self):
        rows = [{"x_mm": 100, "y_mm": 0, "z_mm": 0, "range_mm": 100}] * 10
        result = reconstruct.reconstruct_points(rows)
        self.assertEqual(result["point_count"], 0)
        self.assertEqual(result["boxes"], [])


if __name__ == "__main__":
    unittest.main()
