"""Synthesize an original soundtrack for the timeline and mix it under the voiceover."""
import json, subprocess
import numpy as np

SR = 44100
tl = json.load(open("timeline.json"))
TOTAL = tl["total"]
BPM = tl["bpm"]
BEAT = 60 / BPM
BAR = 4 * BEAT
N = int(TOTAL * SR)
rng = np.random.default_rng(7)

L = np.zeros(N)
R = np.zeros(N)
lines = {l["id"]: l for l in tl["lines"]}
DROP = lines["s04"]["start"]
BREAK = lines["s11"]["start"] - 0.4
FINAL = lines["s12"]["start"]


def add(sig, t0, gain=1.0, pan=0.0):
    i0 = int(t0 * SR)
    if i0 >= N:
        return
    sig = sig[: N - i0]
    gl = gain * np.sqrt(0.5 * (1 - pan))
    gr = gain * np.sqrt(0.5 * (1 + pan))
    if i0 < 0:
        sig = sig[-i0:]
        i0 = 0
    L[i0:i0 + len(sig)] += sig * gl
    R[i0:i0 + len(sig)] += sig * gr


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def saw(f, t, harmonics=10, detune=0.0):
    out = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        out += np.sin(2 * np.pi * f * k * (1 + detune) * t) / k
    return out


def highpass_noise(n):
    x = rng.standard_normal(n)
    k = np.ones(8) / 8
    return x - np.convolve(x, k, mode="same")


# Am - F - C - G, one chord per bar
CHORDS = [
    (57, [57, 60, 64, 69], 33),
    (53, [53, 57, 60, 65], 29),
    (60, [55, 60, 64, 67], 36),
    (55, [55, 59, 62, 67], 31),
]


def chord_at(t):
    return CHORDS[int(t // BAR) % 4]


# --- pads: whole track, brighter after the drop -------------------------------
nbars = int(np.ceil(TOTAL / BAR))
for b in range(nbars):
    t0 = b * BAR
    _, notes, _ = CHORDS[b % 4]
    dur = BAR + 0.6
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(1, t / 0.8) * np.minimum(1, (dur - t) / 0.6)
    bright = 3 if t0 < DROP else (7 if t0 < BREAK else 4)
    lvl = 0.05 if t0 < 3 else 0.08
    if t0 >= DROP - 0.01 and t0 < BREAK:
        lvl = 0.07
    for j, m in enumerate(notes):
        for d, p in ((-0.004, -0.6), (0.004, 0.6)):
            add(saw(hz(m), t, bright, d) * env, t0, lvl / len(notes), p * (0.3 + 0.2 * j / 3))
    # airy fifth on top
    add(np.sin(2 * np.pi * hz(notes[-1] + 12) * t) * env * 0.5, t0, lvl * 0.15, 0)

# fade the intro in
fade = np.minimum(1, np.arange(N) / SR / 2.5)
L *= fade
R *= fade

# --- sub pulse before the drop -------------------------------------------------
for b in range(int(DROP / BEAT)):
    t0 = b * BEAT
    if t0 < 5.0:
        continue
    _, _, root = chord_at(t0)
    t = np.arange(int(0.5 * SR)) / SR
    add(np.sin(2 * np.pi * hz(root) * t) * np.exp(-t * 6), t0, 0.18)

# ticking tension hats from scene 3 to the drop
for k in range(int((DROP - 12.9) / (BEAT / 2))):
    t0 = 12.9 + k * BEAT / 2
    if t0 > lines["s03"]["start"] + lines["s03"]["dur"] + 0.3:
        break
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    add(highpass_noise(n) * np.exp(-t * 90), t0, 0.05, 0.4 if k % 2 else -0.4)

# --- riser + impact into the reveal -------------------------------------------
rs = lines["s03"]["start"] + lines["s03"]["dur"] + 0.2
rdur = DROP - rs
n = int(rdur * SR)
t = np.arange(n) / SR
x = t / rdur
noise = highpass_noise(n) * (x ** 2.5)
sweep = np.sin(2 * np.pi * (200 * t + (1200 - 200) * t * x / 2)) * x ** 3
add(noise * 0.22 + sweep * 0.05, rs)


def impact(t0, g=1.0):
    n = int(3.5 * SR)
    t = np.arange(n) / SR
    f = 30 + 70 * np.exp(-t * 8)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.4)
    burst = highpass_noise(n) * np.exp(-t * 5)
    add(boom * 0.55 * g, t0)
    add(burst * 0.12 * g, t0, 1, -0.3)
    add(burst[::-1][:n] * 0, t0)


impact(DROP)
impact(FINAL, 0.9)

# --- groove after the drop ----------------------------------------------------
def kick():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)


def clap():
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    env = np.zeros(n)
    for o in (0, 0.012, 0.024):
        env += (t >= o) * np.exp(-(t - o).clip(0) * (60 if o < 0.02 else 18))
    return highpass_noise(n) * env * 0.5


K, C = kick(), clap()
beat_i = 0
t0 = DROP
while t0 < BREAK - 0.01:
    # first two bars: kick only on 1, then four on the floor
    full = t0 >= DROP + 2 * BAR
    if full or beat_i % 4 == 0:
        add(K, t0, 0.42)
    if full and beat_i % 4 in (1, 3):
        add(C, t0, 0.16, 0.1)
    if full:
        n = int(0.06 * SR)
        tt = np.arange(n) / SR
        add(highpass_noise(n) * np.exp(-tt * 70), t0 + BEAT / 2, 0.07, 0.35)
        n = int(0.03 * SR)
        tt = np.arange(n) / SR
        add(highpass_noise(n) * np.exp(-tt * 140), t0 + BEAT / 4, 0.03, -0.35)
        add(highpass_noise(n) * np.exp(-tt * 140), t0 + 3 * BEAT / 4, 0.03, -0.35)
    # bass: 8ths, sidechained feel (rests on the beat)
    _, _, root = chord_at(t0)
    n = int(BEAT / 2 * SR)
    tt = np.arange(n) / SR
    env = np.minimum(1, tt / 0.01) * np.exp(-tt * 5)
    b = (np.sin(2 * np.pi * hz(root) * tt) + 0.3 * np.sin(2 * np.pi * hz(root) * 2 * tt)) * env
    add(b, t0 + BEAT / 2, 0.22)
    if full:
        add(b * 0.6, t0, 0.18)
    t0 += BEAT
    beat_i += 1

# --- arpeggio pluck (with a stereo echo) --------------------------------------
def pluck(f, n):
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t) + 0.1 * np.sin(2 * np.pi * 3 * f * t)) * np.exp(-t * 9)


PATTERN = [0, 2, 1, 3, 2, 1, 3, 2]
step = BEAT / 4
t0 = DROP + BAR
k = 0
while t0 < TOTAL - 3:
    _, notes, _ = chord_at(t0)
    m = notes[PATTERN[k % 8]] + 12
    g = 0.05 if t0 < BREAK else 0.035
    p = pluck(hz(m), int(0.4 * SR))
    add(p, t0, g, -0.2)
    add(p, t0 + 3 * step, g * 0.4, 0.6)
    t0 += step
    k += 1

# --- simple reverb (FFT convolution with decaying noise) ----------------------
def reverb(x, secs=2.2, wet=0.18):
    n = int(secs * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t * 3.2)
    ir /= np.sqrt((ir ** 2).sum())
    m = len(x) + n
    nfft = 1 << (m - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[: len(x)]
    return x + wet * y


L, R = reverb(L), reverb(R)

# --- voice --------------------------------------------------------------------
V = np.zeros(N)
for l in tl["lines"]:
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", f"vo/{l['id']}.wav", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    )
    v = np.frombuffer(raw, np.float32).astype(float)
    i0 = int(l["start"] * SR)
    V[i0:i0 + len(v)] += v[: N - i0]
V /= np.abs(V).max()

# ducking envelope from voice activity, smoothed (attack/release via moving average)
win = int(0.05 * SR)
act = np.sqrt(np.convolve(V ** 2, np.ones(win) / win, mode="same"))
act = (act > 0.02).astype(float)
sm = int(0.35 * SR)
act = np.convolve(act, np.ones(sm) / sm, mode="same")
duck = 1 - 0.55 * np.clip(act * 1.6, 0, 1)

music = np.stack([L, R]) * duck
music /= np.abs(music).max()
# fade out
tail = np.clip((TOTAL - np.arange(N) / SR) / 3.5, 0, 1)
music *= tail

mix = 0.42 * music + 0.85 * V
mix /= np.abs(mix).max() * 1.05
np.stack([music[0], music[1]]).T.astype(np.float32).tofile("music.f32")
mix.T.astype(np.float32).tofile("mix.f32")
print("ok", TOTAL)
