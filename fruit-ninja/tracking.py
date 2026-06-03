"""Webcam + MediaPipe hand tracking on a background thread (Tasks API).

mediapipe 0.10+ removed mp.solutions; uses HandLandmarker Tasks API instead.
VIDEO mode gives synchronous per-frame results without a callback.
"""
import math
import os
import threading
import time
import urllib.request

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

import config as C

MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)


def _ensure_model():
    if not os.path.exists(MODEL_PATH):
        print("MediaPipe 모델 다운로드 중…")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("완료")


class OneEuro:
    def __init__(self, min_cutoff, beta, dcutoff):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.x_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x
        dt = max(1e-3, t - self.t_prev)
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.dcutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat


class HandState:
    def __init__(self):
        self.fx = OneEuro(C.OE_MIN_CUTOFF, C.OE_BETA, C.OE_DCUTOFF)
        self.fy = OneEuro(C.OE_MIN_CUTOFF, C.OE_BETA, C.OE_DCUTOFF)
        self.pos = None
        self.vel = (0.0, 0.0)
        self.last_t = None
        self.last_pos = None

    def update(self, x, y, t):
        sx = self.fx(x, t)
        sy = self.fy(y, t)
        if self.last_pos is not None and self.last_t is not None:
            dt = max(1e-3, t - self.last_t)
            self.vel = ((sx - self.last_pos[0]) / dt,
                        (sy - self.last_pos[1]) / dt)
        self.last_pos = (sx, sy)
        self.last_t = t
        self.pos = (sx, sy)

    def lost(self):
        self.pos = None
        self.vel = (0.0, 0.0)
        self.last_pos = None
        self.last_t = None


class Tracker:
    def __init__(self):
        _ensure_model()
        self._lock = threading.Lock()
        self._hands = [HandState() for _ in range(C.NUM_HANDS)]
        self._frame = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self):
        options = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=C.NUM_HANDS,
            min_hand_detection_confidence=C.TRACK_MIN_DET_CONF,
            min_hand_presence_confidence=C.TRACK_MIN_TRACK_CONF,
            min_tracking_confidence=C.TRACK_MIN_TRACK_CONF,
        )
        cap = cv2.VideoCapture(C.CAM_INDEX, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, C.CAM_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, C.CAM_H)

        with mp_vision.HandLandmarker.create_from_options(options) as landmarker:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.005)
                    continue
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                t = time.perf_counter()
                ts_ms = int(t * 1000)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(mp_img, ts_ms)

                seen = [False] * C.NUM_HANDS
                if result.hand_landmarks:
                    for i, lm_list in enumerate(result.hand_landmarks[: C.NUM_HANDS]):
                        tip = lm_list[8]  # index fingertip
                        x = tip.x * C.WIDTH
                        y = tip.y * C.HEIGHT
                        with self._lock:
                            self._hands[i].update(x, y, t)
                        seen[i] = True
                for i in range(C.NUM_HANDS):
                    if not seen[i]:
                        with self._lock:
                            self._hands[i].lost()

                with self._lock:
                    self._frame = rgb

        cap.release()

    def get_hands(self):
        with self._lock:
            return [(h.pos, h.vel) for h in self._hands]

    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()
