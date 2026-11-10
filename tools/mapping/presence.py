#!/usr/bin/env python3
"""Rule-based HLK-LD2410C presence tracker.

The tracker is deliberately conservative: a target must be valid, in range,
above the energy threshold and confirmed for several frames before it is
reported as a human presence. The result is a rule baseline, not a trained
classifier; the dashboard labels it as such.
"""
from __future__ import annotations

import time
from collections import deque


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class PresenceTracker:
    def __init__(self, confirm_frames=3, hold_s=6.0, min_cm=30.0,
                 max_cm=600.0, energy_threshold=40.0, history_limit=120):
        self.confirm_frames = max(1, int(confirm_frames))
        self.hold_s = max(0.0, float(hold_s))
        self.min_cm = float(min_cm)
        self.max_cm = float(max_cm)
        self.energy_threshold = float(energy_threshold)
        self._history = deque(maxlen=max(10, int(history_limit)))
        self._state = "empty"
        self._confidence = 0.0
        self._confirm = 0
        self._last_seen = None
        self._last_reason = "waiting"
        self._last_distance = None
        self._last_energy = None
        self._last_target = None

    def _decay(self, now, reason):
        self._confirm = max(0, self._confirm - 1)
        if (self._state in ("present", "holding") and self._last_seen is not None
                and now - self._last_seen <= self.hold_s):
            self._state = "holding"
            remaining = 1.0 - (now - self._last_seen) / self.hold_s
            self._confidence = max(0.10, 0.55 * remaining)
            self._last_reason = "holding"
        else:
            self._state = "empty"
            self._confidence = 0.0
            self._last_reason = reason

    def update(self, hlk, now=None, scanning=False):
        now = time.monotonic() if now is None else float(now)
        hlk = hlk or {}
        valid = bool(hlk.get("valid"))
        stale = bool(hlk.get("stale"))
        distance = _number(hlk.get("distance_cm"))
        energy = _number(hlk.get("energy"))
        target = _number(hlk.get("target_state"))
        moving_energy = _number(hlk.get("moving_energy"))
        stationary_energy = _number(hlk.get("stationary_energy"))
        self._last_distance = distance
        self._last_energy = energy
        self._last_target = target

        if scanning:
            self._confirm = 0
            self._state = "scanning"
            self._confidence = 0.0
            self._last_reason = "scan_mode"
        elif not valid:
            self._decay(now, "hlk_invalid")
        elif stale:
            self._decay(now, "hlk_stale")
        elif distance is None or distance < self.min_cm or distance > self.max_cm:
            self._decay(now, "out_of_range")
        elif energy is None or energy < self.energy_threshold or not target:
            self._decay(now, "below_threshold")
        else:
            self._confirm += 1
            self._last_seen = now
            if self._confirm >= self.confirm_frames:
                self._state = "present"
                self._confidence = min(
                    0.99,
                    0.55 + 0.08 * min(self._confirm, 5)
                    + 0.15 * min(1.0, energy / 150.0),
                )
                self._last_reason = ("moving_target" if target in (1, 3)
                                     else "stationary_target")
            else:
                self._state = "confirming"
                self._confidence = min(0.50, 0.15 + 0.10 * self._confirm)
                self._last_reason = "confirming"

        self._history.append({
            "t": round(now, 3),
            "distance_cm": round(distance, 1) if distance is not None else None,
            "energy": int(energy) if energy is not None else None,
            "moving_energy": int(moving_energy) if moving_energy is not None else None,
            "stationary_energy": int(stationary_energy) if stationary_energy is not None else None,
            "state": self._state,
            "confidence": round(self._confidence, 3),
        })
        return self.snapshot()

    def snapshot(self):
        presence_class = ("human" if self._state in ("present", "holding")
                          else "unknown" if self._state in ("confirming", "scanning")
                          else "empty")
        return {
            "state": self._state,
            "class": presence_class,
            "confidence": round(self._confidence, 3),
            "distance_cm": (round(self._last_distance, 1)
                            if self._last_distance is not None else None),
            "energy": (int(self._last_energy)
                       if self._last_energy is not None else None),
            "target_state": (int(self._last_target)
                             if self._last_target is not None else None),
            "confirm_frames": self._confirm,
            "confirm_required": self.confirm_frames,
            "reason": self._last_reason,
            "hold_s": self.hold_s,
            "rule": ("HLK valid, target>0, energy>=40, "
                     "30<=distance<=600 cm, 3 frames"),
            "model": "rule baseline (DL not deployed)",
            "history": list(self._history),
        }

    def reset(self):
        self._history.clear()
        self._state = "empty"
        self._confidence = 0.0
        self._confirm = 0
        self._last_seen = None
        self._last_reason = "waiting"
        self._last_distance = None
        self._last_energy = None
        self._last_target = None
