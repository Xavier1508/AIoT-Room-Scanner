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
    if long_side >= 1.8 and short_side <= 0.9 and geometry["z_top"] >= 1.2:
        return "wall"
    if geometry["z_top"] >= 1.5 and short_side <= 0.35 and long_side >= 0.15:
        return "wall_edge"
    if geometry["z_top"] >= 1.5 and short_side <= 0.60 and long_side >= 0.80:
        return "wall"
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


def apply_annotations(result, annotations):
    """Apply manual label overrides, hidden boxes and pairwise merges."""
    annotations = annotations or {}
    labels = annotations.get("labels") or {}
    hidden = {str(item) for item in (annotations.get("hidden") or [])}
    merges = annotations.get("merges") or []
    boxes = [dict(box) for box in (result.get("boxes") or [])]
    boxes = [box for box in boxes if str(box.get("id")) not in hidden]
    for box in boxes:
        override = labels.get(str(box.get("id")))
        if override:
            box["label"] = str(override)[:24]
            box["label_source"] = "manual"
    for pair in merges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        ids = [str(pair[0]), str(pair[1])]
        selected = [box for box in boxes if str(box.get("id")) in ids]
        if len(selected) != 2:
            continue
        merged = _merge_boxes(selected)
        boxes = [box for box in boxes if str(box.get("id")) not in ids]
        boxes.append(merged)
    boxes.sort(key=lambda box: (box.get("label") not in WALL_LABELS,
                                -int(box.get("points", 0))))
    result["boxes"] = boxes
    result["annotations"] = {
        "labels": {str(key): str(value) for key, value in labels.items()},
        "hidden": sorted(hidden),
        "merges": [list(pair) for pair in merges if isinstance(pair, (list, tuple)) and len(pair) == 2],
    }
    result["annotation_count"] = len(labels) + len(hidden) + len(merges)
    return result


def reconstruct_points(rows, cell_m=0.10, eps_m=0.45, min_points=5,
                       near_field_m=0.40, mount_guard_m=0.75,
                       mount_guard_z_m=0.72, fov_limit_deg=60,
                       annotations=None):
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
                  "mount_points": mount_points, "boxes": [], "grid": [],
                  "occluded_deg": [[-fov_limit_deg, fov_limit_deg]],
                  "fov_limit_deg": fov_limit_deg,
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
    grid = [[cell[0], cell[1], len(cells[cell])] for cell in sorted(cells)]
    occluded = []
    bin_size = 10
    for start in range(-fov_limit_deg, fov_limit_deg, bin_size):
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
        "boxes": boxes,
        "grid": grid,
        "occluded_deg": occluded,
        "fov_limit_deg": fov_limit_deg,
        "near_field_m": near_field_m,
        "mount_guard_m": mount_guard_m,
        "note": ("Estimated boxes from one fixed viewpoint; hidden sides are inferred. "
                 "Occluded sectors have too few returns. Near-field mount returns are hidden."),
    }
    return apply_annotations(result, annotations)
