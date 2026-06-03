"""Fruit, bomb and special entities with simple projectile physics."""
import math
import random

import config as C

FRUIT, BOMB, FRENZY, CRIT = "fruit", "bomb", "frenzy", "crit"


class Entity:
    __slots__ = ("x", "y", "vx", "vy", "radius", "kind", "color", "name",
                 "alive", "sliced", "spin", "angle", "is_crit")

    def __init__(self, x, y, vx, vy, kind, color, name, radius, is_crit=False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        self.kind = kind
        self.color = color
        self.name = name
        self.alive = True
        self.sliced = False
        self.is_crit = is_crit
        self.spin = random.uniform(-2.0, 2.0)
        self.angle = 0.0

    def update(self, dt):
        self.vy += C.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        # Off the bottom of the screen -> gone
        if self.y - self.radius > C.HEIGHT and self.vy > 0:
            self.alive = False

    def missed(self):
        """True if it fell off-screen without being sliced (costs a life if fruit)."""
        return (not self.sliced) and (self.y - self.radius > C.HEIGHT) and self.vy > 0


class Half:
    """A sliced fruit half flying apart."""
    __slots__ = ("x", "y", "vx", "vy", "radius", "color", "angle", "spin", "life", "side")

    def __init__(self, x, y, vx, vy, color, radius, side):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.radius = radius
        self.angle = 0.0
        self.spin = random.uniform(-C.HALF_SPIN, C.HALF_SPIN)
        self.life = 2.0
        self.side = side  # -1 left half, +1 right half

    def update(self, dt):
        self.vy += C.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.life -= dt

    @property
    def alive(self):
        return self.life > 0 and self.y - self.radius < C.HEIGHT + 80


def make_fruit(name=None, is_crit=False):
    if name is None:
        name = random.choice(list(C.FRUIT_TYPES.keys()))
    color = C.FRUIT_TYPES[name]
    x = random.uniform(C.WIDTH * 0.15, C.WIDTH * 0.85)
    vx = random.uniform(-C.LAUNCH_VX_RANGE, C.LAUNCH_VX_RANGE)
    # nudge horizontal velocity toward screen center so it stays in view
    vx += (C.WIDTH * 0.5 - x) * 0.6
    vy = random.uniform(C.LAUNCH_VY_MAX, C.LAUNCH_VY_MIN)
    kind = CRIT if is_crit else FRUIT
    return Entity(x, C.SPAWN_Y, vx, vy, kind, color, name, C.FRUIT_RADIUS, is_crit)


def make_bomb():
    x = random.uniform(C.WIDTH * 0.15, C.WIDTH * 0.85)
    vx = random.uniform(-C.LAUNCH_VX_RANGE, C.LAUNCH_VX_RANGE)
    vx += (C.WIDTH * 0.5 - x) * 0.6
    vy = random.uniform(C.LAUNCH_VY_MAX, C.LAUNCH_VY_MIN)
    return Entity(x, C.SPAWN_Y, vx, vy, BOMB, (0.1, 0.1, 0.12), "bomb", C.BOMB_RADIUS)


def make_frenzy():
    x = random.uniform(C.WIDTH * 0.2, C.WIDTH * 0.8)
    vx = (C.WIDTH * 0.5 - x) * 0.6
    vy = random.uniform(C.LAUNCH_VY_MAX, C.LAUNCH_VY_MIN)
    return Entity(x, C.SPAWN_Y, vx, vy, FRENZY, (1.0, 0.85, 0.1), "frenzy", C.FRUIT_RADIUS)


def make_arc_cluster(n):
    """A row of fruits along an arc -> naturally invites a one-swipe combo."""
    cx = random.uniform(C.WIDTH * 0.3, C.WIDTH * 0.7)
    spread = random.uniform(120, 220)
    base_vy = random.uniform(C.LAUNCH_VY_MAX, C.LAUNCH_VY_MIN)
    out = []
    for i in range(n):
        t = (i / max(1, n - 1)) - 0.5  # -0.5..0.5
        x = cx + t * spread * 2
        vx = t * 380 + (C.WIDTH * 0.5 - x) * 0.3
        e = make_fruit()
        e.x = x
        e.vx = vx
        e.vy = base_vy + abs(t) * 120
        out.append(e)
    return out


def split_halves(e):
    """Produce two halves from a sliced fruit, flying apart sideways."""
    left = Half(e.x, e.y, e.vx - 220, e.vy - 120, e.color, e.radius, -1)
    right = Half(e.x, e.y, e.vx + 220, e.vy - 120, e.color, e.radius, +1)
    return [left, right]
