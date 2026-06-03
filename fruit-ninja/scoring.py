"""Score, combo chaining and flashy score popups."""
import random

import config as C


class Popup:
    __slots__ = ("x", "y", "text", "color", "life", "max_life", "scale", "vy")

    def __init__(self, x, y, text, color, scale):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.scale = scale
        self.life = 0.9
        self.max_life = 0.9
        self.vy = -60.0

    def update(self, dt):
        self.life -= dt
        self.y += self.vy * dt
        self.vy *= 0.92

    @property
    def alive(self):
        return self.life > 0

    @property
    def t(self):
        """0..1 progress."""
        return 1.0 - self.life / self.max_life


class Scoring:
    def __init__(self):
        self.score = 0
        self.popups = []
        self._combo_timer = 0.0
        self._combo_count = 0
        self.best_combo = 0

    def update(self, dt):
        if self._combo_timer > 0:
            self._combo_timer -= dt
            if self._combo_timer <= 0:
                self._combo_count = 0
        for p in self.popups:
            p.update(dt)
        self.popups = [p for p in self.popups if p.alive]

    def register_cut(self, entities):
        """entities: list of sliced Entity objects cut by ONE swing this frame.

        Returns (gained, combo_count) for callers that drive extra juice.
        """
        if not entities:
            return 0, 0
        n = len(entities)
        # chain into the running combo window
        self._combo_count += n
        self._combo_timer = C.COMBO_WINDOW
        self.best_combo = max(self.best_combo, self._combo_count)

        gained = 0
        for e in entities:
            base = C.SCORE_PER_FRUIT
            if e.is_crit:
                base *= C.CRIT_MULT
            gained += base
        # multi-cut bonus
        if n > 1:
            gained += n * C.COMBO_BONUS_PER

        self.score += gained

        # popup at the centroid of the cut group
        cx = sum(e.x for e in entities) / n
        cy = sum(e.y for e in entities) / n
        if n > 1:
            scale = min(3.2, 1.2 + n * 0.45)
            color = (1.0, 0.9, 0.2)
            self.popups.append(Popup(cx, cy, f"COMBO x{n}!  +{gained}", color, scale))
        else:
            e = entities[0]
            if e.is_crit:
                self.popups.append(Popup(cx, cy, f"CRITICAL! +{gained}",
                                         (1.0, 0.3, 0.9), 2.2))
            else:
                self.popups.append(Popup(cx, cy, f"+{gained}", (1.0, 1.0, 1.0), 1.0))
        return gained, n

    @property
    def combo(self):
        return self._combo_count if self._combo_timer > 0 else 0
