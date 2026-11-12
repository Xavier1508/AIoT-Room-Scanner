"""Export a scan plus its measured and prior boxes as an ASCII PLY scene.

The PLY is a plain, dependency-free deliverable that can be opened in MeshLab,
Blender, CloudCompare or any other point-cloud viewer. Scan points keep their
sensor colour (cyan ToF, orange HC); every box becomes 8 vertices and 12
triangles coloured by label. A JSON sidecar records the exact boxes, yaw
calibration and file hash so the scene can be audited later.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

MAPPING = Path(__file__).resolve().parent
if str(MAPPING) not in sys.path:
    sys.path.insert(0, str(MAPPING))

from common import RESEARCH, SCANS, read_json, utc_iso, utc_stamp  # noqa: E402
from reconstruct import reconstruct_points  # noqa: E402

SCENES = RESEARCH / "scenes"

LABEL_COLORS = {
    "wall": (80, 150, 230),
    "wall_edge": (130, 200, 255),
    "door-wc": (255, 107, 107),
    "door-exit": (255, 209, 102),
    "wardrobe": (205, 130, 255),
    "partition": (154, 214, 160),
    "desk": (255, 150, 90),
    "chair": (255, 150, 120),
    "bed": (170, 140, 255),
    "table": (255, 170, 90),
    "object": (70, 210, 150),
}
TOF_COLOR = (80, 220, 255)
HC_COLOR = (255, 170, 60)


def _as_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _box_color(box):
    return LABEL_COLORS.get(str(box.get("label")), (70, 210, 150))


def _mirror_from_annotations(annotations):
    room = annotations.get("room") or {}
    try:
        mirror_y = bool(float(room.get("mirror_y", 1.0)))
    except (TypeError, ValueError):
        mirror_y = True
    try:
        center = float(room.get("mirror_center_m"))
    except (TypeError, ValueError):
        ys = [float(point[1]) for point in (annotations.get("room_outline") or [])
              if isinstance(point, (list, tuple)) and len(point) >= 2]
        center = (min(ys) + max(ys)) / 2.0 if ys else 0.0
    return mirror_y, center


def _map_point(row, yaw_scale, rotation_ca, rotation_sa,
               mirror_y=False, mirror_center_m=0.0):
    """Apply the same yaw/rotation mapping used by reconstruct_points."""
    x = _as_float(row.get("x_mm"))
    y = _as_float(row.get("y_mm"))
    z = _as_float(row.get("z_mm"))
    if x is None or y is None or z is None:
        return None
    x, y, z = x / 1000.0, y / 1000.0, z / 1000.0
    if abs(x) > 20 or abs(y) > 20 or z < -1.0 or z > 5.0:
        return None
    yaw_value = row.get("yaw_deg")
    if yaw_scale != 1.0 and yaw_value not in (None, ""):
        yaw = math.radians(float(yaw_value) * yaw_scale)
        distance = math.hypot(x, y)
        x = distance * math.cos(yaw)
        y = distance * math.sin(yaw)
    if rotation_ca != 1.0 or rotation_sa != 0.0:
        x, y = (x * rotation_ca - y * rotation_sa,
                x * rotation_sa + y * rotation_ca)
    if mirror_y:
        y = 2.0 * float(mirror_center_m) - y
    return x, y, z


def _box_vertices(box):
    angle = math.radians(float(box.get("angle_deg", 0.0) or 0.0))
    ca, sa = math.cos(angle), math.sin(angle)
    cx = float(box.get("cx_m", 0.0) or 0.0)
    cy = float(box.get("cy_m", 0.0) or 0.0)
    half_length = max(0.025, float(box.get("length_m", 0.05) or 0.05) / 2.0)
    half_width = max(0.025, float(box.get("width_m", 0.05) or 0.05) / 2.0)
    z0 = float(box.get("z_bottom_m", 0.0) or 0.0)
    z1 = max(z0 + 0.01, float(box.get("z_top_m", 0.05) or 0.05))
    ring = ((-half_length, -half_width), (half_length, -half_width),
            (half_length, half_width), (-half_length, half_width))
    vertices = []
    for z in (z0, z1):
        for u, v in ring:
            vertices.append((cx + u * ca - v * sa, cy + u * sa + v * ca, z))
    return vertices


def _box_faces(base):
    return [
        (base + 0, base + 3, base + 2), (base + 0, base + 2, base + 1),
        (base + 4, base + 5, base + 6), (base + 4, base + 6, base + 7),
        (base + 0, base + 1, base + 5), (base + 0, base + 5, base + 4),
        (base + 1, base + 2, base + 6), (base + 1, base + 6, base + 5),
        (base + 2, base + 3, base + 7), (base + 2, base + 7, base + 6),
        (base + 3, base + 0, base + 4), (base + 3, base + 4, base + 7),
    ]


def build_ply(points, boxes, scan_id="", yaw_scale=1.0, map_rotation_deg=0.0,
              mirror_y=False, mirror_center_m=0.0):
    """Return ASCII PLY text for point dicts (x,y,z) and reconstruction boxes."""
    box_vertices = [(_box_vertices(box), _box_color(box)) for box in boxes]
    vertex_count = len(points) + sum(len(vertices) for vertices, _ in box_vertices)
    face_count = len(boxes) * 12
    lines = [
        "ply",
        "format ascii 1.0",
        f"comment AIoT room scan {scan_id}",
        "comment frame x=right y=forward z=up units=meters",
        f"comment yaw_scale={yaw_scale:.3f} map_rotation_deg={map_rotation_deg:.1f}",
        f"comment mirror_y={1 if mirror_y else 0} mirror_center_m={mirror_center_m:.3f}",
        f"comment points={len(points)} boxes={len(boxes)}",
        f"element vertex {vertex_count}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        f"element face {face_count}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    vertex_lines = []
    face_lines = []
    for point in points:
        vertex_lines.append(
            f"{point['x']:.4f} {point['y']:.4f} {point['z']:.4f} "
            f"{point['r']} {point['g']} {point['b']}")
    base = len(points)
    for vertices, (red, green, blue) in box_vertices:
        for x, y, z in vertices:
            vertex_lines.append(f"{x:.4f} {y:.4f} {z:.4f} {red} {green} {blue}")
        for face in _box_faces(base):
            face_lines.append(f"3 {face[0]} {face[1]} {face[2]}")
        base += len(vertices)
    # PLY requires all vertex elements before all face elements.
    lines.extend(vertex_lines)
    lines.extend(face_lines)
    return "\n".join(lines) + "\n"


def _relative(path: Path) -> str:
    try:
        return path.relative_to(RESEARCH.parent.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_path(folder: Path, stem: str) -> Path:
    candidate = folder / f"{stem}.ply"
    index = 1
    while candidate.exists():
        candidate = folder / f"{stem}-{index}.ply"
        index += 1
    return candidate


def export_scene(scan_id: str, yaw_scale: float = 1.0,
                 map_rotation_deg: float = 0.0, mirror_y=None,
                 mirror_center_m=None, snap_wall_objects=None) -> dict:
    scan_dir = SCANS / scan_id
    points_path = scan_dir / "points.csv"
    if not points_path.is_file():
        raise ValueError("points.csv not found")
    with points_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    annotations = read_json(scan_dir / "annotations.json", {}) or {}
    default_mirror, default_center = _mirror_from_annotations(annotations)
    if mirror_y is None:
        mirror_y = default_mirror
    if mirror_center_m is None:
        mirror_center_m = default_center
    if snap_wall_objects is None:
        room = annotations.get("room") or {}
        try:
            snap_wall_objects = bool(float(room.get("snap_wall_objects", 1.0)))
        except (TypeError, ValueError):
            snap_wall_objects = True
    mirror_y = bool(mirror_y)
    mirror_center_m = float(mirror_center_m)
    reconstruction = reconstruct_points(
        rows, yaw_scale=yaw_scale, map_rotation_deg=map_rotation_deg,
        annotations=annotations, mirror_y=mirror_y,
        mirror_center_m=mirror_center_m,
        snap_wall_objects=bool(snap_wall_objects), add_anchors=True)
    mount_rows = set(int(index) for index in (reconstruction.get("mount_rows") or []))
    rotation_ca = math.cos(math.radians(map_rotation_deg))
    rotation_sa = math.sin(math.radians(map_rotation_deg))
    points = []
    for index, row in enumerate(rows):
        if index in mount_rows:
            continue
        mapped = _map_point(row, yaw_scale, rotation_ca, rotation_sa,
                            mirror_y=mirror_y,
                            mirror_center_m=mirror_center_m)
        if mapped is None:
            continue
        source = str(row.get("range_source") or "")
        red, green, blue = TOF_COLOR if source == "tof" else HC_COLOR
        points.append({"x": mapped[0], "y": mapped[1], "z": mapped[2],
                       "r": red, "g": green, "b": blue})
    boxes = reconstruction.get("boxes") or []
    ply_text = build_ply(points, boxes, scan_id=scan_id,
                         yaw_scale=yaw_scale,
                         map_rotation_deg=map_rotation_deg,
                         mirror_y=mirror_y,
                         mirror_center_m=mirror_center_m)
    SCENES.mkdir(parents=True, exist_ok=True)
    folder = SCENES / scan_id
    folder.mkdir(parents=True, exist_ok=True)
    ply_path = _unique_path(folder, utc_stamp())
    ply_path.write_text(ply_text, encoding="utf-8")
    measured = sum(1 for box in boxes if str(box.get("source")) != "prior")
    metadata = {
        "scan_id": scan_id,
        "created_utc": utc_iso(),
        "yaw_scale": round(float(yaw_scale), 3),
        "map_rotation_deg": round(float(map_rotation_deg), 1),
        "mirror_y": bool(mirror_y),
        "mirror_center_m": round(float(mirror_center_m), 3),
        "snap_wall_objects": bool(snap_wall_objects),
        "points": len(points),
        "boxes": len(boxes),
        "measured_boxes": measured,
        "prior_boxes": len(boxes) - measured,
        "faces": len(boxes) * 12,
        "ply": ply_path.name,
        "sha256": _sha256(ply_path),
        "box_details": boxes,
    }
    metadata_path = ply_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return {
        "ok": True,
        "scan_id": scan_id,
        "folder": _relative(folder),
        "file": _relative(ply_path),
        "metadata_file": _relative(metadata_path),
        "counts": {
            "points": len(points),
            "boxes": len(boxes),
            "measured_boxes": measured,
            "prior_boxes": len(boxes) - measured,
            "faces": len(boxes) * 12,
        },
        "bytes": ply_path.stat().st_size,
        "sha256": metadata["sha256"],
    }
