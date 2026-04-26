#!/usr/bin/env python3
"""Robot-beep sound effects for Claude Code hooks.

Usage:
  friend.py <kind> [--force]   play a sound; <kind> in:
                               chirp working excited alarm greeting done question
  friend.py on                 enable sounds
  friend.py off                disable sounds
  friend.py status             show current state
  friend.py test               play one of each (sequentially)
"""
import math
import os
import random
import shlex
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

HOME = Path.home()
PLUGIN_DIR = HOME / ".claude" / "friend"
DISABLED_FLAG = PLUGIN_DIR / "disabled"
STATE_FILE = PLUGIN_DIR / "state"
RATE = 22050

MIN_INTERVAL = {
    "chirp": 10.0,
    "working": 6.0,
    "excited": 0.0,
    "alarm": 3.0,
    "greeting": 0.0,
    "done": 0.0,
    "question": 0.0,
}


def is_enabled():
    if os.environ.get("FRIEND_OFF"):
        return False
    return not DISABLED_FLAG.exists()


def read_last_ts():
    try:
        return float(STATE_FILE.read_text().strip())
    except Exception:
        return 0.0


def write_last_ts(ts):
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(f"{ts}")


def should_play(kind, force):
    if not is_enabled():
        return False
    if force:
        return True
    interval = MIN_INTERVAL.get(kind, 5.0)
    if interval <= 0:
        return True
    return (time.time() - read_last_ts()) >= interval


# ---------------- synthesis ----------------

def _envelope(n, attack=0.015, release=0.035):
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    out = [1.0] * n
    for i in range(min(a, n)):
        out[i] = i / a
    for i in range(min(r, n)):
        out[n - 1 - i] = min(out[n - 1 - i], i / r)
    return out


def syllable(duration, f_start, f_end, vibrato_hz=0.0, vibrato_depth=0.0, wave_type="sine"):
    """One swept-tone 'syllable' with optional vibrato."""
    n = max(1, int(duration * RATE))
    env = _envelope(n)
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / RATE
        f = f_start * (f_end / f_start) ** (i / max(1, n - 1))
        if vibrato_hz > 0:
            f *= 1.0 + vibrato_depth * math.sin(2 * math.pi * vibrato_hz * t)
        phase += 2 * math.pi * f / RATE
        if wave_type == "square":
            s = 0.55 if math.sin(phase) >= 0 else -0.55
        elif wave_type == "triangle":
            s = (2 / math.pi) * math.asin(math.sin(phase))
        else:
            s = math.sin(phase)
        out[i] = s * env[i]
    return out


def silence(duration):
    return [0.0] * max(0, int(duration * RATE))


def join(*parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


# ---------------- presets ----------------

def make_chirp():
    f0 = random.uniform(600, 900)
    f1 = f0 * random.uniform(1.4, 2.2)
    return syllable(random.uniform(0.10, 0.16), f0, f1, vibrato_hz=18, vibrato_depth=0.05)


def make_working():
    parts = []
    for _ in range(random.randint(2, 3)):
        f0 = random.uniform(400, 1100)
        f1 = f0 * random.choice([0.6, 1.5, 1.8])
        parts.append(syllable(
            random.uniform(0.08, 0.14), f0, f1,
            vibrato_hz=random.uniform(15, 30), vibrato_depth=0.07,
        ))
        parts.append(silence(random.uniform(0.02, 0.05)))
    return join(*parts)


def make_excited():
    parts = []
    base = random.uniform(500, 700)
    for i in range(random.randint(3, 4)):
        f0 = base * (1.2 ** i)
        f1 = f0 * random.uniform(1.3, 1.7)
        parts.append(syllable(0.09, f0, f1, vibrato_hz=22, vibrato_depth=0.08))
        parts.append(silence(0.02))
    return join(*parts)


def make_alarm():
    parts = []
    f = random.uniform(800, 1000)
    for _ in range(3):
        parts.append(syllable(0.16, f, f * 0.55, vibrato_hz=10, vibrato_depth=0.15))
        parts.append(silence(0.04))
        f *= 0.75
    return join(*parts)


def make_greeting():
    return join(
        syllable(0.10, 700, 1100, vibrato_hz=20, vibrato_depth=0.08),
        silence(0.03),
        syllable(0.12, 900, 1400, vibrato_hz=22, vibrato_depth=0.08),
    )


def make_done():
    return join(
        syllable(0.12, 600, 700, vibrato_hz=18, vibrato_depth=0.06),
        silence(0.04),
        syllable(0.12, 500, 600),
        silence(0.04),
        syllable(0.20, 800, 1500, vibrato_hz=24, vibrato_depth=0.10),
    )


def make_question():
    # Inquisitive 'boodleoop?' — two short steady taps then a long rising
    # sweep that imitates the rising-pitch intonation of a spoken question.
    # Repeated twice so it carries if the user has stepped away.
    one = join(
        syllable(0.10, 620, 640, vibrato_hz=14, vibrato_depth=0.04),
        silence(0.05),
        syllable(0.10, 720, 740, vibrato_hz=14, vibrato_depth=0.04),
        silence(0.05),
        syllable(0.36, 520, 1600, vibrato_hz=18, vibrato_depth=0.08),
    )
    return join(one, silence(0.18), one)


PRESETS = {
    "chirp": make_chirp,
    "working": make_working,
    "excited": make_excited,
    "alarm": make_alarm,
    "greeting": make_greeting,
    "done": make_done,
    "question": make_question,
}


def write_wav(samples, path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s * 0.7)) * 32000)
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))


def play(kind, force=False):
    if not should_play(kind, force):
        return
    # Reserve the slot before forking so concurrent hooks don't double-fire.
    write_last_ts(time.time())
    try:
        pid = os.fork()
    except OSError:
        return
    if pid != 0:
        return  # parent returns immediately

    # ---- child: synth + play, then exit ----
    try:
        os.setsid()
    except OSError:
        pass
    try:
        samples = PRESETS[kind]()
        fd, path = tempfile.mkstemp(suffix=".wav", prefix=f"friend-{kind}-")
        os.close(fd)
        write_wav(samples, path)
        cmd = f"afplay {shlex.quote(path)} >/dev/null 2>&1; rm -f {shlex.quote(path)}"
        subprocess.Popen(cmd, shell=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    finally:
        os._exit(0)


# ---------------- CLI ----------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0

    cmd = args[0]

    if cmd == "on":
        if DISABLED_FLAG.exists():
            DISABLED_FLAG.unlink()
        print("friend: enabled")
        return 0

    if cmd == "off":
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        DISABLED_FLAG.touch()
        print("friend: disabled")
        return 0

    if cmd == "status":
        print("friend:", "enabled" if is_enabled() else "disabled")
        last = read_last_ts()
        if last:
            print(f"last play: {time.time() - last:.1f}s ago")
        else:
            print("last play: never")
        return 0

    if cmd == "test":
        for k in ("greeting", "chirp", "working", "excited", "question", "alarm", "done"):
            print("playing", k)
            play(k, force=True)
            time.sleep(1.4)
        return 0

    if cmd in PRESETS:
        force = "--force" in args
        play(cmd, force=force)
        return 0

    print(f"friend: unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
