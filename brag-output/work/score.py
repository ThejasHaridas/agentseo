"""The /brag soundtrack: 8 bars at 96 BPM in A minor (exactly 20.0 s), music and effects on one grid."""
import numpy as np

SR = 48000
BPM = 96
BEAT = 60 / BPM          # 0.625 s
BAR = 4 * BEAT           # 2.5 s
TOTAL = 8 * BAR          # 20.0 s
N = int(TOTAL * SR)
rng = np.random.default_rng(11)
L = np.zeros(N)
R = np.zeros(N)


def add(sig, t0, gain=1.0, pan=0.0):
    i0 = int(round(t0 * SR))
    if i0 < 0:
        sig, i0 = sig[-i0:], 0
    sig = sig[: N - i0]
    L[i0:i0 + len(sig)] += sig * gain * np.sqrt(0.5 * (1 - pan))
    R[i0:i0 + len(sig)] += sig * gain * np.sqrt(0.5 * (1 + pan))


def hz(m):
    return 440 * 2 ** ((m - 69) / 12)


def tt(d):
    return np.arange(int(d * SR)) / SR


def saw(f, t, h=10, det=0.0):
    return sum(np.sin(2 * np.pi * f * k * (1 + det) * t) / k for k in range(1, h + 1))


def smooth(x, n):
    return np.convolve(x, np.ones(n) / n, mode="same")


def noise(d, dark=24):
    """Noise darkened by a moving average: soft, never hiss."""
    return smooth(rng.standard_normal(int(d * SR)), dark)


# Am, F, C, G, Am: one chord per bar from bar 4
CH = {0: [45, 52, 57, 60], 1: [41, 48, 53, 57], 2: [48, 55, 60, 64], 3: [43, 50, 55, 59]}

# --- drone under everything, swelling into the reveal ---------------------------
t = tt(TOTAL)
drone = (saw(hz(33), t, 6) * 0.6 + saw(hz(40), t, 4) * 0.35) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.2 * t) ** 2)
env = np.interp(t, [0, 0.4, 4.9, 5.0, 7.5, 17.4, 17.5, 19.4, 20], [0, 0.35, 0.6, 0.9, 0.45, 0.6, 1.0, 0.4, 0])
add(drone * env, 0, 0.05)


# --- sub hits, impacts and braams ---------------------------------------------------
def sub(t0, g=1.0, dur=1.6):
    x = tt(dur)
    f = 28 + 52 * np.exp(-x * 9)
    add(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 2.4), t0, 0.5 * g)


def impact(t0, g=1.0):
    sub(t0, 1.2 * g, 3.0)
    x = tt(1.2)
    add(noise(1.2, 6) * np.exp(-x * 7), t0, 0.16 * g, -0.2)
    add(noise(1.2, 6) * np.exp(-x * 7), t0, 0.16 * g, 0.2)


def braam(t0, notes, dur=2.4, g=1.0):
    x = tt(dur)
    e = np.minimum(1, x / 0.06) * np.exp(-x * 0.9) * np.minimum(1, (dur - x) / 0.4)
    bright = np.interp(x, [0, 0.3, dur], [14, 8, 3])
    for m in notes:
        for det, p in ((-0.003, -0.5), (0.003, 0.5)):
            s = sum(np.sin(2 * np.pi * hz(m) * k * (1 + det) * x) / k * np.clip(bright - k + 1, 0, 1) for k in range(1, 15))
            add(s * e, t0, 0.2 * g / len(notes) * 2, p)


sub(0.0, 0.55)
sub(BAR, 0.5)
impact(2 * BAR)
braam(2 * BAR, [33, 45, 52, 57, 60])
impact(7 * BAR, 1.1)
braam(7 * BAR, [33, 45, 52, 57, 64], dur=2.5, g=1.1)

# --- ticking eighths in the hook and the problem ---------------------------------
for k in range(int(2 * BAR / (BEAT / 2))):
    x = tt(0.04)
    add(smooth(rng.standard_normal(len(x)), 2) * np.exp(-x * 160), k * BEAT / 2, 0.03 if k % 2 == 0 else 0.018, 0.35 if k % 2 else -0.35)


# --- risers: noise opening up, a rising tone ----------------------------------------
def riser(t0, t1, g=1.0):
    d = t1 - t0
    x = tt(d)
    k = x / d
    dark, bright = noise(d, 40), noise(d, 4)
    sweep = np.sin(2 * np.pi * np.cumsum(150 + 650 * k ** 2) / SR)
    add((dark * (1 - k) + bright * k) * k ** 2.2 * 0.5 + sweep * k ** 3 * 0.05, t0, g)


riser(BAR, 2 * BAR, 0.6)
riser(6 * BAR, 7 * BAR, 0.8)


# --- whoosh into each wipe (wipes end on the bar line) -------------------------------
def whoosh(t_end, g=1.0):
    d = 0.55
    x = tt(d)
    k = x / d
    add((noise(d, 30) * (1 - k) + noise(d, 8) * k) * np.sin(np.pi * k) ** 2, t_end - d + 0.05, 0.22 * g)


for b in (1, 3, 4, 5, 6):
    whoosh(b * BAR, 0.8)


# --- the driving section, bars 4 to 7 ------------------------------------------------
def tom(t0, f0=96, g=1.0):
    x = tt(0.5)
    f = f0 * (0.65 + 0.35 * np.exp(-x * 18))
    add(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 7), t0, 0.33 * g)


def snare(t0, g=1.0):
    x = tt(0.3)
    add((noise(0.3, 3) * 0.6 + np.sin(2 * np.pi * 190 * x) * 0.4) * np.exp(-x * 16), t0, 0.12 * g, 0.1)


def pluck(m, g=1.0, pan=0.0, d=0.22):
    x = tt(d)
    return saw(hz(m), x, 6) * np.exp(-x * 16) * g


for bar in range(3, 7):
    t0 = bar * BAR
    chord = CH[(bar - 3) % 4]
    for b in range(4):
        tom(t0 + b * BEAT, 90 if b % 2 == 0 else 70, 1.0 if b % 2 == 0 else 0.7)
        if b in (1, 3):
            snare(t0 + b * BEAT, 0.9)
    # tom fill on the last beat of each bar, leading into the cut
    for s in range(4):
        tom(t0 + 3 * BEAT + s * BEAT / 4, 110 - s * 8, 0.35 + 0.1 * s)
    # sixteenth ostinato over the chord, an octave higher in the last bar
    pat = [0, 2, 3, 2, 1, 2, 3, 2]
    up = 12 if bar == 6 else 0
    for s in range(16):
        m = chord[pat[s % 8]] + 12 + up
        add(pluck(m), t0 + s * BEAT / 4, 0.05, -0.3 if s % 2 else 0.3)
    # low bass on the chord root, eighths
    for e in range(8):
        x = tt(BEAT / 2)
        add(np.sin(2 * np.pi * hz(chord[0] - 12) * x) * np.exp(-x * 5), t0 + e * BEAT / 2, 0.2)

# soft clicks under the agent's cursor in the "It tests" scene, on the beats
for b in range(1, 4):
    x = tt(0.05)
    add(np.sin(2 * np.pi * 1760 * x) * np.exp(-x * 120), 4 * BAR + b * BEAT - BEAT / 2, 0.05, 0.2)

# a high pad that opens in the outro
x = tt(BAR)
pad = sum(np.sin(2 * np.pi * hz(m) * x) for m in (69, 72, 76)) * np.minimum(1, x / 0.8) * np.minimum(1, (BAR - x) / 1.2)
add(pad, 7 * BAR, 0.025)


# --- one room for everything: a short convolution reverb ------------------------------
def reverb(x, secs=1.8, wet=0.22):
    n = int(secs * SR)
    ir = smooth(rng.standard_normal(n), 3) * np.exp(-np.arange(n) / SR * 3.6)
    ir /= np.sqrt((ir ** 2).sum())
    m = len(x) + n
    nf = 1 << (m - 1).bit_length()
    return x + wet * np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[: len(x)]


L, R = reverb(L), reverb(R)
fade = np.clip((TOTAL - np.arange(N) / SR) / 0.6, 0, 1)
mix = np.stack([L, R]) * fade
mix /= np.abs(mix).max() * 1.1
mix.T.astype(np.float32).tofile("score.f32")
print("bars", TOTAL / BAR, "seconds", TOTAL)
