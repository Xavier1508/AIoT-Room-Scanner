import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))
source = MAPPING / "dataset_export.py"
spec = importlib.util.spec_from_file_location("dataset_export", source)
dataset_export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dataset_export
spec.loader.exec_module(dataset_export)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class DatasetExportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scans = self.root / "scans"
        self.scan = self.scans / "test-scan"
        self.scan.mkdir(parents=True)
        write_json(self.scan / "metadata.json", {
            "scan_id": "test-scan",
            "started_utc": "2026-11-10T00:00:00Z",
            "finished_utc": "2026-11-10T00:01:00Z",
            "points": 3,
            "valid_points": 2,
            "tof_points": 1,
            "hc_points": 1,
            "tilt_targets": [500, 525, 550],
            "calibration": {"sensor_height_mm": 770},
        })
        write_json(self.scan / "annotations.json", {
            "labels": {},
            "hidden": [],
            "merges": [],
            "point_labels": {"fan": [0]},
            "label_catalog": {},
            "manual_boxes": [{
                "id": "prior:wardrobe",
                "label": "wardrobe",
                "cx_m": 0.3,
                "cy_m": -0.5,
                "angle_deg": 0.0,
                "length_m": 0.7,
                "width_m": 0.6,
                "z_bottom_m": 0.0,
                "z_top_m": 2.0,
                "source": "prior",
            }],
            "room_outline": [[-0.3, -1.0], [2.4, -1.0], [2.4, 1.5], [-0.3, 1.5]],
            "room": {"width_m": 2.7, "depth_m": 2.5, "yaw_scale": 1.0,
                     "map_rotation_deg": 0.0},
        })
        rows = [
            {"point_index": 0, "yaw_half_steps": -684, "yaw_deg": -60.0,
             "servo_us": 500, "tilt_deg": 22.5, "hc_raw_mm": 2000,
             "hc_cal_mm": 2000, "hc_valid_rate": 1.0, "tof_raw_mm": 1900,
             "tof_cal_mm": 1900, "tof_valid_rate": 1.0,
             "tof_status": "range_valid", "hlk_cm": 120, "hlk_energy": 80,
             "hlk_valid": True, "range_mm": 1900, "range_source": "tof",
             "x_mm": 950, "y_mm": -1645, "z_mm": 1500},
            {"point_index": 1, "yaw_half_steps": -684, "yaw_deg": -60.0,
             "servo_us": 525, "tilt_deg": 20.0, "hc_raw_mm": 2000,
             "hc_cal_mm": 2000, "hc_valid_rate": 1.0, "tof_raw_mm": 1900,
             "tof_cal_mm": 1900, "tof_valid_rate": 1.0,
             "tof_status": "range_valid", "hlk_cm": 120, "hlk_energy": 80,
             "hlk_valid": True, "range_mm": 1900, "range_source": "tof",
             "x_mm": 950, "y_mm": -1645, "z_mm": 1000},
            {"point_index": 2, "yaw_half_steps": -684, "yaw_deg": -60.0,
             "servo_us": 550, "tilt_deg": 17.5, "hc_raw_mm": 2000,
             "hc_cal_mm": 2000, "hc_valid_rate": 1.0, "tof_raw_mm": "",
             "tof_cal_mm": "", "tof_valid_rate": 0.0,
             "tof_status": "wrap_target_fail", "hlk_cm": 120, "hlk_energy": 80,
             "hlk_valid": True, "range_mm": "", "range_source": "hc",
             "x_mm": 1000, "y_mm": -1732, "z_mm": 600},
        ]
        with (self.scan / "points.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        with (self.scan / "samples.jsonl").open("w", encoding="utf-8") as handle:
            for index in range(3):
                handle.write(json.dumps({
                    "scan_id": "test-scan",
                    "yaw_index": 0,
                    "tilt_index": index,
                    "sample_index": 0,
                    "status": {
                        "uptime_ms": 1000 + index * 100,
                        "sensors": {"hlk": {"distance_cm": 120, "energy": 80}},
                    },
                }) + "\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_export_clean_run(self):
        result = dataset_export.export_run(
            "test-scan", clean=True, run_label="unit test", notes="clean",
            output_root=self.root / "dataset", scans_root=self.scans)
        folder = Path(result["folder"])
        self.assertIn("clean", str(folder))
        self.assertEqual(result["counts"]["points_total"], 3)
        self.assertEqual(result["counts"]["points_valid"], 2)
        self.assertTrue(Path(result["files"]["points_csv"]).is_file())
        with Path(result["files"]["points_csv"]).open(encoding="utf-8") as handle:
            points = list(csv.DictReader(handle))
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0]["clean"], "true")
        self.assertEqual(points[0]["point_label"], "fan")
        self.assertEqual(points[2]["range_source"], "hc")
        with Path(result["files"]["objects_csv"]).open(encoding="utf-8") as handle:
            objects = list(csv.DictReader(handle))
        self.assertTrue(any(row["is_prior"] == "true" for row in objects))
        self.assertTrue((self.root / "dataset" / "index.csv").is_file())

    def test_export_dirty_run(self):
        result = dataset_export.export_run(
            "test-scan", clean=False, run_label="unit dirty",
            output_root=self.root / "dataset", scans_root=self.scans)
        self.assertIn("dirty", result["folder"])
        manifest = json.loads(Path(result["files"]["manifest_json"]).read_text(encoding="utf-8"))
        self.assertFalse(manifest["clean"])
        self.assertEqual(manifest["points_total"], 3)
        self.assertIn("points_csv", manifest["sha256"])


if __name__ == "__main__":
    unittest.main()
