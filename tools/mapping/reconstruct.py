#!/usr/bin/env python3
"""Reconstruct a top-down occupancy grid and estimated solid boxes.

This is a 2.5D reconstruction from one fixed scanner viewpoint: near-mount
returns are removed, points are clustered in the x/y plane, each cluster is
fitted with an oriented rectangle, and the rectangle is extruded from the floor
to the observed top. It is an estimate, not a full mesh; hidden sides are
inferred.
"""
from __future__ import annotations

import math
from collections import defaultdict


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


def reconstruct_points(rows, cell_m=0.10, eps_m=0.45, min_points=5):
    points = []
    for row in rows:
        try:
            x = float(row.get("x_mm")) / 1000.0
            y = float(row.get("y_mm")) / 1000.0
            z = float(row.get("z_mm")) / 1000.0
        except (TypeError, ValueError):
            continue
        if abs(x) > 20 or abs(y) > 20 or z < -1.0 or z > 5.0:
            continue
        # The scanner mount/arm is a near-field return, not the room.
        if math.hypot(x, y) < 0.30:
            continue
        range_mm = row.get("range_mm")
        if range_mm is not None:
            try:
                if float(range_mm) < 300:
                    continue
            except (TypeError, ValueError):
                pass
        points.append((x, y, z, row.get("range_source") or ""))

    if not points:
        return {"cell_m": cell_m, "eps_m": eps_m, "point_count": 0,
                "boxes": [], "grid": [],
                "note": "No points after near-mount filtering."}

    cells = defaultdict(list)
    for point in points:
        cells[(math.floor(point[0] / cell_m), math.floor(point[1] / cell_m))].append(point)

    boxes = []
    for indices in _cluster_indices(points, eps_m):
        if len(indices) < min_points:
            continue
        cluster = [points[index] for index in indices]
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
        long_side, short_side = max(length, width), min(length, width)
        label = "wall" if long_side >= 1.8 and short_side <= 0.9 and z_top >= 1.2 else "object"
        boxes.append({
            "label": label,
            "cx_m": round(cx, 3),
            "cy_m": round(cy, 3),
            "angle_deg": round(math.degrees(angle), 1),
            "length_m": round(length, 3),
            "width_m": round(width, 3),
            "z_bottom_m": 0.0,
            "z_top_m": round(z_top, 3),
            "points": len(cluster),
            "range_x_m": [round(min(xs), 3), round(max(xs), 3)],
            "range_y_m": [round(min(ys), 3), round(max(ys), 3)],
        })
    boxes.sort(key=lambda box: (box["label"] != "wall", -box["points"]))
    grid = [[cell[0], cell[1], len(cells[cell])] for cell in sorted(cells)]
    return {
        "cell_m": cell_m,
        "eps_m": eps_m,
        "point_count": len(points),
        "boxes": boxes,
        "grid": grid,
        "note": "Estimated boxes from one fixed viewpoint; hidden sides are inferred.",
    }
