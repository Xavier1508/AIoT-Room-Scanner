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

WALL_LABELS = ("wall", "wall_edge")


def _percentile(values, fraction):
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
    return values[index]


def _cluster_indices(points, eps_m):
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
        for j in range(i + 1, len(points)):
            dx = xi - points[j][0]
            dy = yi - points[j][1]
            if dx * dx + dy * dy <= eps2:
                union(i, j)
    groups = defaultdict(list)
    for index in range(len(points)):
        groups[find(index)].append(index)
    return list(groups.values())


def _fit_geometry(cluster):
    """Fit an oriented rectangle to a cluster of (x, y, z, source) points."""
    xs = [point[0] for point in cluster]
    ys = [point[1] for point in cluster]
    zs = [point[2] for point in cluster]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    cov_xx = sum((x - mx) ** 2 for x in xs) / len(xs)
    cov_yy = sum((y - my) ** 2 for y in ys) / len(ys)
    cov_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    angle = 0.5 * math.atan2(2 * cov_xy, cov_xx - cov_yy)
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


def _box_from_cluster(cluster):
    geometry = _fit_geometry(cluster)
    label = _classify(geometry)
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


def apply_annotations(result, annotations):
    """Apply manual label overrides, hidden boxes and pairwise merges."""
    annotations = annotations or {}
    labels = annotations.get("labels") or {}
    hidden_raw = annotations.get("hidden") or []
    merges_raw = annotations.get("merges") or []
    boxes = [dict(box) for box in (result.get("boxes") or [])]
    hidden = {resolved for item in hidden_raw
              if (resolved := _resolve_box_id(item, boxes)) is not None}
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
    boxes = [box for box in boxes if str(box.get("id")) not in hidden]
    boxes.sort(key=lambda box: (box.get("label") not in WALL_LABELS,
                                -int(box.get("points", 0))))
    result["boxes"] = boxes
    result["annotations"] = {
        "labels": resolved_labels,
        "hidden": sorted(hidden),
        "merges": resolved_merges,
        "manual_boxes": manual_boxes,
        "room_outline": annotations.get("room_outline") or [],
        "room": annotations.get("room") or {},
        "point_labels": annotations.get("point_labels") or {},
        "label_catalog": annotations.get("label_catalog") or {},
    }
    result["annotation_count"] = (len(resolved_labels) + len(hidden) + len(resolved_merges)
                                  + len(manual_boxes)
                                  + sum(len(v) for v in (annotations.get("point_labels") or {}).values()))
    return result


def reconstruct_points(rows, cell_m=0.10, eps_m=0.45, min_points=5,
                       near_field_m=0.40, mount_guard_m=0.75,
                       mount_guard_z_m=0.72, fov_limit_deg=60,
                       yaw_scale=0.76, annotations=None):
    try:
        yaw_scale = max(0.40, min(1.0, float(yaw_scale)))
    except (TypeError, ValueError):
        yaw_scale = 1.0
    effective_fov_deg = max(5.0, min(90.0, float(fov_limit_deg) * yaw_scale))
    points = []
    mount_points = 0
    for row in rows:
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
        # Below-floor returns are floor/arm artefacts, not room geometry.
        if z < -0.05:
            mount_points += 1
            continue
        distance = math.hypot(x, y)
        # The scanner mount/arm is a near-field return, not the room.
        if distance < near_field_m:
            mount_points += 1
            continue
        # Low returns inside the mount radius are the table/arm edge that the
        # downward servo sweep hits. Keep them out of the 3D map.
        if distance < mount_guard_m and z < mount_guard_z_m:
            mount_points += 1
            continue
        range_mm = row.get("range_mm")
        if range_mm is not None:
            try:
                if float(range_mm) < near_field_m * 1000.0:
                    mount_points += 1
                    continue
            except (TypeError, ValueError):
                pass
        points.append((x, y, z, row.get("range_source") or ""))

    if not points:
        result = {"cell_m": cell_m, "eps_m": eps_m, "point_count": 0,
                  "mount_points": mount_points, "mount_boxes": 0,
                  "boxes": [], "grid": [],
                  "occluded_deg": [[-effective_fov_deg, effective_fov_deg]],
                  "fov_limit_deg": effective_fov_deg,
                  "yaw_scale": yaw_scale,
                  "near_field_m": near_field_m,
                  "mount_guard_m": mount_guard_m,
                  "note": "No points after near-mount filtering."}
        return apply_annotations(result, annotations)

    cells = defaultdict(list)
    for point in points:
        cells[(math.floor(point[0] / cell_m), math.floor(point[1] / cell_m))].append(point)

    boxes = []
    for indices in _cluster_indices(points, eps_m):
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
    for start in range(-fov_int, fov_int, bin_size):
        count = 0
        for x, y, z, source in points:
            yaw = math.degrees(math.atan2(y, x))
            if start <= yaw < start + bin_size:
                count += 1
        if count < 2:
            occluded.append([start, start + bin_size])
    result = {
        "cell_m": cell_m,
        "eps_m": eps_m,
        "point_count": len(points),
        "mount_points": mount_points,
        "mount_boxes": mount_boxes,
        "boxes": boxes,
        "grid": grid,
        "occluded_deg": occluded,
        "fov_limit_deg": effective_fov_deg,
        "yaw_scale": yaw_scale,
        "near_field_m": near_field_m,
        "mount_guard_m": mount_guard_m,
        "note": ("Estimated boxes from one fixed viewpoint; hidden sides are inferred. "
                 "Occluded sectors have too few returns. Near-field mount returns are hidden. "
                 "Yaw scale is provisional until a known-target calibration."),
    }
    return apply_annotations(result, annotations)
