"""Spawn director: encodes the Fruit-Ninja difficulty curve and rhythm.

Ramps spawn frequency + burst size over time, injects periodic peak waves
(dense clusters + bombs) followed by breathers, and handles frenzy storms.
"""
import random

import config as C
import entities as E


def _lerp(a, b, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return a + (b - a) * t


class Spawner:
    def __init__(self):
        self.t = 0.0
        self._next = 0.6
        self.frenzy_timer = 0.0
        self._frenzy_next = 0.0

    def _ramp(self):
        return self.t / C.RAMP_TIME

    def _in_peak(self):
        phase = self.t % C.PEAK_PERIOD
        return phase < C.PEAK_DURATION

    def trigger_frenzy(self):
        self.frenzy_timer = C.FRENZY_DURATION
        self._frenzy_next = 0.0

    def update(self, dt):
        """Return a list of newly spawned entities for this frame."""
        self.t += dt
        out = []

        # --- frenzy storm: rapid fruit-only bursts, no bombs ---
        if self.frenzy_timer > 0:
            self.frenzy_timer -= dt
            self._frenzy_next -= dt
            if self._frenzy_next <= 0:
                self._frenzy_next = C.FRENZY_INTERVAL
                for _ in range(random.randint(2, 4)):
                    out.append(E.make_fruit())
            return out

        self._next -= dt
        if self._next > 0:
            return out

        ramp = self._ramp()
        interval = _lerp(C.SPAWN_INTERVAL_START, C.SPAWN_INTERVAL_END, ramp)
        peak = self._in_peak()
        if peak:
            interval *= 0.55
        self._next = interval * random.uniform(0.8, 1.2)

        burst_max = int(round(_lerp(C.BURST_MAX_START, C.BURST_MAX_END, ramp)))
        if peak:
            burst_max += C.PEAK_BURST_BONUS
        n = random.randint(C.BURST_MIN_START, max(C.BURST_MIN_START, burst_max))

        # Occasionally launch a clean arc cluster to invite a one-swipe combo.
        if n >= 3 and random.random() < 0.5:
            out.extend(E.make_arc_cluster(n))
        else:
            for _ in range(n):
                r = random.random()
                if r < C.FRENZY_CHANCE:
                    out.append(E.make_frenzy())
                elif r < C.FRENZY_CHANCE + C.CRIT_CHANCE:
                    out.append(E.make_fruit(is_crit=True))
                else:
                    out.append(E.make_fruit())

        # Bombs: hidden inside the action, denser during peaks.
        bomb_chance = C.BOMB_CHANCE_PEAK if peak else C.BOMB_CHANCE
        if random.random() < bomb_chance:
            out.append(E.make_bomb())
        return out
