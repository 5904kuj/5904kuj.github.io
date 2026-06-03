"""Procedurally generated sound effects (no asset files needed)."""
import numpy as np
import pygame

SR = 44100


def _to_sound(wave):
    wave = np.clip(wave, -1, 1)
    audio = (wave * 32767).astype(np.int16)
    stereo = np.column_stack((audio, audio))
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def _env(n, attack=0.01, release=0.2):
    t = np.linspace(0, 1, n)
    a = int(n * attack)
    r = int(n * release)
    env = np.ones(n)
    if a > 0:
        env[:a] = np.linspace(0, 1, a)
    if r > 0:
        env[-r:] = np.linspace(1, 0, r)
    return env


def _swish(dur=0.18, f0=1800, f1=400):
    n = int(SR * dur)
    t = np.linspace(0, dur, n)
    freq = np.linspace(f0, f1, n)
    phase = np.cumsum(2 * np.pi * freq / SR)
    noise = np.random.uniform(-1, 1, n) * 0.5
    tone = np.sin(phase) * 0.5
    return (tone + noise) * _env(n, 0.005, 0.5) * 0.6


def _blip(freq=880, dur=0.12):
    n = int(SR * dur)
    t = np.linspace(0, dur, n)
    w = np.sin(2 * np.pi * freq * t) * _env(n, 0.01, 0.6)
    return w * 0.5


def _boom(dur=0.6):
    n = int(SR * dur)
    t = np.linspace(0, dur, n)
    freq = np.linspace(180, 40, n)
    phase = np.cumsum(2 * np.pi * freq / SR)
    tone = np.sin(phase)
    noise = np.random.uniform(-1, 1, n)
    w = (tone * 0.7 + noise * 0.5) * _env(n, 0.001, 0.7)
    return w * 0.8


class Audio:
    def __init__(self):
        try:
            pygame.mixer.init(frequency=SR, size=-16, channels=2, buffer=512)
            self.ok = True
        except Exception:
            self.ok = False
            return
        self.slice = [_to_sound(_swish(f0=f, f1=f * 0.25))
                      for f in (1600, 1900, 2200)]
        # rising combo blips for combo escalation
        self.combo = [_to_sound(_blip(440 * (2 ** (i / 12.0)))) for i in range(12)]
        self.bomb = _to_sound(_boom())
        self.frenzy = _to_sound(_swish(dur=0.4, f0=2400, f1=1600))

    def play_slice(self, intensity=0.5):
        if not self.ok:
            return
        idx = min(len(self.slice) - 1, int(intensity * len(self.slice)))
        self.slice[idx].play()

    def play_combo(self, n):
        if not self.ok:
            return
        self.combo[min(len(self.combo) - 1, n)].play()

    def play_bomb(self):
        if self.ok:
            self.bomb.play()

    def play_frenzy(self):
        if self.ok:
            self.frenzy.play()
