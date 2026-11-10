#!/usr/bin/env python3
"""Rule-based HLK-LD2410C presence tracker.

The tracker is deliberately conservative: a target must be valid, in range,
above the energy threshold and confirmed for several frames before it is
reported as a human presence. It also gates the HLK distance against the
current ToF/HC wall distance so a person behind the sensor/wall (a common
false positive) does not produce a human capsule. The result is a rule
baseline, not a trained classifier; the dashboard labels it as such.
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
                 max_cm=600.0, energy_threshold=40.0, history_limit=120,
                 beyond_margin_cm=50.0, no_target_hold_s=2.5,
                 distance_spread_cm=20.0):
        self.confirm_frames = max(1, int(confirm_frames))
        self.hold_s = max(0.0, float(hold_s))
        self.min_cm = float(min_cm)
        self.max_cm = float(max_cm)
        self.energy_threshold = float(energy_threshold)
        self.beyond_margin_cm = max(0.0, float(beyond_margin_cm))
        self.no_target_hold_s = max(0.0, float(no_target_hold_s))
        self.distance_spread_cm = max(1.0, float(distance_spread_cm))
        self._history = deque(maxlen=max(10, int(history_limit)))
        self._distance_history = deque(maxlen=5)
        self._state = "empty"
        self._confidence = 0.0
        self._confirm = 0
        self._last_seen = None
        self._last_reason = "waiting"
        self._last_gate = "waiting"
        self._last_distance = None
        self._last_energy = None
        self._last_target = None
        self._last_max_range = None
        self._last_spread = None

    def _decay(self, now, reason, hold_s=None):
        hold = self.hold_s if hold_s is None else max(0.0, float(hold_s))
        self._confirm = max(0, self._confirm - 1)
        self._last_gate = reason
        if (self._state in ("present", "holding") and self._last_seen is not None
                and now - self._last_seen <= hold):
            self._state = "holding"
            remaining = 1.0 - (now - self._last_seen) / hold if hold > 0 else 0.0
            self._confidence = max(0.10, 0.55 * remaining)
            self._last_reason = "holding"
        else:
            self._state = "empty"
            self._confidence = 0.0
            self._last_reason = reason

    def update(self, hlk, now=None, scanning=False, max_range_cm=None):
        now = time.monotonic() if now is None else float(now)
        hlk = hlk or {}
        valid = bool(hlk.get("valid"))
        stale = bool(hlk.get("stale"))
        distance = _number(hlk.get("distance_cm"))
        energy = _number(hlk.get("energy"))
        target = _number(hlk.get("target_state"))
        moving_energy = _number(hlk.get("moving_energy"))
        stationary_energy = _number(hlk.get("stationary_energy"))
        max_range = _number(max_range_cm)
        self._last_distance = distance
        self._last_energy = energy
        self._last_target = target
        self._last_max_range = max_range
        self._last_spread = None

        if scanning:
            self._confirm = 0
            self._state = "scanning"
            self._confidence = 0.0
            self._last_reason = "scan_mode"
            self._last_gate = "scan_mode"
        elif not valid:
            self._decay(now, "hlk_invalid")
        elif stale:
            self._decay(now, "hlk_stale")
        elif distance is None or distance < self.min_cm or distance > self.max_cm:
            self._decay(now, "out_of_range")
        elif max_range is not None and distance > max_range + self.beyond_margin_cm:
            # HLK sees through/behind the wall. Clear immediately; a hold here
            # would keep a ghost human capsule after the person leaves.
            self._confirm = 0
            self._state = "empty"
            self._confidence = 0.0
            self._last_seen = None
            self._last_reason = "beyond_wall"
            self._last_gate = "beyond_wall"
        elif energy is None or energy < self.energy_threshold:
            self._decay(now, "below_threshold")
        elif not target:
            self._decay(now, "no_target", hold_s=self.no_target_hold_s)
        else:
            self._distance_history.append(distance)
            if len(self._distance_history) >= 3:
                spread = max(self._distance_history) - min(self._distance_history)
                self._last_spread = round(spread, 1)
                if spread > self.distance_spread_cm:
                    self._decay(now, "distance_unstable",
                                hold_s=self.no_target_hold_s)
                    self._history.append({
                        "t": round(now, 3),
                        "distance_cm": round(distance, 1),
                        "energy": int(energy) if energy is not None else None,
                        "moving_energy": int(moving_energy) if moving_energy is not None else None,
                        "stationary_energy": int(stationary_energy) if stationary_energy is not None else None,
                        "state": self._state,
                        "confidence": round(self._confidence, 3),
                    })
                    return self.snapshot()
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
                self._last_gate = "ok"
            else:
                self._state = "confirming"
                self._confidence = min(0.50, 0.15 + 0.10 * self._confirm)
                self._last_reason = "confirming"
                self._last_gate = "confirming"

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
            "gate": self._last_gate,
            "max_range_cm": (round(self._last_max_range, 1)
                             if self._last_max_range is not None else None),
            "distance_spread_cm": self._last_spread,
            "beyond_margin_cm": self.beyond_margin_cm,
            "hold_s": self.hold_s,
            "no_target_hold_s": self.no_target_hold_s,
            "rule": ("HLK valid, target>0, energy>=40, 30<=distance<=600 cm, "
                     "3 frames, distance<=wall+50 cm"),
            "model": "rule baseline (DL not deployed)",
            "history": list(self._history),
        }

    def reset(self):
        self._history.clear()
        self._distance_history.clear()
        self._state = "empty"
        self._confidence = 0.0
        self._confirm = 0
        self._last_seen = None
        self._last_reason = "waiting"
        self._last_gate = "waiting"
        self._last_distance = None
        self._last_energy = None
        self._last_target = None
        self._last_max_range = None
        self._last_spread = None
