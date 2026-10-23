"""Vertical cut soundtrack: 20 bars at 96 BPM in A minor (exactly 50.0 s), music and effects on one grid."""
import numpy as np

SR = 48000
BEAT = 60 / 96
BAR = 4 * BEAT
NB = 20
TOTAL = NB * BAR
N = int(TOTAL * SR)
rng = np.random.default_rng(23)
L = np.zeros(N)
R = np.zeros(N)
B = lambda n: n * BAR  # start of bar n (0-based)


def add(sig, t0, gain=1.0, pan=0.0):
    i0 = int(round(t0 * SR))
    sig = sig[: max(0, N - i0)]
    L[i0:i0 + len(sig)] += sig * gain * np.sqrt(0.5 * (1 - pan))
    R[i0:i0 + len(sig)] += sig * gain * np.sqrt(0.5 * (1 + pan))


hz = lambda m: 440 * 2 ** ((m - 69) / 12)
tt = lambda d: np.arange(int(d * SR)) / SR
smooth = lambda x, n: np.convolve(x, np.ones(n) / n, mode="same")
noise = lambda d, dark=24: smooth(rng.standard_normal(int(d * SR)), dark)


def saw(f, t, h=10, det=0.0):
    return sum(np.sin(2 * np.pi * f * k * (1 + det) * t) / k for k in range(1, h + 1))


CH = [[45, 52, 57, 60], [41, 48, 53, 57], [48, 55, 60, 64], [43, 50, 55, 59]]  # Am F C G
chord = lambda bar: CH[bar % 4]

# ---- drone, shaped across the whole piece ----------------------------------------------
t = tt(TOTAL)
drone = saw(hz(33), t, 6) * 0.6 + saw(hz(40), t, 4) * 0.35
env = np.interp(t, [0, 0.5, B(2), B(5), B(6), B(8), B(12), B(12) + 0.1, B(13) - 0.1, B(13), B(17), B(19), TOTAL - 0.3, TOTAL],
                   [0, 0.35, 0.45, 0.55, 0.9, 0.45, 0.4, 0.12, 0.12, 0.7, 0.5, 1.0, 0.3, 0])
add(drone * env * (0.6 + 0.4 * np.sin(2 * np.pi * 0.2 * t) ** 2), 0, 0.05)


def sub(t0, g=1.0, dur=1.6):
    x = tt(dur)
    add(np.sin(2 * np.pi * np.cumsum(28 + 52 * np.exp(-x * 9)) / SR) * np.exp(-x * 2.4), t0, 0.5 * g)


def impact(t0, g=1.0):
    sub(t0, 1.2 * g, 3.0)
    x = tt(1.2)
    for p in (-0.2, 0.2):
        add(noise(1.2, 6) * np.exp(-x * 7), t0, 0.16 * g, p)


def braam(t0, notes, dur=2.5, g=1.0):
    x = tt(dur)
    e = np.minimum(1, x / 0.06) * np.exp(-x * 0.9) * np.minimum(1, (dur - x) / 0.4)
    bright = np.interp(x, [0, 0.3, dur], [14, 8, 3])
    for m in notes:
        for det, p in ((-0.003, -0.5), (0.003, 0.5)):
            s = sum(np.sin(2 * np.pi * hz(m) * k * (1 + det) * x) / k * np.clip(bright - k + 1, 0, 1) for k in range(1, 15))
            add(s * e, t0, 0.4 * g / len(notes), p)


def riser(t0, t1, g=1.0):
    d = t1 - t0
    x = tt(d)
    k = x / d
    sweep = np.sin(2 * np.pi * np.cumsum(150 + 650 * k ** 2) / SR)
    add((noise(d, 40) * (1 - k) + noise(d, 4) * k) * k ** 2.2 * 0.5 + sweep * k ** 3 * 0.05, t0, g)


def whoosh(t_end, g=1.0):
    d = 0.55
    x = tt(d)
    k = x / d
    add((noise(d, 30) * (1 - k) + noise(d, 8) * k) * np.sin(np.pi * k) ** 2, t_end - d + 0.05, 0.2 * g)


def tick(t0, g=1.0, pan=0.0):
    x = tt(0.04)
    add(smooth(rng.standard_normal(len(x)), 2) * np.exp(-x * 160), t0, 0.03 * g, pan)


def tom(t0, f0=96, g=1.0):
    x = tt(0.5)
    add(np.sin(2 * np.pi * np.cumsum(f0 * (0.65 + 0.35 * np.exp(-x * 18))) / SR) * np.exp(-x * 7), t0, 0.33 * g)


def snare(t0, g=1.0):
    x = tt(0.3)
    add((noise(0.3, 3) * 0.6 + np.sin(2 * np.pi * 190 * x) * 0.4) * np.exp(-x * 16), t0, 0.12 * g, 0.1)


def pluck(m, d=0.22):
    x = tt(d)
    return saw(hz(m), x, 6) * np.exp(-x * 16)


def click(t0, f=1760, g=1.0):
    x = tt(0.05)
    add(np.sin(2 * np.pi * f * x) * np.exp(-x * 120), t0, 0.05 * g, 0.2)


def drive(bar, intensity=1.0, octave=0, fill=True):
    t0 = B(bar)
    c = chord(bar)
    for b in range(4):
        tom(t0 + b * BEAT, 90 if b % 2 == 0 else 70, (1.0 if b % 2 == 0 else 0.7) * intensity)
        if b in (1, 3):
            snare(t0 + b * BEAT, 0.9 * intensity)
    if fill:
        for s in range(4):
            tom(t0 + 3 * BEAT + s * BEAT / 4, 110 - s * 8, (0.35 + 0.1 * s) * intensity)
    pat = [0, 2, 3, 2, 1, 2, 3, 2]
    for s in range(16):
        add(pluck(c[pat[s % 8]] + 12 + octave), t0 + s * BEAT / 4, 0.05, -0.3 if s % 2 else 0.3)
    for e in range(8):
        x = tt(BEAT / 2)
        add(np.sin(2 * np.pi * hz(c[0] - 12) * x) * np.exp(-x * 5), t0 + e * BEAT / 2, 0.2)


def pad(bar, bars=1, g=1.0, notes=None):
    x = tt(bars * BAR)
    ns = notes or [m + 12 for m in chord(bar)[1:]]
    s = sum(np.sin(2 * np.pi * hz(m) * x) for m in ns)
    add(s * np.minimum(1, x / 0.6) * np.minimum(1, (bars * BAR - x) / 0.8), B(bar), 0.03 * g)


# bars 1-2: hook. bar 3: light pulse.
sub(B(0), 0.55); sub(B(1), 0.5)
for k in range(int(3 * BAR / (BEAT / 2))):
    tick(k * BEAT / 2, 1.0 if k % 2 == 0 else 0.6, 0.35 if k % 2 else -0.35)
for b in (0, 2):
    tom(B(2) + b * BEAT, 80, 0.75)
whoosh(B(2), 0.7)

# bars 4-5: problem; pulse plus a low, quiet ostinato
whoosh(B(3), 0.8)
for bar in (3, 4):
    for b in range(4):
        tom(B(bar) + b * BEAT, 80, 0.5 if b % 2 == 0 else 0.3)
    for s in range(8):
        add(pluck(chord(bar)[[0, 2, 1, 2][s % 4]], 0.3), B(bar) + s * BEAT / 2, 0.04, -0.2 if s % 2 else 0.2)
    pad(bar, 1, 0.6)

# bar 6: stakes; riser and a snare roll into the drop
riser(B(5), B(6), 0.6)
for s in range(16):
    if s >= 8 or s % 2 == 0:
        snare(B(5) + s * BEAT / 4, 0.25 + 0.5 * s / 16)

# bars 7-8: reveal
impact(B(6)); braam(B(6), [33, 45, 52, 57, 60])
pad(7, 1, 1.2)
for b in (0, 2):
    tom(B(7) + b * BEAT, 80, 0.5)
whoosh(B(8), 0.8)

# bars 9-12: drive (reads, tests)
for bar in (8, 9, 10, 11):
    drive(bar, 1.0, 0, fill=bar in (9, 11))
whoosh(B(10), 0.8); whoosh(B(12), 0.8)
for c_t in (B(10) + 1.5 * BEAT, B(10) + 3 * BEAT, B(10) + 4.5 * BEAT):
    click(c_t)

# bar 13: safe; everything stops dead on the bar line
sub(B(12), 0.35, 1.0)
pad(12, 1, 0.7, [69, 72, 76])
for k in range(8):
    tick(B(12) + k * BEAT / 2, 0.5, 0.3 if k % 2 else -0.3)

# bars 14-17: drive again (asks, fixes)
whoosh(B(13), 0.9)
for bar in (13, 14, 15, 16):
    drive(bar, 1.0, 0, fill=bar in (14, 16))
whoosh(B(15), 0.8); whoosh(B(17), 0.8)

# bars 18-19: features; the lift, toggle clicks every two beats, riser into the outro
for bar in (17, 18):
    drive(bar, 0.9, 12, fill=False)
for i in range(4):
    click(B(17) + i * 2 * BEAT, 1320, 1.2)
riser(B(18), B(19), 0.7)

# bar 20: outro
impact(B(19), 1.1); braam(B(19), [33, 45, 52, 57, 64], 2.5, 1.1)
pad(19, 1, 1.0, [69, 72, 76])


def reverb(x, secs=1.8, wet=0.22):
    n = int(secs * SR)
    ir = smooth(rng.standard_normal(n), 3) * np.exp(-np.arange(n) / SR * 3.6)
    ir /= np.sqrt((ir ** 2).sum())
    nf = 1 << (len(x) + n - 1).bit_length()
    return x + wet * np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[: len(x)]


L, R = reverb(L), reverb(R)
mix = np.stack([L, R]) * np.clip((TOTAL - np.arange(N) / SR) / 0.6, 0, 1)
mix /= np.abs(mix).max() * 1.1
mix.T.astype(np.float32).tofile("score_vertical.f32")
print("bars", TOTAL / BAR, "seconds", TOTAL)
