"""All tunable constants live here. Playtest by editing these values."""

# ---------- Window / display ----------
WIDTH = 1280
HEIGHT = 720
FPS = 60
TITLE = "FRUIT FRENZY"

# Webcam overlay
CAM_INDEX = 0
CAM_W = 640
CAM_H = 480
WEBCAM_DARKEN = 0.45  # 0=black bg, 1=full bright webcam. Lower = moodier, effects pop more.

# ---------- Hand tracking ----------
NUM_HANDS = 2
TRACK_MIN_DET_CONF = 0.5
TRACK_MIN_TRACK_CONF = 0.5
# One-Euro filter params (low-latency smoothing)
OE_MIN_CUTOFF = 1.7
OE_BETA = 0.012
OE_DCUTOFF = 1.0

# ---------- Blade / slicing ----------
TRAIL_LEN = 18            # how many recent points form the blade trail
TRAIL_BASE_WIDTH = 10.0   # px, base half-width of trail
TRAIL_MAX_WIDTH = 46.0    # px, half-width at max swing speed (BIG trails)
SLICE_MIN_SPEED = 900.0   # px/sec. Below this you CANNOT cut. Forces a real swing.
SPEED_MAX = 4200.0        # px/sec mapped to max effect intensity
TRAIL_FADE = 0.82         # per-frame alpha decay of trail points

# ---------- Physics ----------
GRAVITY = 1700.0          # px/sec^2
SPAWN_Y = HEIGHT + 60     # spawn just below screen
LAUNCH_VY_MIN = -1500.0
LAUNCH_VY_MAX = -1850.0
LAUNCH_VX_RANGE = 420.0

# ---------- Fruit ----------
FRUIT_RADIUS = 52
BOMB_RADIUS = 50
HALF_SPIN = 6.0           # rad/sec spin of cut halves

# ---------- Scoring ----------
SCORE_PER_FRUIT = 1
COMBO_WINDOW = 0.45       # sec; fruits cut within this window chain a combo
COMBO_BONUS_PER = 1       # extra points per fruit in a multi-cut
CRIT_CHANCE = 0.10
CRIT_MULT = 3

# ---------- Lives ----------
MAX_LIVES = 3

# ---------- Effects ----------
SHAKE_MAX = 26.0          # px max screen shake amplitude
SHAKE_DECAY = 6.0         # per-sec decay
SLOWMO_SCALE = 0.30       # time scale during slow-mo
SLOWMO_DURATION = 0.45    # sec
PARTICLES_PER_SLICE = 22
SPARK_PER_SLICE = 14
BLOOM_THRESHOLD = 0.62
BLOOM_INTENSITY = 1.5

# ---------- Spawn director (difficulty curve) ----------
# Spawn interval (sec) interpolates from START to END over RAMP_TIME seconds.
SPAWN_INTERVAL_START = 1.25
SPAWN_INTERVAL_END = 0.55
RAMP_TIME = 60.0
# Simultaneous fruits per spawn grows over time.
BURST_MIN_START = 1
BURST_MAX_START = 2
BURST_MAX_END = 5
# Peak wave: every PEAK_PERIOD sec, a dense cluster + bombs, then a breather.
PEAK_PERIOD = 22.0
PEAK_DURATION = 8.0
PEAK_BURST_BONUS = 3
BOMB_CHANCE = 0.12
BOMB_CHANCE_PEAK = 0.22
# Frenzy banana: rare special that triggers a spawn storm.
FRENZY_CHANCE = 0.006
FRENZY_DURATION = 5.0
FRENZY_INTERVAL = 0.18

# ---------- Colors (R,G,B 0-1) for procedural fruits ----------
FRUIT_TYPES = {
    "watermelon": (0.20, 0.85, 0.30),
    "orange":     (1.00, 0.55, 0.10),
    "apple":      (0.95, 0.18, 0.22),
    "lemon":      (1.00, 0.90, 0.15),
    "grape":      (0.62, 0.30, 0.85),
    "blueberry":  (0.25, 0.45, 1.00),
}
