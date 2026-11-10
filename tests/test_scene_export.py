import importlib.util
from pathlib import Path
import sys
import unittest

MAPPING = Path(__file__).resolve().parents[1] / "tools" / "mapping"
sys.path.insert(0, str(MAPPING))
source = MAPPING / "scene_export.py"
spec = importlib.util.spec_from_file_location("scene_export", source)
scene_export = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scene_export
spec.loader.exec_module(scene_export)


class SceneExport(unittest.TestCase):
    def test_ply_counts_and_faces(self):
        points = [
            {"x": 0.0, "y": 0.0, "z": 1.0, "r": 80, "g": 220, "b": 255},
            {"x": 1.0, "y": 0.5, "z": 1.2, "r": 255, "g": 170, "b": 60},
        ]
        boxes = [{
            "label": "partition", "cx_m": -0.1, "cy_m": 0.5,
            "angle_deg": 0.0, "length_m": 0.2, "width_m": 0.6,
            "z_bottom_m": 0.0, "z_top_m": 2.4, "source": "prior",
        }]
        text = scene_export.build_ply(points, boxes, scan_id="scan-test",
                                      yaw_scale=1.0, map_rotation_deg=0.0)
        self.assertIn("format ascii 1.0", text)
        self.assertIn("element vertex 10", text)
        self.assertIn("element face 12", text)
        self.assertIn("comment points=2 boxes=1", text)
        body = text.split("end_header\n", 1)[1].strip().splitlines()
        self.assertEqual(len(body), 10 + 12)
        verts = [line for line in body[:10]]
        self.assertIn("0.0000 0.0000 1.0000 80 220 255", verts)
        faces = [line for line in body[10:]]
        for face in faces:
            parts = face.split()
            self.assertEqual(parts[0], "3")
            for index in parts[1:]:
                self.assertGreaterEqual(int(index), 2)
                self.assertLess(int(index), 10)

    def test_box_vertices_are_centred(self):
        box = {
            "cx_m": 1.0, "cy_m": 2.0, "angle_deg": 0.0,
            "length_m": 1.0, "width_m": 0.4,
            "z_bottom_m": 0.0, "z_top_m": 1.0,
        }
        vertices = scene_export._box_vertices(box)
        self.assertEqual(len(vertices), 8)
        xs = [vertex[0] for vertex in vertices]
        ys = [vertex[1] for vertex in vertices]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 1.0)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, 2.0)


if __name__ == "__main__":
    unittest.main()
