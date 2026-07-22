#!/usr/bin/env python3
# gen_sfx.py — synthesises the six sequence transition sounds as premium, designed SFX
# (time-varying resonant band-pass on shaped noise + tonal layers + clean envelopes).
# Not cheap beeps: each has attack/decay shaping, a pitch/formant sweep matched to the
# motion, and a soft tail. 48 kHz stereo 16-bit WAV -> motion/public/sfx/<key>.wav.
import wave, struct, math, sys
import numpy as np

FS = 48000
rng = np.random.default_rng(20260722)


def svf_bandpass(x, fc, Q):
    """Chamberlin state-variable filter, band-pass out. fc may be an array (per-sample)."""
    n = len(x)
    fc = np.broadcast_to(np.asarray(fc, dtype=np.float64), (n,))
    f = 2.0 * np.sin(np.pi * np.clip(fc, 20, FS / 6) / FS)
    q = 1.0 / max(Q, 0.5)
    low = band = 0.0
    out = np.empty(n)
    for i in range(n):
        high = x[i] - low - q * band
        band = band + f[i] * high
        low = low + f[i] * band
        out[i] = band
    return out


def env(n, attack, release, hold=0.0, curve=2.0):
    """Attack (linear-ish) -> hold -> exponential release, length n samples."""
    a = max(1, int(attack * FS))
    h = int(hold * FS)
    r = max(1, n - a - h)
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a) ** 0.6
    tail = np.linspace(0, 1, r)
    e[a + h:a + h + r] = np.exp(-curve * 3.0 * tail)
    if a + h + r < n:
        e[a + h + r:] = 0.0
    return e[:n]


def norm(x, peak_db=-3.0):
    x = x - np.mean(x)
    m = np.max(np.abs(x)) or 1.0
    return x / m * (10 ** (peak_db / 20.0))


def fade_edges(x, ms=1.5):
    k = int(ms / 1000 * FS)
    if k * 2 < len(x):
        x[:k] *= np.linspace(0, 1, k)
        x[-k:] *= np.linspace(1, 0, k)
    return x


def whoosh(dur=0.42, f0=380, f1=3400, f2=850, Q=3.2, peak=-3.5, hp=True):
    n = int(dur * FS)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    # center frequency: rise fast to f1 then fall to f2 (the "wsh")
    up = f0 + (f1 - f0) * np.sin(np.clip(t / 0.42, 0, 1) * math.pi / 2)
    down = f1 + (f2 - f1) * np.clip((t - 0.42) / 0.58, 0, 1)
    fc = np.where(t < 0.42, up, down)
    bp = svf_bandpass(noise, fc, Q)
    e = env(n, 0.012, dur, hold=0.02, curve=2.2)
    body = bp * e
    if hp:  # remove low rumble
        body = body - svf_bandpass(body, 180, 0.7) * 0.0  # (bp already high-ish)
    # subtle airy top layer
    top = svf_bandpass(noise, np.clip(fc * 1.8, 20, FS / 6), 2.0) * env(n, 0.02, dur, curve=2.6) * 0.35
    return norm(fade_edges(body + top), peak)


def swish(dur=0.38):
    n = int(dur * FS)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    fc = 520 + 1400 * np.sin(np.clip(t / 0.5, 0, 1) * math.pi / 2) - 900 * np.clip((t - 0.5) / 0.5, 0, 1)
    bp = svf_bandpass(noise, np.clip(fc, 120, 6000), 1.8)
    e = env(n, 0.03, dur, curve=2.4)
    return norm(fade_edges(bp * e), -6.0)


def airy(dur=0.55):
    n = int(dur * FS)
    noise = rng.standard_normal(n)
    hp = svf_bandpass(noise, 2600, 0.8)          # high, breathy
    hp = hp - svf_bandpass(hp, 2600, 0.8) * 0.0
    e = env(n, 0.06, dur, curve=1.6)
    return norm(fade_edges(hp * e), -11.0)


def whoosh2(dur=0.5):
    # airier 3D swoosh: doppler-ish bend + width
    base = whoosh(dur=dur, f0=300, f1=2200, f2=700, Q=2.2, peak=-5.0)
    n = len(base)
    t = np.linspace(0, 1, n)
    # add a faint pitched shimmer bending down (doppler tail)
    fsh = 1400 * np.exp(-2.5 * t)
    shimmer = np.sin(2 * math.pi * np.cumsum(fsh) / FS) * np.exp(-4 * t) * 0.12
    return norm(fade_edges(base + shimmer), -5.0)


def click(dur=0.06):
    n = int(dur * FS)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    burst = svf_bandpass(noise, 3200, 1.2) * np.exp(-t * 60)     # tight transient
    tick = np.sin(2 * math.pi * 2600 * (t * dur)) * np.exp(-t * 55) * 0.5
    return norm(fade_edges(burst + tick, ms=0.5), -6.0)


def pop(dur=0.22):
    n = int(dur * FS)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    trans = svf_bandpass(noise, 2400, 1.0) * np.exp(-t * 90) * 0.5   # attack chirp
    fpop = 880 * np.exp(-t * 14) + 150                              # pitch drop -> body
    tone = np.sin(2 * math.pi * np.cumsum(fpop) / FS) * np.exp(-t * 9)
    return norm(fade_edges(trans + tone, ms=1.0), -3.5)


def stereo(mono, spread=0.02):
    n = len(mono)
    d = max(1, int(spread / 1000 * FS))  # tiny inter-channel delay for width
    left = mono.copy()
    right = np.concatenate([np.zeros(d), mono])[:n]
    # slight decorrelation
    return np.stack([left, 0.98 * right], axis=1)


def write_wav(path, stereo_arr):
    a = np.clip(stereo_arr, -1, 1)
    pcm = (a * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(pcm.tobytes())


SOUNDS = {
    'whoosh': whoosh,     # whip pan
    'whoosh2': whoosh2,   # 3D swoosh
    'swish': swish,       # glass slide
    'airy': airy,         # blur zoom
    'click': click,       # push
    'pop': pop,           # iris / app open
}

if __name__ == '__main__':
    outdir = sys.argv[1]
    for name, fn in SOUNDS.items():
        mono = fn()
        write_wav(f'{outdir}/{name}.wav', stereo(mono))
        print(f'{name}.wav  {len(mono)/FS*1000:.0f}ms  peak {20*math.log10(max(np.max(np.abs(mono)),1e-6)):.1f}dBFS')
    print('done')
