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
        result = reconstruct.reconstruct_points(rows, cell_m=0.1, eps_m=0.45, min_points=5,
                                                map_rotation_deg=0.0)
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
        result = reconstruct.reconstruct_points(rows, map_rotation_deg=0.0)
        labels = [box["label"] for box in result["boxes"]]
        self.assertIn("wall_edge", labels)
        self.assertTrue(result["occluded_deg"])

    def test_mount_box_is_hidden(self):
        rows = [{"x_mm": 1000, "y_mm": 0, "z_mm": 1200, "range_mm": 1000}] * 8
        result = reconstruct.reconstruct_points(rows)
        self.assertEqual(result["boxes"], [])
        self.assertEqual(result["mount_boxes"], 1)

    def test_mirror_y_flips_measured_geometry(self):
        rows = [{"x_mm": 1500, "y_mm": 1500, "z_mm": 1500,
                 "range_mm": 2121, "yaw_deg": 45}] * 20
        base = reconstruct.reconstruct_points(
            rows, yaw_scale=1.0, map_rotation_deg=0.0)
        mirrored = reconstruct.reconstruct_points(
            rows, yaw_scale=1.0, map_rotation_deg=0.0,
            mirror_y=True, mirror_center_m=0.0)
        self.assertAlmostEqual(base["boxes"][0]["cy_m"], 1.5, places=2)
        self.assertAlmostEqual(mirrored["boxes"][0]["cy_m"], -1.5, places=2)
        self.assertTrue(mirrored["mirror_y"])
        self.assertAlmostEqual(mirrored["mirror_center_m"], 0.0)

    def test_measured_box_size_override(self):
        rows = []
        for x in (800, 900, 1000, 1100):
            for y in (0, 100, 200):
                rows.append({"x_mm": x, "y_mm": y, "z_mm": 300,
                             "range_mm": (x * x + y * y) ** 0.5})
        base = reconstruct.reconstruct_points(rows, map_rotation_deg=0.0)
        box = base["boxes"][0]
        locked = reconstruct.reconstruct_points(
            rows, map_rotation_deg=0.0,
            annotations={"size_overrides": {
                box["id"]: {"length_m": 2.0, "width_m": 1.2,
                            "z_bottom_m": 0.0, "z_top_m": 0.76}}})
        result = locked["boxes"][0]
        self.assertAlmostEqual(result["length_m"], 2.0, places=3)
        self.assertAlmostEqual(result["width_m"], 1.2, places=3)
        self.assertAlmostEqual(result["z_top_m"], 0.76, places=3)
        self.assertEqual(result["size_source"], "manual")
        self.assertIn(box["id"], locked["annotations"]["size_overrides"])

    def test_sensor_anchor_uses_configured_or_partition_center(self):
        configured = {"room": {"sensor_origin_m": [-0.139, 0.637, 0.77]}}
        self.assertEqual(
            reconstruct._sensor_anchor(configured, True, 0.3555),
            (-0.139, 0.637))
        partition = {"manual_boxes": [
            {"label": "partition", "cx_m": -0.10, "cy_m": 0.50}]}
        self.assertEqual(
            reconstruct._sensor_anchor(partition, True, 0.3555),
            (-0.10, 0.50))
        self.assertEqual(
            reconstruct._sensor_anchor({}, True, 0.3555),
            (0.0, 0.711))

    def test_axis_residual_and_wall_snap(self):
        self.assertAlmostEqual(reconstruct._axis_residual_deg(3.0), 3.0)
        self.assertAlmostEqual(reconstruct._axis_residual_deg(87.0), 3.0)
        self.assertAlmostEqual(reconstruct._axis_residual_deg(90.0), 0.0)
        import math
        angle = math.radians(20.0)
        ca, sa = math.cos(angle), math.sin(angle)
        large = []
        for i in range(21):
            for j in range(11):
                u = -1.0 + i * 0.1
                v = -0.5 + j * 0.1
                large.append((u * ca - v * sa, u * sa + v * ca, 0.6, "tof"))
        snapped = reconstruct._box_from_cluster(
            large, wall_angles=[0.0, math.pi / 2.0],
            snap_wall_objects=True)
        self.assertEqual(snapped["angle_source"], "wall_snap")
        self.assertAlmostEqual(snapped["angle_deg"], 0.0, places=1)
        small = []
        for i in range(6):
            for j in range(5):
                u = -0.25 + i * 0.1
                v = -0.2 + j * 0.1
                small.append((u * ca - v * sa, u * sa + v * ca, 0.6, "tof"))
        untouched = reconstruct._box_from_cluster(
            small, wall_angles=[0.0, math.pi / 2.0],
            snap_wall_objects=True)
        self.assertEqual(untouched["angle_source"], "pca")

    def test_auto_align_returns_three_wall_frame(self):
        import math
        angle = math.radians(4.0)
        ca, sa = math.cos(angle), math.sin(angle)
        rows = []
        for index in range(26):
            x, y = index * 0.1, 0.0
            rows.append({"x_mm": (x * ca - y * sa) * 1000,
                         "y_mm": (x * sa + y * ca) * 1000,
                         "z_mm": 1500, "range_mm": 2000, "yaw_deg": 0})
        for index in range(21):
            x, y = 2.5, index * 0.1
            rows.append({"x_mm": (x * ca - y * sa) * 1000,
                         "y_mm": (x * sa + y * ca) * 1000,
                         "z_mm": 1500, "range_mm": 2000, "yaw_deg": 0})
        for index in range(26):
            x, y = index * 0.1, 2.0
            rows.append({"x_mm": (x * ca - y * sa) * 1000,
                         "y_mm": (x * sa + y * ca) * 1000,
                         "z_mm": 1500, "range_mm": 2000, "yaw_deg": 0})
        result = reconstruct.auto_align_rotation(
            rows, yaw_scale=1.0, mirror_y=False, mirror_center_m=0.0,
            search_min=-5.0, search_max=5.0)
        self.assertEqual(result["wall_count"], 3)
        self.assertLess(result["residual_deg"], 2.0)
        self.assertGreaterEqual(result["rotation_deg"], -5.0)
        self.assertLessEqual(result["rotation_deg"], 5.0)

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

    def test_dense_room_perimeter_keeps_walls_separate(self):
        rows = []
        for index in range(21):
            value = index * 100 - 1000
            rows.append({"x_mm": 2500, "y_mm": value, "z_mm": 1200, "range_mm": 2500})
            rows.append({"x_mm": value + 1500, "y_mm": -1000, "z_mm": 1200, "range_mm": 2500})
            rows.append({"x_mm": value + 1500, "y_mm": 1000, "z_mm": 1200, "range_mm": 2500})
        for index in range(10):
            rows.append({"x_mm": 1000, "y_mm": 0, "z_mm": 400, "range_mm": 1000})
        result = reconstruct.reconstruct_points(
            rows, eps_m=0.30, min_points=5, map_rotation_deg=0.0)
        labels = [box["label"] for box in result["boxes"]]
        self.assertGreaterEqual(labels.count("wall"), 3)
        self.assertIn("object", labels)
        self.assertFalse(any(box["label"] == "object"
                             and box["length_m"] > 2.0 and box["width_m"] > 1.5
                             for box in result["boxes"]))

    def test_annotations_label_hide_merge(self):
        rows = []
        for index in range(20):
            rows.append({"x_mm": 2000, "y_mm": index * 100 - 1000, "z_mm": 1500, "range_mm": 2000})
        for index in range(10):
            rows.append({"x_mm": 1000, "y_mm": 0, "z_mm": 300, "range_mm": 1000})
        base = reconstruct.reconstruct_points(rows, map_rotation_deg=0.0)
        wall = next(box for box in base["boxes"] if box["label"] == "wall")
        obj = next(box for box in base["boxes"] if box["label"] == "object")

        labelled = reconstruct.reconstruct_points(
            rows, map_rotation_deg=0.0,
            annotations={"labels": {wall["id"]: "bed"}})
        self.assertTrue(any(box["label"] == "bed" and box["label_source"] == "manual"
                            for box in labelled["boxes"]))

        hidden = reconstruct.reconstruct_points(
            rows, map_rotation_deg=0.0,
            annotations={"hidden": [obj["id"]]})
        self.assertFalse(any(box["id"] == obj["id"] for box in hidden["boxes"]))

        removed = reconstruct.reconstruct_points(
            rows, map_rotation_deg=0.0,
            annotations={"hidden": [], "removed": [obj["id"]]})
        self.assertFalse(any(box["id"] == obj["id"] for box in removed["boxes"]))
        self.assertIn(obj["id"], removed["annotations"]["removed"])
        self.assertNotIn(obj["id"], removed["annotations"]["hidden"])

        merged = reconstruct.reconstruct_points(
            rows, map_rotation_deg=0.0,
            annotations={"merges": [[wall["id"], obj["id"]]]})
        self.assertEqual(len(merged["boxes"]), 1)
        self.assertTrue(merged["boxes"][0]["id"].startswith("merged:"))
        self.assertEqual(merged["boxes"][0]["points"], wall["points"] + obj["points"])

    def test_room_eps_override(self):
        rows = [{"x_mm": 880, "y_mm": 0, "z_mm": 600, "range_mm": 880}] * 8
        result = reconstruct.reconstruct_points(
            rows, annotations={"room": {"eps_m": 0.22}})
        self.assertAlmostEqual(result["eps_m"], 0.22)

    def test_object_anchors_snap_labelled_box_and_add_prior(self):
        def measured():
            return {"boxes": [{
                "id": "bed-measured", "label": "bed", "label_source": "manual",
                "cx_m": 1.31, "cy_m": 0.05, "angle_deg": 2.0,
                "length_m": 1.90, "width_m": 1.00,
                "z_bottom_m": 0.0, "z_top_m": 0.50, "points": 12,
            }]}
        out = reconstruct.apply_annotations(measured(), {}, add_anchors=True)
        bed = next(box for box in out["boxes"] if box["label"] == "bed")
        self.assertEqual(bed["id"], "bed-measured")
        self.assertAlmostEqual(bed["cx_m"], 1.346, places=3)
        self.assertAlmostEqual(bed["length_m"], 2.0, places=3)
        self.assertTrue(bed["snapped_to_anchor"])
        self.assertEqual(bed["points"], 12)
        fan = next(box for box in out["boxes"] if box["label"] == "fan")
        self.assertEqual(fan["points"], 0)
        self.assertEqual(fan["source"], "prior")
        self.assertFalse(fan["snapped_to_anchor"])
        self.assertEqual(len(out["annotations"]["anchor_matches"]), 2)

        plain = reconstruct.apply_annotations(measured(), {})
        self.assertEqual([box["label"] for box in plain["boxes"]], ["bed"])
        self.assertEqual(plain["annotations"]["anchors"], [])


if __name__ == "__main__":
    unittest.main()
