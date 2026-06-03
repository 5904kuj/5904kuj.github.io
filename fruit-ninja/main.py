"""FRUIT FRENZY - full-body / hand interactive fruit-slicing game.

Run:  .venv/Scripts/python.exe main.py
Controls: swing your hand(s) in front of the webcam to slice.
          SPACE skip/start, R restart, ESC quit.
"""
import math
import sys
import time

import pygame
import moderngl

import config as C
import entities as E
from tracking import Tracker
from blade import Blade, seg_circle_hit
from spawner import Spawner
from scoring import Scoring
from effects import Effects
from render_gl import Renderer
from audio import Audio

MENU, TUTORIAL, PLAY, GAMEOVER = range(4)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.set_mode((C.WIDTH, C.HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
        pygame.display.set_caption(C.TITLE)
        self.ctx = moderngl.create_context()
        self.renderer = Renderer(self.ctx)
        self.audio = Audio()
        self.tracker = Tracker()
        self.tracker.start()
        self.clock = pygame.time.Clock()
        self.blades = [Blade() for _ in range(C.NUM_HANDS)]
        self.state = MENU
        self.best_score = 0
        self.frame = None
        self._reset_play()
        # tutorial state
        self.tut_step = 0
        self.tut_timer = 0.0
        self.tut_hint = ""

    def _reset_play(self):
        self.spawner = Spawner()
        self.scoring = Scoring()
        self.effects = Effects()
        self.entities = []
        self.halves = []
        self.lives = C.MAX_LIVES
        self.play_time = 0.0

    # ---------------- slicing ----------------
    def _do_slicing(self, kill_on_bomb=True):
        """Test each blade against entities; returns True if a bomb was hit."""
        bomb_hit = False
        for b in self.blades:
            seg = b.slice_segment()
            if seg is None:
                continue
            p0, p1 = seg
            group = []
            for e in self.entities:
                if e.sliced or not e.alive:
                    continue
                if seg_circle_hit(p0, p1, e.x, e.y, e.radius):
                    if e.kind == E.BOMB:
                        e.sliced = True
                        e.alive = False
                        self.effects.bomb_burst(e.x, e.y)
                        self.audio.play_bomb()
                        if kill_on_bomb:
                            bomb_hit = True
                        continue
                    e.sliced = True
                    e.alive = False
                    self.halves.extend(E.split_halves(e))
                    swing = (p1[0] - p0[0], p1[1] - p0[1])
                    self.effects.juice_burst(e.x, e.y, e.color, b.intensity, swing)
                    if e.kind == E.FRENZY:
                        self.spawner.trigger_frenzy()
                        self.effects.add_flash(0.5)
                        self.audio.play_frenzy()
                    group.append(e)
            if group:
                gained, n = self.scoring.register_cut(group)
                self.audio.play_slice(b.intensity)
                # juicy feedback scaled by swing speed and combo size
                self.effects.add_shake(8 + b.intensity * 14 + n * 3)
                if n >= 3:
                    self.effects.trigger_slowmo()
                    self.effects.add_flash(0.35)
                    self.audio.play_combo(n)
        return bomb_hit

    # ---------------- update ----------------
    def update(self, dt_real):
        self.frame = self.tracker.get_frame()
        hands = self.tracker.get_hands()
        for b, (pos, vel) in zip(self.blades, hands):
            b.update(pos, vel)

        ts = self.effects.time_scale
        dt = dt_real * ts

        if self.state == MENU:
            # start when a fast swing is detected or SPACE pressed
            if any(b.active for b in self.blades):
                self._start_tutorial()
        elif self.state == TUTORIAL:
            self._update_tutorial(dt, dt_real)
        elif self.state == PLAY:
            self._update_play(dt, dt_real)
        elif self.state == GAMEOVER:
            self.effects.update(dt, dt_real)

    def _start_tutorial(self):
        self.state = TUTORIAL
        self.tut_step = 0
        self.tut_timer = 0.0
        self.tut_hint = ""
        self.entities = []
        self.halves = []
        self.effects = Effects()

    def _start_play(self):
        self.state = PLAY
        self._reset_play()

    def _step_entities(self, dt):
        for e in self.entities:
            e.update(dt)
        for h in self.halves:
            h.update(dt)
        self.halves = [h for h in self.halves if h.alive]

    def _update_play(self, dt, dt_real):
        self.play_time += dt
        self.entities.extend(self.spawner.update(dt))
        self._step_entities(dt)
        bomb = self._do_slicing(kill_on_bomb=True)
        # life loss for missed fruit
        for e in self.entities:
            if e.kind in (E.FRUIT, E.CRIT) and e.missed():
                self.lives -= 1
                self.effects.add_shake(10)
        self.entities = [e for e in self.entities if e.alive]
        self.scoring.update(dt)
        self.effects.update(dt, dt_real)
        if bomb or self.lives <= 0:
            self._game_over()

    def _game_over(self):
        self.best_score = max(self.best_score, self.scoring.score)
        self.effects.add_flash(0.8)
        self.effects.add_shake(C.SHAKE_MAX)
        self.state = GAMEOVER

    # ---------------- tutorial ----------------
    def _update_tutorial(self, dt, dt_real):
        self.tut_timer += dt_real
        self._step_entities(dt)
        self.scoring.update(dt)

        step = self.tut_step
        if step == 0:
            self.tut_hint = "손을 화면에 비춰보세요"
            if any(b.pos is not None for b in self.blades) and self.tut_timer > 1.0:
                self._next_tut()
        elif step == 1:
            self.tut_hint = "강하게 휘둘러 잘라!"
            self._ensure_tut_fruit()
            cut = self._tut_slice()
            if cut:
                self._next_tut()
        elif step == 2:
            self.tut_hint = "천천히 움직이면 베이지 않아요 — 빠르게 휘둘러야 잘립니다!"
            self._ensure_tut_fruit()
            # show a sub-hint if the hand passes over a fruit too slowly
            self._slow_pass_hint()
            if self._tut_slice():
                self._next_tut()
        elif step == 3:
            self.tut_hint = "폭탄은 베지 마세요!"
            if not any(e.kind == E.BOMB for e in self.entities):
                self.entities.append(E.make_bomb())
            self._do_slicing(kill_on_bomb=False)  # bombs harmless in tutorial
            self.entities = [e for e in self.entities if e.alive]
            if self.tut_timer > 3.0:
                self._next_tut()
        elif step == 4:
            self.tut_hint = "콤보! 한 번에 여러 개를 베면 점수 폭발"
            if len([e for e in self.entities if e.kind in (E.FRUIT, E.CRIT)]) < 3:
                self.entities.extend(E.make_arc_cluster(4))
            n = self._tut_slice_count()
            if n >= 2 or self.tut_timer > 7.0:
                self._start_play()
        # respawn safety: keep tutorial fruit alive
        self.entities = [e for e in self.entities if e.alive]
        self.effects.update(dt, dt_real)

    def _next_tut(self):
        self.tut_step += 1
        self.tut_timer = 0.0
        self.tut_hint = ""
        self.entities = []

    def _ensure_tut_fruit(self):
        live = [e for e in self.entities if e.kind in (E.FRUIT, E.CRIT) and e.alive]
        if not live:
            f = E.make_fruit()
            f.vy = -1200.0  # gentle lob so it lingers on screen
            self.entities.append(f)

    def _slow_pass_hint(self):
        for b in self.blades:
            if b.pos is None:
                continue
            for e in self.entities:
                if e.kind in (E.FRUIT, E.CRIT):
                    d = math.hypot(b.pos[0] - e.x, b.pos[1] - e.y)
                    if d < e.radius and not b.active:
                        self.tut_hint = "더 빠르게 휘둘러!"
                        return

    def _tut_slice(self):
        before = self.scoring.score
        self._do_slicing(kill_on_bomb=False)
        self.entities = [e for e in self.entities if e.alive]
        return self.scoring.score > before

    def _tut_slice_count(self):
        before = self.scoring.best_combo
        self._do_slicing(kill_on_bomb=False)
        self.entities = [e for e in self.entities if e.alive]
        return self.scoring.best_combo if self.scoring.best_combo > before else 0

    # ---------------- render ----------------
    def render(self):
        r = self.renderer
        r.begin_scene()
        r.draw_webcam(self.frame)
        # halves (behind fruit)
        for h in self.halves:
            a = max(0.0, min(1.0, h.life))
            col = tuple(c * a for c in h.color)
            r.draw_sprite(h.x, h.y, h.radius, col, "fruit", h.angle, half_side=h.side)
        # entities
        for e in self.entities:
            r.draw_sprite(e.x, e.y, e.radius, e.color, e.kind, e.angle)
        # trails on top
        r.draw_trails(self.blades)
        r.draw_particles(self.effects.particles)

        r.postprocess(self.effects.flash, (self.effects.shake_dx, self.effects.shake_dy))

        # ---- HUD / text overlays (drawn after bloom) ----
        if self.state == PLAY:
            r.draw_text(f"{self.scoring.score}", 30, 20, 56, (1, 1, 0.3), center=False)
            r.draw_text("♥ " * max(0, self.lives), C.WIDTH - 230, 24, 40,
                        (1, 0.3, 0.3), center=False)
            if self.scoring.combo >= 2:
                r.draw_text(f"COMBO x{self.scoring.combo}", C.WIDTH // 2, 60, 48,
                            (1, 0.85, 0.2))
            if self.spawner.frenzy_timer > 0:
                r.draw_text("FRENZY!", C.WIDTH // 2, 130, 60, (1, 0.5, 0.1))
        for p in self.scoring.popups:
            sz = int(28 * p.scale * (1.0 + 0.6 * (1 - p.life / p.max_life)))
            r.draw_text(p.text, p.x, p.y, max(18, sz), p.color)

        if self.state == MENU:
            r.draw_text(C.TITLE, C.WIDTH // 2, 200, 96, (1, 0.9, 0.2))
            r.draw_text("손을 빠르게 휘둘러 시작하세요", C.WIDTH // 2, 360, 44, (1, 1, 1))
            r.draw_text("강하게 휘둘러야 과일이 잘립니다!", C.WIDTH // 2, 430, 32,
                        (0.8, 0.9, 1))
            if self.best_score:
                r.draw_text(f"BEST  {self.best_score}", C.WIDTH // 2, 520, 36,
                            (1, 0.8, 0.3))
        elif self.state == TUTORIAL:
            r.draw_text(self.tut_hint, C.WIDTH // 2, C.HEIGHT - 90, 46, (1, 1, 0.4))
            r.draw_text(f"튜토리얼  {self.tut_step + 1}/5  (SPACE 건너뛰기)",
                        C.WIDTH // 2, 40, 28, (0.8, 0.8, 0.8))
        elif self.state == GAMEOVER:
            r.draw_text("GAME OVER", C.WIDTH // 2, 230, 90, (1, 0.3, 0.3))
            r.draw_text(f"SCORE  {self.scoring.score}", C.WIDTH // 2, 350, 56, (1, 1, 1))
            r.draw_text(f"BEST  {self.best_score}", C.WIDTH // 2, 420, 40, (1, 0.8, 0.3))
            r.draw_text("R 다시하기   ESC 종료", C.WIDTH // 2, 510, 36, (0.9, 0.9, 0.9))

        pygame.display.flip()

    # ---------------- loop ----------------
    def run(self):
        running = True
        while running:
            dt_real = min(0.05, self.clock.tick(C.FPS) / 1000.0)
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_SPACE:
                        if self.state == MENU:
                            self._start_tutorial()
                        elif self.state == TUTORIAL:
                            self._start_play()
                    elif ev.key == pygame.K_r and self.state == GAMEOVER:
                        self.state = MENU
            self.update(dt_real)
            self.render()
        self.tracker.stop()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
