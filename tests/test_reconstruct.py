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
            rows.append({"x_mm": 1000, "y_mm": 0, "z_mm": 300, "range_mm": 1000})
        result = reconstruct.reconstruct_points(rows, cell_m=0.1, eps_m=0.45, min_points=5)
        labels = [box["label"] for box in result["boxes"]]
        self.assertIn("wall", labels)
        self.assertIn("object", labels)
        for box in result["boxes"]:
            self.assertIn("distance_m", box)
            self.assertIn("nearest_m", box)

    def test_near_mount_filtered(self):
        rows = [{"x_mm": 100, "y_mm": 0, "z_mm": 0, "range_mm": 100}] * 10
        result = reconstruct.reconstruct_points(rows)
        self.assertEqual(result["point_count"], 0)
        self.assertEqual(result["boxes"], [])

    def test_low_table_guard(self):
        low = [{"x_mm": 500, "y_mm": 0, "z_mm": 300, "range_mm": 500}] * 8
        self.assertEqual(reconstruct.reconstruct_points(low)["point_count"], 0)
        high = [{"x_mm": 880, "y_mm": 0, "z_mm": 600, "range_mm": 880}] * 8
        result = reconstruct.reconstruct_points(high)
        self.assertEqual(result["point_count"], 8)
        self.assertEqual(len(result["boxes"]), 1)

    def test_wall_edge_and_occluded(self):
        rows = [{"x_mm": 2000, "y_mm": index * 100, "z_mm": 1800, "range_mm": 2000}
                for index in range(10)]
        result = reconstruct.reconstruct_points(rows)
        labels = [box["label"] for box in result["boxes"]]
        self.assertIn("wall_edge", labels)
        self.assertTrue(result["occluded_deg"])

    def test_mount_box_is_hidden(self):
        rows = [{"x_mm": 1000, "y_mm": 0, "z_mm": 1200, "range_mm": 1000}] * 8
        result = reconstruct.reconstruct_points(rows)
        self.assertEqual(result["boxes"], [])
        self.assertEqual(result["mount_boxes"], 1)

    def test_yaw_scale_metadata(self):
        rows = [{"x_mm": 1000, "y_mm": 0, "z_mm": 1500, "range_mm": 1000,
                 "yaw_deg": 0}] * 8
        result = reconstruct.reconstruct_points(rows, yaw_scale=0.5, fov_limit_deg=60)
        self.assertAlmostEqual(result["yaw_scale"], 0.5)
        self.assertAlmostEqual(result["fov_limit_deg"], 30.0)

    def test_map_rotation_metadata(self):
        rows = [{"x_mm": 1500, "y_mm": 0, "z_mm": 1500, "range_mm": 1500,
                 "yaw_deg": 0}] * 8
        result = reconstruct.reconstruct_points(
            rows, yaw_scale=1.0, map_rotation_deg=10.0)
        self.assertAlmostEqual(result["map_rotation_deg"], 10.0)
        box = result["boxes"][0]
        self.assertAlmostEqual(box["cx_m"], 1.477, places=2)
        self.assertAlmostEqual(box["cy_m"], 0.260, places=2)

    def test_annotations_label_hide_merge(self):
        rows = []
        for index in range(20):
            rows.append({"x_mm": 2000, "y_mm": index * 100 - 1000, "z_mm": 1500, "range_mm": 2000})
        for index in range(10):
            rows.append({"x_mm": 1000, "y_mm": 0, "z_mm": 300, "range_mm": 1000})
        base = reconstruct.reconstruct_points(rows)
        wall = next(box for box in base["boxes"] if box["label"] == "wall")
        obj = next(box for box in base["boxes"] if box["label"] == "object")

        labelled = reconstruct.reconstruct_points(
            rows, annotations={"labels": {wall["id"]: "bed"}})
        self.assertTrue(any(box["label"] == "bed" and box["label_source"] == "manual"
                            for box in labelled["boxes"]))

        hidden = reconstruct.reconstruct_points(
            rows, annotations={"hidden": [obj["id"]]})
        self.assertFalse(any(box["id"] == obj["id"] for box in hidden["boxes"]))

        merged = reconstruct.reconstruct_points(
            rows, annotations={"merges": [[wall["id"], obj["id"]]]})
        self.assertEqual(len(merged["boxes"]), 1)
        self.assertTrue(merged["boxes"][0]["id"].startswith("merged:"))
        self.assertEqual(merged["boxes"][0]["points"], wall["points"] + obj["points"])


if __name__ == "__main__":
    unittest.main()
