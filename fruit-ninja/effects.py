"""Particles (juice + sparks), screen shake and slow-motion state."""
import math
import random

import config as C


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "color", "life", "max_life", "size", "spark", "grav")

    def __init__(self, x, y, vx, vy, color, life, size, spark, grav):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.max_life = life
        self.size = size
        self.spark = spark
        self.grav = grav

    def update(self, dt):
        if self.grav:
            self.vy += C.GRAVITY * 0.7 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    @property
    def alive(self):
        return self.life > 0

    @property
    def alpha(self):
        return max(0.0, self.life / self.max_life)


class Effects:
    def __init__(self):
        self.particles = []
        self.shake = 0.0
        self.shake_dx = 0.0
        self.shake_dy = 0.0
        self.slowmo = 0.0   # remaining seconds of slow-mo
        self.flash = 0.0    # white/colored full-screen flash 0..1

    # ---- triggers ----
    def add_shake(self, amount):
        self.shake = min(C.SHAKE_MAX, self.shake + amount)

    def trigger_slowmo(self):
        self.slowmo = C.SLOWMO_DURATION

    def add_flash(self, amount):
        self.flash = min(1.0, self.flash + amount)

    def juice_burst(self, x, y, color, intensity, swing_dir=(0, 0)):
        n = int(C.PARTICLES_PER_SLICE * (0.6 + intensity))
        sx, sy = swing_dir
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(120, 520) * (0.7 + intensity)
            vx = math.cos(ang) * spd + sx * 0.25
            vy = math.sin(ang) * spd + sy * 0.25
            self.particles.append(Particle(
                x, y, vx, vy, color, random.uniform(0.4, 0.9),
                random.uniform(4, 11), spark=False, grav=True))
        # bright sparks along swing direction (scale with speed)
        ns = int(C.SPARK_PER_SLICE * (0.4 + intensity * 1.4))
        sdir = math.atan2(sy, sx) if (sx or sy) else random.uniform(0, math.tau)
        for _ in range(ns):
            ang = sdir + random.uniform(-0.6, 0.6)
            spd = random.uniform(400, 1100) * (0.6 + intensity)
            self.particles.append(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd,
                (1.0, 1.0, 0.85), random.uniform(0.15, 0.4),
                random.uniform(2, 5), spark=True, grav=False))

    def bomb_burst(self, x, y):
        for _ in range(70):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(200, 900)
            self.particles.append(Particle(
                x, y, math.cos(ang) * spd, math.sin(ang) * spd,
                (1.0, random.uniform(0.2, 0.6), 0.1),
                random.uniform(0.4, 1.0), random.uniform(4, 12),
                spark=False, grav=True))
        self.add_shake(C.SHAKE_MAX)
        self.add_flash(0.9)

    # ---- per-frame ----
    def update(self, dt_game, dt_real):
        # particles run on game time so they slow down during slow-mo
        for p in self.particles:
            p.update(dt_game)
        self.particles = [p for p in self.particles if p.alive]

        # shake/slowmo/flash run on real (wall-clock) time
        if self.shake > 0:
            self.shake = max(0.0, self.shake - C.SHAKE_DECAY * dt_real * (self.shake + 4))
            ang = random.uniform(0, math.tau)
            self.shake_dx = math.cos(ang) * self.shake
            self.shake_dy = math.sin(ang) * self.shake
        else:
            self.shake_dx = self.shake_dy = 0.0

        if self.slowmo > 0:
            self.slowmo -= dt_real
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt_real * 2.5)

    @property
    def time_scale(self):
        return C.SLOWMO_SCALE if self.slowmo > 0 else 1.0
