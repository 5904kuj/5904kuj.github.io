"""Blade trails (one per hand) and segment-vs-circle slice detection.

Effect intensity scales with swing speed: faster swings make the trail bigger
and brighter and produce stronger shake/particles (handled by callers reading
`intensity`).
"""
import math
from collections import deque

import config as C


def _clamp01(v):
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def seg_circle_hit(p0, p1, cx, cy, r):
    """True if segment p0->p1 intersects circle (cx,cy,r)."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    seg_len2 = dx * dx + dy * dy
    if seg_len2 < 1e-6:
        return (x0 - cx) ** 2 + (y0 - cy) ** 2 <= r * r
    t = ((cx - x0) * dx + (cy - y0) * dy) / seg_len2
    t = _clamp01(t)
    px, py = x0 + t * dx, y0 + t * dy
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


class Blade:
    """Tracks one hand's recent positions and current swing intensity."""

    def __init__(self):
        self.points = deque(maxlen=C.TRAIL_LEN)  # list of (x, y, intensity)
        self.pos = None
        self.prev_pos = None
        self.speed = 0.0
        self.intensity = 0.0
        self.active = False  # True only when swinging fast enough to cut

    def update(self, pos, vel):
        if pos is None:
            self.prev_pos = None
            self.pos = None
            self.active = False
            # let the trail fade out naturally
            if self.points:
                self.points.popleft()
            return
        self.prev_pos = self.pos
        self.pos = pos
        self.speed = math.hypot(vel[0], vel[1])
        self.intensity = _clamp01(self.speed / C.SPEED_MAX)
        self.active = self.speed >= C.SLICE_MIN_SPEED
        self.points.append((pos[0], pos[1], self.intensity))

    def slice_segment(self):
        """The segment to test for cuts this frame, or None."""
        if self.pos is None or self.prev_pos is None or not self.active:
            return None
        return (self.prev_pos, self.pos)

    def trail_points(self):
        return list(self.points)
