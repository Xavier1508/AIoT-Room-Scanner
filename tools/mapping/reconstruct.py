#!/usr/bin/env python3
"""Reconstruct a top-down occupancy grid and estimated solid boxes.

This is a 2.5D reconstruction from one fixed scanner viewpoint: near-mount
returns are removed, points are clustered in the x/y plane, each cluster is
fitted with an oriented rectangle, and the rectangle is extruded from the floor
to the observed top. Wall-like clusters that contain two surfaces are split at
the largest gap so a corner does not become one very thick block.

The result is an estimate, not a full mesh; hidden sides are inferred. Manual
annotations (label override, hide, merge) are applied by ``apply_annotations``.
"""
from __future__ import annotations

import math
from collections import defaultdict

from common import RESEARCH, read_json

WALL_LABELS = ("wall", "wall_edge")

# Known object anchors from the clean 8-sample reference scan
# 20261110T184241Z (Mirror Y ON, map rotation -1.1 deg). They keep the bed and
# fan at their usual places even when a fast scan has too few points to fit
# them reliably. research/mapping/object_anchors.json may override these.
DEFAULT_ANCHORS = (
    {"label": "bed", "cx_m": 1.346, "cy_m": 0.004, "angle_deg": -1.2,
     "length_m": 2.0, "width_m": 1.2, "z_bottom_m": 0.0, "z_top_m": 0.62,
     "match_m": 0.75, "source": "reference-20261110T184241Z"},
    {"label": "fan", "cx_m": 0.822, "cy_m": 1.254, "angle_deg": 81.8,
     "length_m": 0.508, "width_m": 0.446, "z_bottom_m": 0.0, "z_top_m": 0.538,
     "match_m": 0.60, "source": "reference-20261110T184241Z"},
)


def _sensor_anchor(annotations, mirror_y, mirror_center_m):
    """Return the scanner (x, y) in the displayed/prior frame.

    The raw scanner is at (0, 0); Mirror Y maps it to (0, 2*center). The
    dashboard can override this anchor, and otherwise uses the centre of the
    partition block so the axes visibly sit on the sensor mount.
    """
    room = (annotations or {}).get("room") or {}
    configured = room.get("sensor_origin_m")
    if isinstance(configured, (list, tuple)) and len(configured) >= 2:
        try:
            x = float(configured[0])
            y = float(configured[1])
            if math.isfinite(x) and math.isfinite(y):
                return x, y
        except (TypeError, ValueError):
            pass
    for item in (annotations or {}).get("manual_boxes") or []:
        if not isinstance(item, dict) or str(item.get("label")) != "partition":
            continue
        try:
            x = float(item.get("cx_m"))
            y = float(item.get("cy_m"))
            if math.isfinite(x) and math.isfinite(y):
                return x, y
        except (TypeError, ValueError):
            continue
    return 0.0, (2.0 * float(mirror_center_m) if mirror_y else 0.0)


def _percentile(values, fraction):
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
    return values[index]


def _cluster_indices(points, eps_m, use_z=False):
    parent = list(range(len(points)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    eps2 = eps_m * eps_m
    for i in range(len(points)):
        xi, yi = points[i][0], points[i][1]
        zi = points[i][2] if use_z else 0.0
        for j in range(i + 1, len(points)):
            dx = xi - points[j][0]
            dy = yi - points[j][1]
            dz = zi - (points[j][2] if use_z else 0.0)
            if dx * dx + dy * dy + dz * dz <= eps2:
                union(i, j)
    groups = defaultdict(list)
    for index in range(len(points)):
        groups[find(index)].append(index)
    return list(groups.values())


def _fit_geometry(cluster, angle_override=None):
    """Fit an oriented rectangle to a cluster of (x, y, z, source) points.

    ``angle_override`` is used by the wall-constrained object fit: large low
    objects near a wall are projected onto the wall direction instead of the
    PCA direction, which otherwise makes a bed/desk look diagonally crooked.
    """
    xs = [point[0] for point in cluster]
    ys = [point[1] for point in cluster]
    zs = [point[2] for point in cluster]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    if angle_override is None:
        cov_xx = sum((x - mx) ** 2 for x in xs) / len(xs)
        cov_yy = sum((y - my) ** 2 for y in ys) / len(ys)
        cov_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
        angle = 0.5 * math.atan2(2 * cov_xy, cov_xx - cov_yy)
    else:
        angle = float(angle_override)
    ca, sa = math.cos(angle), math.sin(angle)
    us = [(x - mx) * ca + (y - my) * sa for x, y in zip(xs, ys)]
    vs = [-(x - mx) * sa + (y - my) * ca for x, y in zip(xs, ys)]
    u0, u1 = _percentile(us, 0.02), _percentile(us, 0.98)
    v0, v1 = _percentile(vs, 0.02), _percentile(vs, 0.98)
    length = max(0.10, u1 - u0)
    width = max(0.10, v1 - v0)
    uc, vc = (u0 + u1) / 2, (v0 + v1) / 2
    cx = mx + uc * ca - vc * sa
    cy = my + uc * sa + vc * ca
    z_top = max(0.10, min(3.0, _percentile(zs, 0.98)))
    return {
        "cx": cx,
        "cy": cy,
        "angle": angle,
        "length": length,
        "width": width,
        "width_robust": max(0.10, _percentile(vs, 0.75) - _percentile(vs, 0.25)),
        "z_top": z_top,
        "points": len(cluster),
        "range_x": [min(xs), max(xs)],
        "range_y": [min(ys), max(ys)],
    }


def _classify(geometry):
    long_side = max(geometry["length"], geometry["width"])
    short_side = min(geometry["length"], geometry["width"])
    distance = math.hypot(geometry["cx"], geometry["cy"])
    if long_side >= 1.8 and short_side <= 0.9 and geometry["z_top"] >= 1.2:
        return "wall"
    if geometry["z_top"] >= 1.5 and short_side <= 0.35 and long_side >= 0.15:
        return "wall_edge"
    if geometry["z_top"] >= 1.5 and short_side <= 0.60 and long_side >= 0.80:
        return "wall"
    # A small, thin, tall cluster close to the scanner is the table/mount edge,
    # not a room object. It is removed from the 3D map.
    if (distance <= 1.30 and long_side <= 0.45 and short_side <= 0.16
            and geometry["z_top"] >= 0.90):
        return "mount"
    return "object"


def _box_id(geometry):
    return (f"{geometry['cx']:.2f}|{geometry['cy']:.2f}|"
            f"{geometry['length']:.2f}|{geometry['width']:.2f}")


def _split_wall_cluster(cluster, min_points, depth=0, max_depth=2):
    """Split a wall cluster at its largest along-wall gap.

    A single fixed viewpoint can see two wall surfaces that touch inside the
    clustering radius (for example the far wall and the left wall). One thick
    box for both is misleading, so split them when a real gap exists.
    """
    geometry = _fit_geometry(cluster)
    if depth >= max_depth or _classify(geometry) != "wall":
        return [cluster]
    if geometry["width"] <= 0.65:
        return [cluster]
    angle = geometry["angle"]
    ca, sa = math.cos(angle), math.sin(angle)
    mx = sum(point[0] for point in cluster) / len(cluster)
    my = sum(point[1] for point in cluster) / len(cluster)
    us = [(point[0] - mx) * ca + (point[1] - my) * sa for point in cluster]
    order = sorted(range(len(cluster)), key=lambda index: us[index])
    best_gap = 0.0
    best_index = -1
    for position in range(len(order) - 1):
        gap = us[order[position + 1]] - us[order[position]]
        if gap > best_gap:
            best_gap = gap
            best_index = position
    if best_gap < 0.30 or best_index < 0:
        return [cluster]
    left = [cluster[index] for index in order[:best_index + 1]]
    right = [cluster[index] for index in order[best_index + 1:]]
    if len(left) < min_points or len(right) < min_points:
        return [cluster]
    return (_split_wall_cluster(left, min_points, depth + 1, max_depth) +
            _split_wall_cluster(right, min_points, depth + 1, max_depth))


def _angle_distance(first, second):
    """Smallest absolute difference between two undirected line angles."""
    delta = (float(first) - float(second) + math.pi / 2.0) % math.pi
    return abs(delta - math.pi / 2.0)


def _box_from_cluster(cluster, force_label=None, wall_angles=None,
                      snap_wall_objects=False):
    geometry = _fit_geometry(cluster)
    label = force_label or _classify(geometry)
    angle_source = "pca"
    # A large, low object next to a wall is almost always parallel to that
    # wall. PCA alone fits the visible L-shape and makes a bed/desk look
    # diagonally crooked. Small objects (e.g. the fan) are left untouched.
    if (snap_wall_objects and label == "object" and wall_angles
            and geometry["length"] >= 1.2 and geometry["z_top"] <= 0.90):
        nearest = min(wall_angles,
                      key=lambda value: _angle_distance(geometry["angle"], value))
        if _angle_distance(geometry["angle"], nearest) <= math.radians(30):
            geometry = _fit_geometry(cluster, angle_override=nearest)
            angle_source = "wall_snap"
    # HC beam spread makes a wall look 0.5 m thick. Keep the observed width in
    # metadata but draw the wall with the robust 25-75% spread.
    display_width = geometry["width"]
    if label == "wall":
        display_width = min(display_width, max(0.12, geometry["width_robust"]))
    corners = [
        (geometry["cx"] + u * math.cos(geometry["angle"]) - v * math.sin(geometry["angle"]),
         geometry["cy"] + u * math.sin(geometry["angle"]) + v * math.cos(geometry["angle"]))
        for u, v in ((-geometry["length"] / 2, -display_width / 2),
                     (geometry["length"] / 2, -display_width / 2),
                     (geometry["length"] / 2, display_width / 2),
                     (-geometry["length"] / 2, display_width / 2))
    ]
    nearest = min(math.hypot(x, y) for x, y in corners)
    return {
        "id": _box_id(geometry),
        "label": label,
        "label_source": "auto",
        "angle_source": angle_source,
        "cx_m": round(geometry["cx"], 3),
        "cy_m": round(geometry["cy"], 3),
        "angle_deg": round(math.degrees(geometry["angle"]), 1),
        "length_m": round(geometry["length"], 3),
        "width_m": round(display_width, 3),
        "width_observed_m": round(geometry["width"], 3),
        "z_bottom_m": 0.0,
        "z_top_m": round(geometry["z_top"], 3),
        "distance_m": round(math.hypot(geometry["cx"], geometry["cy"]), 2),
        "nearest_m": round(nearest, 2),
        "points": geometry["points"],
        "range_x_m": [round(geometry["range_x"][0], 3), round(geometry["range_x"][1], 3)],
        "range_y_m": [round(geometry["range_y"][0], 3), round(geometry["range_y"][1], 3)],
    }


def _box_corners_xy(box):
    angle = math.radians(float(box.get("angle_deg", 0.0)))
    ca, sa = math.cos(angle), math.sin(angle)
    half_length = float(box.get("length_m", 0.1)) / 2.0
    half_width = float(box.get("width_m", 0.1)) / 2.0
    cx, cy = float(box.get("cx_m", 0.0)), float(box.get("cy_m", 0.0))
    return [
        (cx + u * ca - v * sa, cy + u * sa + v * ca)
        for u, v in ((-half_length, -half_width), (half_length, -half_width),
                     (half_length, half_width), (-half_length, half_width))
    ]


def _merge_boxes(boxes):
    corners = [corner for box in boxes for corner in _box_corners_xy(box)]
    xs = [corner[0] for corner in corners]
    ys = [corner[1] for corner in corners]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    labels = [box.get("label") for box in boxes if box.get("label") not in ("object", "mount")]
    label = labels[0] if labels and len(set(labels)) == 1 else "object"
    ids = sorted(str(box.get("id")) for box in boxes)
    return {
        "id": "merged:" + "+".join(ids),
        "label": label,
        "label_source": "manual" if any(box.get("label_source") == "manual" for box in boxes) else "auto",
        "cx_m": round((x0 + x1) / 2.0, 3),
        "cy_m": round((y0 + y1) / 2.0, 3),
        "angle_deg": 0.0,
        "length_m": round(max(0.10, x1 - x0), 3),
        "width_m": round(max(0.10, y1 - y0), 3),
        "z_bottom_m": 0.0,
        "z_top_m": round(max(float(box.get("z_top_m", 0.1)) for box in boxes), 3),
        "distance_m": round(math.hypot((x0 + x1) / 2.0, (y0 + y1) / 2.0), 2),
        "nearest_m": round(min(math.hypot(x, y) for x, y in corners), 2),
        "points": sum(int(box.get("points", 0)) for box in boxes),
        "range_x_m": [round(x0, 3), round(x1, 3)],
        "range_y_m": [round(y0, 3), round(y1, 3)],
        "merged_from": ids,
    }


def _parse_box_key(value):
    parts = str(value).split("|")
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _resolve_box_id(value, boxes):
    """Resolve an old annotation id to a current box id.

    Yaw calibration changes box centroids, so a stored key may not match
    exactly. Fall back to the nearest box within 0.8 m.
    """
    text = str(value)
    if any(str(box.get("id")) == text for box in boxes):
        return text
    parsed = _parse_box_key(text)
    if parsed is None:
        return None
    best_id = None
    best_distance = float("inf")
    for box in boxes:
        distance = math.hypot(float(box.get("cx_m", 0.0)) - parsed[0],
                              float(box.get("cy_m", 0.0)) - parsed[1])
        if distance < best_distance:
            best_distance = distance
            best_id = str(box.get("id"))
    return best_id if best_distance <= 0.80 else None


def _anchor_items(annotations):
    items = (annotations or {}).get("anchors")
    if not items:
        try:
            items = read_json(RESEARCH / "object_anchors.json", {}).get("anchors")
        except (OSError, ValueError):
            items = None
    return items or list(DEFAULT_ANCHORS)


def _apply_anchors(boxes, annotations):
    """Snap the known bed/fan anchors onto measured boxes, or add a prior.

    The anchors are the tape/reference positions from the 8-sample scan. A new
    scan keeps them even when its point cloud is sparse; a measured box near an
    anchor is snapped to the reference centre/angle/size so the bed and fan are
    always placed at their usual positions.
    """
    anchors = _anchor_items(annotations)
    matches = []
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            continue
        label = str(anchor.get("label") or "").strip()[:24]
        if not label:
            continue
        try:
            cx = float(anchor.get("cx_m", 0.0))
            cy = float(anchor.get("cy_m", 0.0))
            angle = float(anchor.get("angle_deg", 0.0))
            length = max(0.05, min(10.0, float(anchor.get("length_m", 0.2))))
            width = max(0.05, min(10.0, float(anchor.get("width_m", 0.2))))
            z0 = max(0.0, min(4.0, float(anchor.get("z_bottom_m", 0.0))))
            z1 = max(z0 + 0.05, min(4.0, float(anchor.get("z_top_m", 0.6))))
            match_m = max(0.05, min(2.0, float(anchor.get("match_m", 0.6))))
        except (TypeError, ValueError):
            continue
        labelled = [box for box in boxes if str(box.get("label")) == label]
        candidates = labelled
        candidate = None
        if candidates:
            candidate = min(
                candidates,
                key=lambda box: math.hypot(float(box.get("cx_m", 0.0)) - cx,
                                           float(box.get("cy_m", 0.0)) - cy))
            distance = math.hypot(float(candidate.get("cx_m", 0.0)) - cx,
                                  float(candidate.get("cy_m", 0.0)) - cy)
            if distance > match_m:
                candidate = None
        if candidate is not None:
            candidate.update({
                "cx_m": round(cx, 3), "cy_m": round(cy, 3),
                "angle_deg": round(angle, 3),
                "length_m": round(length, 3), "width_m": round(width, 3),
                "z_bottom_m": round(z0, 3), "z_top_m": round(z1, 3),
                "label": label,
                "label_source": ("manual" if candidate.get("label_source") == "manual"
                                 else "anchor"),
                "anchor_source": str(anchor.get("source", "reference")),
                "snapped_to_anchor": True,
                "size_source": "anchor", "angle_source": "anchor",
            })
            matches.append({"label": label, "box_id": str(candidate.get("id")),
                            "matched": True,
                            "distance_m": round(distance, 3)})
            continue
        box = {
            "id": f"anchor:{index}:{label}",
            "label": label, "label_source": "prior", "source": "prior",
            "anchor_source": str(anchor.get("source", "reference")),
            "snapped_to_anchor": False,
            "size_source": "anchor", "angle_source": "anchor",
            "cx_m": round(cx, 3), "cy_m": round(cy, 3),
            "angle_deg": round(angle, 3),
            "length_m": round(length, 3), "width_m": round(width, 3),
            "z_bottom_m": round(z0, 3), "z_top_m": round(z1, 3),
            "points": 0,
        }
        corners = _box_corners_xy(box)
        box["distance_m"] = round(math.hypot(cx, cy), 2)
        box["nearest_m"] = round(min(math.hypot(x, y) for x, y in corners), 2)
        boxes.append(box)
        matches.append({"label": label, "box_id": box["id"],
                        "matched": False, "distance_m": None})
    return anchors, matches


def apply_annotations(result, annotations, add_anchors=False):
    """Apply manual label overrides, hidden boxes and pairwise merges."""
    annotations = annotations or {}
    labels = annotations.get("labels") or {}
    size_overrides = annotations.get("size_overrides") or {}
    hidden_raw = annotations.get("hidden") or []
    removed_raw = annotations.get("removed") or []
    merges_raw = annotations.get("merges") or []
    boxes = [dict(box) for box in (result.get("boxes") or [])]
    hidden = {resolved for item in hidden_raw
              if (resolved := _resolve_box_id(item, boxes)) is not None}
    removed = {resolved for item in removed_raw
               if (resolved := _resolve_box_id(item, boxes)) is not None}
    hidden.update(removed)
    boxes = [box for box in boxes if str(box.get("id")) not in hidden]
    resolved_labels = {}
    for key, override in labels.items():
        target = _resolve_box_id(key, boxes)
        if target:
            resolved_labels[target] = str(override)[:24]
    for box in boxes:
        override = resolved_labels.get(str(box.get("id")))
        if override:
            box["label"] = override
            box["label_source"] = "manual"
    # Measured boxes are fitted from a single viewpoint, so the hidden width
    # can be overestimated. A locked length/width keeps a tape-measured object
    # (for example a 2.00 x 1.20 m bed) exact without discarding its measured
    # centre and angle.
    resolved_sizes = {}
    for key, override in size_overrides.items():
        if not isinstance(override, dict):
            continue
        target = _resolve_box_id(key, boxes)
        if not target:
            continue
        resolved = {}
        for field, lower, upper in (("length_m", 0.05, 10.0),
                                    ("width_m", 0.05, 10.0),
                                    ("z_bottom_m", 0.0, 4.0),
                                    ("z_top_m", 0.05, 4.0)):
            if field not in override:
                continue
            try:
                resolved[field] = round(
                    max(lower, min(upper, float(override[field]))), 3)
            except (TypeError, ValueError):
                continue
        if resolved:
            resolved_sizes[target] = resolved
    for box in boxes:
        override = resolved_sizes.get(str(box.get("id")))
        if override:
            box.update(override)
            z0 = float(box.get("z_bottom_m", 0.0) or 0.0)
            z1 = float(box.get("z_top_m", z0 + 0.05) or (z0 + 0.05))
            box["z_top_m"] = round(max(z0 + 0.05, z1), 3)
            box["size_source"] = "manual"
    resolved_merges = []
    for pair in merges_raw:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        first = _resolve_box_id(pair[0], boxes)
        second = _resolve_box_id(pair[1], boxes)
        if not first or not second or first == second:
            continue
        selected = [box for box in boxes if str(box.get("id")) in (first, second)]
        if len(selected) != 2:
            continue
        merged = _merge_boxes(selected)
        boxes = [box for box in boxes if str(box.get("id")) not in (first, second)]
        boxes.append(merged)
        resolved_merges.append([first, second])
    boxes.sort(key=lambda box: (box.get("label") not in WALL_LABELS,
                                -int(box.get("points", 0))))
    manual_boxes = []
    existing_ids = {str(box.get("id")) for box in boxes}
    for index, item in enumerate(annotations.get("manual_boxes") or []):
        if not isinstance(item, dict):
            continue
        try:
            box = {
                "id": str(item.get("id") or f"manual:{index}"),
                "label": str(item.get("label", "object"))[:24],
                "label_source": "prior" if item.get("source") == "prior" else "manual",
                "source": "prior" if item.get("source") == "prior" else "manual",
                "cx_m": float(item.get("cx_m", 0.0)),
                "cy_m": float(item.get("cy_m", 0.0)),
                "angle_deg": float(item.get("angle_deg", 0.0)),
                "length_m": max(0.05, float(item.get("length_m", 0.1))),
                "width_m": max(0.05, float(item.get("width_m", 0.1))),
                "z_bottom_m": max(0.0, float(item.get("z_bottom_m", 0.0))),
                "z_top_m": max(0.05, float(item.get("z_top_m", 0.5))),
                "points": int(item.get("points", 0)),
            }
        except (TypeError, ValueError):
            continue
        if box["id"] in existing_ids:
            box["id"] = f"manual:{index}"
        corners = _box_corners_xy(box)
        box["distance_m"] = round(math.hypot(box["cx_m"], box["cy_m"]), 2)
        box["nearest_m"] = round(min(math.hypot(x, y) for x, y in corners), 2)
        existing_ids.add(box["id"])
        manual_boxes.append(box)
    for box in manual_boxes:
        override = labels.get(str(box.get("id")))
        if override:
            box["label"] = str(override)[:24]
            box["label_source"] = "manual"
            resolved_labels[str(box["id"])] = str(override)[:24]
    boxes.extend(manual_boxes)
    if add_anchors:
        anchors, anchor_matches = _apply_anchors(boxes, annotations)
    else:
        anchors, anchor_matches = [], []
    boxes = [box for box in boxes if str(box.get("id")) not in hidden]
    boxes.sort(key=lambda box: (box.get("label") not in WALL_LABELS,
                                -int(box.get("points", 0))))
    result["boxes"] = boxes
    result["annotations"] = {
        "labels": resolved_labels,
        "size_overrides": resolved_sizes,
        "hidden": sorted(hidden - removed),
        "removed": sorted(removed),
        "merges": resolved_merges,
        "manual_boxes": manual_boxes,
        "room_outline": annotations.get("room_outline") or [],
        "room": annotations.get("room") or {},
        "point_labels": annotations.get("point_labels") or {},
        "label_catalog": annotations.get("label_catalog") or {},
        "anchors": anchors,
        "anchor_matches": anchor_matches,
    }
    result["annotation_count"] = (len(resolved_labels) + len(resolved_sizes)
                                  + len(hidden) + len(resolved_merges)
                                  + len(manual_boxes)
                                  + sum(len(v) for v in (annotations.get("point_labels") or {}).values()))
    return result


def _detect_wall_lines(points, tolerance_m=0.12, min_span_m=0.60,
                       min_inliers=8, bin_m=0.05, min_bin_count=4):
    """Find dominant axis-aligned wall lines in the x/y plane.

    The dashboard rotation control is used to make the room walls horizontal
    or vertical, so wall detection works on x-constant and y-constant peaks.
    A fixed-viewpoint dense scan otherwise connects the whole room perimeter
    into one cluster; wall-first extraction keeps those long straight
    surfaces out of the object clustering so furniture does not become one
    room-sized box. A peak that passes through the scanner (offset near zero)
    is the yaw-zero scan ray, not a wall, and is rejected.
    """
    if len(points) < min_inliers:
        return []
    lines = []
    for axis in (0, 1):
        bins = defaultdict(int)
        for point in points:
            bins[math.floor(point[axis] / bin_m)] += 1
        peaks = []
        current = []
        for key in sorted(bins):
            if bins[key] < min_bin_count:
                if current:
                    peaks.append(current)
                    current = []
                continue
            if current and key - current[-1] > 1:
                peaks.append(current)
                current = []
            current.append(key)
        if current:
            peaks.append(current)
        candidates = []
        for peak in peaks:
            values = [point[axis] for point in points
                      if peak[0] <= math.floor(point[axis] / bin_m) <= peak[-1]]
            center = _percentile(values, 0.5)
            if abs(center) < 0.40:
                continue
            inliers = [index for index, point in enumerate(points)
                       if abs(point[axis] - center) <= tolerance_m]
            if len(inliers) < min_inliers:
                continue
            if axis == 0:
                ux, uy, nx, ny = 0.0, 1.0, 1.0, 0.0
            else:
                ux, uy, nx, ny = 1.0, 0.0, 0.0, 1.0
            ordered = sorted((ux * points[index][0] + uy * points[index][1],
                              index) for index in inliers)
            runs = []
            current_run = [ordered[0]]
            for previous, item in zip(ordered, ordered[1:]):
                if item[0] - previous[0] > 0.35:
                    runs.append(current_run)
                    current_run = []
                current_run.append(item)
            runs.append(current_run)
            runs.sort(key=lambda run: run[-1][0] - run[0][0], reverse=True)
            longest = runs[0]
            total_span = ordered[-1][0] - ordered[0][0]
            run_span = longest[-1][0] - longest[0][0]
            # A real wall is one continuous surface. Scattered furniture or a
            # sloped ceiling produces short fragments with large gaps.
            if run_span < min_span_m or run_span < 0.75 * total_span:
                continue
            candidates.append({"ux": ux, "uy": uy, "nx": nx, "ny": ny,
                               "offset": center,
                               "inliers": [index for _, index in longest]})
        candidates.sort(key=lambda line: -len(line["inliers"]))
        kept = []
        for line in candidates:
            if any(abs(line["offset"] - other["offset"]) < 0.25 for other in kept):
                continue
            kept.append(line)
        lines.extend(kept)
    return lines


def _wall_line_segments(indices, points, ux, uy, gap_m=0.35, min_points=4):
    """Split one wall line into segments at real along-wall gaps."""
    if not indices:
        return []
    ordered = sorted((ux * points[index][0] + uy * points[index][1], index)
                     for index in indices)
    segments = []
    current = [ordered[0][1]]
    for (previous_u, _), (current_u, index) in zip(ordered, ordered[1:]):
        if current_u - previous_u > gap_m:
            segments.append(current)
            current = []
        current.append(index)
    segments.append(current)
    return [segment for segment in segments if len(segment) >= min_points]


def _line_span(line, points):
    us = [line["ux"] * points[index][0] + line["uy"] * points[index][1]
          for index in line["inliers"]]
    return max(us) - min(us)


def reconstruct_points(rows, cell_m=0.10, eps_m=0.30, min_points=5,
                       near_field_m=0.40, mount_guard_m=0.75,
                       mount_guard_z_m=0.72, fov_limit_deg=60,
                       yaw_scale=0.76, map_rotation_deg=10.7,
                       annotations=None, mirror_y=False,
                       mirror_center_m=0.0, snap_wall_objects=False,
                       add_anchors=False):
    try:
        yaw_scale = max(0.40, min(1.0, float(yaw_scale)))
    except (TypeError, ValueError):
        yaw_scale = 1.0
    try:
        map_rotation = math.radians(float(map_rotation_deg))
    except (TypeError, ValueError):
        map_rotation = 0.0
    rotation_ca, rotation_sa = math.cos(map_rotation), math.sin(map_rotation)
    effective_fov_deg = max(5.0, min(90.0, float(fov_limit_deg) * yaw_scale))
    points = []
    mount_points = 0
    mount_rows = []
    ceiling_rows = []
    for row_index, row in enumerate(rows):
        try:
            x = float(row.get("x_mm")) / 1000.0
            y = float(row.get("y_mm")) / 1000.0
            z = float(row.get("z_mm")) / 1000.0
        except (TypeError, ValueError):
            continue
        if abs(x) > 20 or abs(y) > 20 or z < -1.0 or z > 5.0:
            continue
        # The commanded yaw is larger than the effective mechanical yaw. The
        # dense scan's wall thickness is minimised around 0.65; keep this
        # adjustable until a known-target calibration confirms it.
        yaw_value = row.get("yaw_deg")
        if yaw_scale != 1.0 and yaw_value not in (None, ""):
            try:
                yaw = math.radians(float(yaw_value) * yaw_scale)
                distance = math.hypot(x, y)
                x = distance * math.cos(yaw)
                y = distance * math.sin(yaw)
            except (TypeError, ValueError):
                pass
        if rotation_ca != 1.0 or rotation_sa != 0.0:
            x, y = (x * rotation_ca - y * rotation_sa,
                    x * rotation_sa + y * rotation_ca)
        # Below-floor returns are floor/arm artefacts, not room geometry.
        if z < -0.05:
            mount_points += 1
            mount_rows.append(row_index)
            continue
        distance = math.hypot(x, y)
        # The scanner mount/arm is a near-field return, not the room.
        if distance < near_field_m:
            mount_points += 1
            mount_rows.append(row_index)
            continue
        # Low returns inside the mount radius are the table/arm edge that the
        # downward servo sweep hits. Keep them out of the 3D map.
        if distance < mount_guard_m and z < mount_guard_z_m:
            mount_points += 1
            mount_rows.append(row_index)
            continue
        range_mm = row.get("range_mm")
        if range_mm is not None:
            try:
                if float(range_mm) < near_field_m * 1000.0:
                    mount_points += 1
                    mount_rows.append(row_index)
                    continue
            except (TypeError, ValueError):
                pass
        # Apply the prior-frame mirror only after sensor-relative filtering so
        # near-field/mount rejection still uses the real scanner origin.
        if mirror_y:
            y = 2.0 * float(mirror_center_m) - y
        points.append((x, y, z, row.get("range_source") or "", row_index))

    if not points:
        result = {"cell_m": cell_m, "eps_m": eps_m, "point_count": 0,
                  "mount_points": mount_points, "ceiling_points": 0,
                  "mount_rows": mount_rows, "ceiling_rows": ceiling_rows,
                  "mount_boxes": 0,
                  "boxes": [], "grid": [],
                  "occluded_deg": [[-effective_fov_deg, effective_fov_deg]],
                  "fov_limit_deg": effective_fov_deg,
                  "yaw_scale": yaw_scale,
                  "map_rotation_deg": round(math.degrees(map_rotation), 1),
                  "mirror_y": bool(mirror_y),
                  "mirror_center_m": round(float(mirror_center_m), 3),
                  "snap_wall_objects": bool(snap_wall_objects),
                  "add_anchors": bool(add_anchors),
                  "near_field_m": near_field_m,
                  "mount_guard_m": mount_guard_m,
                  "note": "No points after near-mount filtering."}
        return apply_annotations(result, annotations, add_anchors)

    cells = defaultdict(list)
    for point in points:
        cells[(math.floor(point[0] / cell_m), math.floor(point[1] / cell_m))].append(point)

    boxes = []
    wall_lines = _detect_wall_lines(points)
    long_walls = [line for line in wall_lines
                  if _line_span(line, points) >= 1.50]
    wall_indices = set()
    ceiling_points = 0
    if long_walls:
        for line in long_walls:
            wall_indices.update(line["inliers"])
        for line in long_walls:
            for segment in _wall_line_segments(line["inliers"], points,
                                               line["ux"], line["uy"]):
                cluster = [points[index] for index in segment]
                geometry = _fit_geometry(cluster)
                label = "wall" if geometry["length"] >= 1.50 else "wall_edge"
                boxes.append(_box_from_cluster(cluster, force_label=label))
        wall_boxes = [box for box in boxes if box["label"] in WALL_LABELS]
        object_wall_angles = [math.radians(float(box["angle_deg"]))
                              for box in wall_boxes]
        interior = [point for index, point in enumerate(points)
                    if index not in wall_indices]
        for indices in _cluster_indices(interior, eps_m, use_z=True):
            if len(indices) < min_points:
                continue
            cluster = [interior[index] for index in indices]
            geometry = _fit_geometry(cluster)
            # A surface parallel to a wall and just outside it is the sloped
            # ceiling above that wall. Extend the wall instead of drawing a
            # second, thicker wall.
            extension = None
            for line in long_walls:
                distance = abs(line["nx"] * geometry["cx"]
                               + line["ny"] * geometry["cy"] - line["offset"])
                wall_angle = math.atan2(line["uy"], line["ux"])
                difference = abs((geometry["angle"] - wall_angle + math.pi / 2)
                                 % math.pi - math.pi / 2)
                if distance <= 0.30 and difference <= math.radians(20):
                    extension = line
                    break
            if extension is not None:
                best_box = None
                best_distance = float("inf")
                for box in wall_boxes:
                    distance = abs(extension["nx"] * box["cx_m"]
                                   + extension["ny"] * box["cy_m"]
                                   - extension["offset"])
                    if distance < best_distance:
                        best_distance = distance
                        best_box = box
                if best_box is not None:
                    best_box["z_top_m"] = round(max(float(best_box["z_top_m"]),
                                                    geometry["z_top"]), 3)
                ceiling_points += len(cluster)
                ceiling_rows.extend(interior[index][4] for index in indices)
                continue
            for part in _split_wall_cluster(cluster, min_points):
                if len(part) < min_points:
                    continue
                boxes.append(_box_from_cluster(
                    part, wall_angles=object_wall_angles,
                    snap_wall_objects=snap_wall_objects))
    else:
        # Sparse or non-axis-aligned scans keep the original 2D clustering.
        fallback_eps = max(eps_m, 0.45)
        for indices in _cluster_indices(points, fallback_eps):
            if len(indices) < min_points:
                continue
            cluster = [points[index] for index in indices]
            for part in _split_wall_cluster(cluster, min_points):
                if len(part) < min_points:
                    continue
                boxes.append(_box_from_cluster(part))

    boxes.sort(key=lambda box: (box["label"] not in WALL_LABELS, -box["points"]))
    mount_boxes = 0
    visible_boxes = []
    for box in boxes:
        if box["label"] == "mount":
            mount_boxes += 1
        else:
            visible_boxes.append(box)
    boxes = visible_boxes
    grid = [[cell[0], cell[1], len(cells[cell])] for cell in sorted(cells)]
    occluded = []
    bin_size = 10
    fov_int = int(round(effective_fov_deg))
    # The displayed map is mirrored into the prior frame, so the scanner is
    # not at (0, 0); it sits at the mirror image of the raw origin or at the
    # configured/partition anchor.
    sensor_x, sensor_y = _sensor_anchor(annotations, mirror_y, mirror_center_m)
    facing_deg = (-math.degrees(map_rotation) if mirror_y
                  else math.degrees(map_rotation))
    for start in range(-fov_int, fov_int, bin_size):
        count = 0
        for point in points:
            x, y = point[0], point[1]
            yaw = math.degrees(math.atan2(y - sensor_y, x - sensor_x)) - facing_deg
            if start <= yaw < start + bin_size:
                count += 1
        if count < 2:
            occluded.append([start + facing_deg, start + bin_size + facing_deg])
    result = {
        "cell_m": cell_m,
        "eps_m": eps_m,
        "point_count": len(points),
        "mount_points": mount_points,
        "ceiling_points": ceiling_points,
        "mount_rows": mount_rows,
        "ceiling_rows": ceiling_rows,
        "mount_boxes": mount_boxes,
        "boxes": boxes,
        "grid": grid,
        "occluded_deg": occluded,
        "fov_limit_deg": effective_fov_deg,
        "yaw_scale": yaw_scale,
        "map_rotation_deg": round(math.degrees(map_rotation), 1),
        "mirror_y": bool(mirror_y),
        "mirror_center_m": round(float(mirror_center_m), 3),
        "snap_wall_objects": bool(snap_wall_objects),
        "add_anchors": bool(add_anchors),
        "near_field_m": near_field_m,
        "mount_guard_m": mount_guard_m,
        "note": ("Estimated boxes from one fixed viewpoint; hidden sides are inferred. "
                 "Occluded sectors have too few returns. Near-field mount returns are hidden. "
                 "Yaw scale is provisional until a known-target calibration."),
    }
    return apply_annotations(result, annotations, add_anchors)


def _axis_residual_deg(angle_deg):
    value = abs(float(angle_deg)) % 90.0
    return min(value, 90.0 - value)


def _wall_score(result, rotation_deg=0.0):
    all_boxes = result.get("boxes") or []
    walls = [box for box in all_boxes
             if box.get("label") in WALL_LABELS
             and str(box.get("source")) != "prior"]
    total_points = sum(int(box.get("points", 0) or 0) for box in walls)
    if len(walls) < 2 or total_points <= 0:
        return -1e9, {
            "wall_count": len(walls),
            "wall_points": total_points,
            "residual_deg": 180.0,
            "wall_length_m": 0.0,
            "wall_thickness_m": 0.0,
            "wall_angles_deg": [],
            "object_align_bonus": 0.0,
        }
    residual = sum(
        int(box.get("points", 0) or 0) * _axis_residual_deg(box.get("angle_deg", 0.0))
        for box in walls) / total_points
    length = sum(float(box.get("length_m", 0.0) or 0.0) for box in walls)
    thickness = sum(
        int(box.get("points", 0) or 0)
        * float(box.get("width_observed_m", box.get("width_m", 0.0)) or 0.0)
        for box in walls) / total_points
    wall_angles = [float(box.get("angle_deg", 0.0)) for box in walls]
    # Large low objects (the bed/desk class) should be snap-able to a wall.
    # This prevents the search from choosing a rotation that straightens the
    # walls only by hiding a false mid-room wall and leaving the bed diagonal.
    object_bonus = 0.0
    for box in all_boxes:
        if (box.get("label") in WALL_LABELS + ("mount",)
                or str(box.get("source")) == "prior"
                or float(box.get("length_m", 0.0) or 0.0) < 1.2
                or float(box.get("z_top_m", 0.0) or 0.0) > 0.90):
            continue
        nearest = min((_angle_distance(
            math.radians(float(box.get("angle_deg", 0.0))),
            math.radians(angle)) for angle in wall_angles), default=math.pi)
        object_bonus += 20.0 if nearest <= math.radians(25) else -30.0
    # Do not chase a perfect wall fit by rotating the whole room far away from
    # the hand-authored prior frame. 1 degree of residual is visually fine.
    score = (-80.0 * max(0.0, residual - 1.0)
             + 0.05 * total_points
             + 2.0 * length
             + 3.0 * len(walls)
             - 5.0 * thickness
             - 4.0 * abs(rotation_deg)
             + object_bonus
             - 50.0 * max(0, len(walls) - 3)
             - 40.0 * max(0, 3 - len(walls)))
    return score, {
        "wall_count": len(walls),
        "wall_points": total_points,
        "residual_deg": residual,
        "wall_length_m": length,
        "wall_thickness_m": thickness,
        "wall_angles_deg": wall_angles,
        "object_align_bonus": object_bonus,
    }


def auto_align_rotation(rows, yaw_scale=1.0,
                        annotations=None, mirror_y=True,
                        mirror_center_m=0.0, search_min=-5.0,
                        search_max=5.0, coarse_step=0.5,
                        refine_step=0.1):
    """Find the map rotation that makes the measured walls straightest.

    The score is dominated by the weighted residual of wall angles to the
    nearest 0/90 axis, with wall support/length as tie-breakers. This is a
    room-frame correction; the selected object angle is handled separately by
    the wall-constrained object fit.
    """
    def evaluate(rotation):
        result = reconstruct_points(
            rows, yaw_scale=yaw_scale, map_rotation_deg=rotation,
            annotations=annotations, mirror_y=mirror_y,
            mirror_center_m=mirror_center_m, snap_wall_objects=False)
        score, details = _wall_score(result, rotation)
        return {"rotation_deg": float(rotation), "score": float(score), **details}

    candidates = []
    steps = int(round((search_max - search_min) / coarse_step))
    for index in range(steps + 1):
        candidates.append(evaluate(search_min + index * coarse_step))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    center = best["rotation_deg"]
    refine_start = center - coarse_step
    refine_end = center + coarse_step
    refine_steps = int(round((refine_end - refine_start) / refine_step))
    for index in range(refine_steps + 1):
        rotation = refine_start + index * refine_step
        if abs(rotation - center) < 1e-9:
            continue
        candidates.append(evaluate(rotation))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = dict(candidates[0])
    best["search_min"] = search_min
    best["search_max"] = search_max
    best["candidates_evaluated"] = len(candidates)
    best["top_candidates"] = [dict(item) for item in candidates[:5]]
    return best

