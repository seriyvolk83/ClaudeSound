#!/usr/bin/env python3
"""Robot-beep sound effects for Claude Code hooks.

Usage:
  friend.py <kind> [--force]   play a sound; <kind> in:
                               chirp working excited alarm greeting done question sad oops
  friend.py stop               read Stop-hook JSON from stdin, play done or sad
  friend.py posttool           read PostToolUse JSON from stdin, play oops on failure
  friend.py on                 enable sounds
  friend.py off                disable sounds
  friend.py status             show current state
  friend.py help               status + command overview (also the no-arg default)
  friend.py test               play one of each (sequentially)
  friend.py voice              show the voice used in this directory
  friend.py voice list         list available voices
  friend.py voice <name>       set the voice for this directory
                               (classic / whistle / wood / chime)
  friend.py voice reset        go back to the default voice here

Sound moments:
  greeting  — you submit a message        (UserPromptSubmit)
  working   — Claude runs a shell command  (PreToolUse Bash)
  chirp     — Claude reads / searches      (PreToolUse Read/Grep/WebFetch…)
  excited   — Claude edits / writes code   (PostToolUse Edit/Write…)
  question  — Claude needs your input      (Notification)
  oops      — a shell command failed       (PostToolUse Bash, non-zero exit)
  done      — Claude finishes successfully (Stop reason=end_turn)
  sad       — interrupted or limit reached (Stop reason=interrupted/max_turns)

Voices:
  Each project directory can have its own voice so parallel Claude windows
  are distinguishable by ear. Same melodies, different instrument:
  robot beeps, human whistling, marimba taps, music-box bells.
  Resolution: $FRIEND_VOICE env var > voices.json[cwd] > "classic".
"""
import json
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
VOICES_FILE = PLUGIN_DIR / "voices.json"
RATE = 22050

MIN_INTERVAL = {
    "chirp":    10.0,
    "working":   6.0,
    "excited":   0.0,
    "alarm":     3.0,
    "greeting":  0.0,
    "done":      0.0,
    "question":  0.0,
    "sad":       0.0,
    "oops":      3.0,
}

# Same melodies, different instrument. Every voice plays the exact same
# pitch contours and durations as the presets define — only the sound
# material changes, so the learned vocabulary carries across voices.
#   sweep   — the original electronic beeps (swept tones + vibrato)
#   whistle — a person whistling the tunes (pure tone, slow human vibrato)
#   notes   — struck notes: a pitch sweep becomes a little run of hits
#             quantized to a pentatonic scale (marimba / music box)
VOICES = {
    "classic": {"style": "sweep", "pitch": 1.0, "speed": 1.0,
                "blurb": "the original robot beeps"},
    "whistle": {"style": "whistle", "pitch": 1.3, "speed": 1.0,
                "blurb": "someone whistling the same tunes"},
    "wood":    {"style": "notes", "pitch": 1.0, "speed": 1.0,
                "step": 0.085, "ring": 0.30, "tail": 0.15,
                "partials": ((1.0, 1.0, 12.0), (3.9, 0.55, 18.0), (9.2, 0.25, 26.0)),
                "blurb": "wooden marimba taps"},
    "chime":   {"style": "notes", "pitch": 1.5, "speed": 1.0,
                "step": 0.11, "ring": 0.60, "tail": 0.30,
                "partials": ((1.0, 1.0, 5.0), (2.0, 0.45, 7.0), (3.0, 0.20, 9.0)),
                "blurb": "little music-box bells"},
}
DEFAULT_VOICE = "classic"
_VOICE = VOICES[DEFAULT_VOICE]


def read_voice_map():
    try:
        data = json.loads(VOICES_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_voice_name():
    env = os.environ.get("FRIEND_VOICE")
    if env in VOICES:
        return env
    name = read_voice_map().get(os.getcwd())
    return name if name in VOICES else DEFAULT_VOICE


def set_current_voice(name=None):
    global _VOICE
    _VOICE = VOICES[name or resolve_voice_name()]


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

def _envelope(n, attack=0.015, release=0.040):
    a = max(1, int(attack * RATE))
    r = max(1, int(release * RATE))
    out = [1.0] * n
    for i in range(min(a, n)):
        out[i] = i / a
    for i in range(min(r, n)):
        out[n - 1 - i] = min(out[n - 1 - i], i / r)
    return out


def _sweep(duration, f_start, f_end, vibrato_hz, vibrato_depth, wave_type,
           attack=0.015, release=0.040):
    """One swept-tone syllable with optional vibrato."""
    n = max(1, int(duration * RATE))
    env = _envelope(n, attack, release)
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


_PENTATONIC = (0, 2, 4, 7, 9)  # major pentatonic — any run of these sounds musical


def _quantize(freq):
    """Snap a frequency to the nearest major-pentatonic note."""
    m = 69.0 + 12.0 * math.log2(freq / 440.0)
    base = math.floor(m / 12.0) * 12.0
    candidates = [base + o + pc for o in (-12, 0, 12) for pc in _PENTATONIC]
    best = min(candidates, key=lambda x: abs(m - x))
    return 440.0 * 2.0 ** ((best - 69.0) / 12.0)


def _strike_into(buf, offset, freq, ring, partials):
    """Additively render one struck note (exponentially decaying partials)."""
    n = min(len(buf) - offset, max(1, int(ring * RATE)))
    amp_total = sum(a for _, a, _ in partials)
    for i in range(n):
        t = i / RATE
        s = 0.0
        for ratio, amp, decay in partials:
            s += amp * math.sin(2 * math.pi * freq * ratio * t) * math.exp(-t * decay)
        buf[offset + i] += s / amp_total


def _note_run(duration, f_start, f_end, v):
    """A pitch sweep as a run of struck notes following the same contour.
    Short syllables become a single hit; long sweeps become a glissando run."""
    n_hits = max(1, round(duration / v["step"]))
    total = max(1, int((duration + v["tail"]) * RATE))
    buf = [0.0] * total
    for k in range(n_hits):
        frac = k / (n_hits - 1) if n_hits > 1 else 0.0
        f = _quantize(f_start * (f_end / f_start) ** frac)
        _strike_into(buf, int(k * v["step"] * RATE), f, v["ring"], v["partials"])
    peak = max(abs(s) for s in buf)
    if peak > 0.95:
        buf = [s * 0.95 / peak for s in buf]
    fade = max(1, int(0.06 * RATE))
    for i in range(min(total, fade)):
        buf[-1 - i] *= i / fade
    return buf


def syllable(duration, f_start, f_end, vibrato_hz=0.0, vibrato_depth=0.0, wave_type="sine"):
    """One melody syllable, rendered in the active voice's instrument."""
    v = _VOICE
    duration *= v["speed"]
    f_start = max(90.0, f_start * v["pitch"])
    f_end = max(90.0, f_end * v["pitch"])
    if v["style"] == "notes":
        return _note_run(duration, f_start, f_end, v)
    if v["style"] == "whistle":
        # a human whistle: always a pure tone, slow gentle vibrato, soft edges
        return _sweep(duration, f_start, f_end,
                      min(vibrato_hz, 6.0), vibrato_depth * 0.7, "sine",
                      attack=0.030, release=0.060)
    return _sweep(duration, f_start, f_end, vibrato_hz, vibrato_depth, wave_type)


def silence(duration):
    return [0.0] * max(0, int(duration * RATE))


def join(*parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


# ---------------- presets ----------------

def make_chirp():
    """Very short read/scan blip — varied direction so it never sounds like a question."""
    f0 = random.uniform(500, 1000)
    ratio = random.choice([0.55, 0.70, 0.90, 1.0, 1.25, 1.40])
    f1 = f0 * ratio
    return syllable(random.uniform(0.08, 0.13), f0, f1, vibrato_hz=15, vibrato_depth=0.04)


def make_working():
    """2–3 short punchy blips for Bash execution — varied, never a long sweep."""
    parts = []
    for _ in range(random.randint(2, 3)):
        f0 = random.uniform(400, 1000)
        ratio = random.choice([0.55, 0.70, 0.85, 1.0, 1.30])
        f1 = f0 * ratio
        parts.append(syllable(
            random.uniform(0.07, 0.11), f0, f1,
            vibrato_hz=random.uniform(20, 35), vibrato_depth=0.06,
        ))
        parts.append(silence(random.uniform(0.02, 0.04)))
    return join(*parts)


def make_excited():
    """1–2 quick blips when Claude writes/edits a file — short like other working sounds."""
    parts = []
    for _ in range(random.randint(1, 2)):
        f0 = random.uniform(700, 1100)
        ratio = random.choice([0.70, 0.85, 1.0, 1.20, 1.35])
        f1 = f0 * ratio
        parts.append(syllable(random.uniform(0.06, 0.10), f0, f1, vibrato_hz=22, vibrato_depth=0.05))
        parts.append(silence(0.02))
    return join(*parts)


def make_alarm():
    """Urgent descending alarm (unused by default hooks, available manually)."""
    parts = []
    f = random.uniform(800, 1000)
    for _ in range(3):
        parts.append(syllable(0.16, f, f * 0.55, vibrato_hz=10, vibrato_depth=0.15))
        parts.append(silence(0.04))
        f *= 0.75
    return join(*parts)


def make_greeting():
    """Friendly wake-up on user prompt submit."""
    return join(
        syllable(0.10, 700, 1100, vibrato_hz=20, vibrato_depth=0.08),
        silence(0.03),
        syllable(0.12, 900, 1400, vibrato_hz=22, vibrato_depth=0.08),
    )


def make_question():
    """Language-curve question: two anchor taps then a long strong rise low→high.
    Played twice so it carries if you stepped away."""
    one = join(
        syllable(0.09, 480, 500, vibrato_hz=10, vibrato_depth=0.03),   # anchor low
        silence(0.045),
        syllable(0.09, 560, 590, vibrato_hz=10, vibrato_depth=0.03),   # step up
        silence(0.045),
        syllable(0.52, 450, 2100, vibrato_hz=20, vibrato_depth=0.09),  # long rising sweep ↑
    )
    return join(one, silence(0.22), one)


def make_sad():
    """Wa-Wa-Wa-wa-a-a: three descending beats then a long trailing fade — dejected robot."""
    parts = []
    descents = [(960, 370), (790, 295), (630, 230)]
    for f_start, f_end in descents:
        parts.append(syllable(
            0.24, f_start, f_end,
            vibrato_hz=7, vibrato_depth=0.14,
            wave_type="triangle",
        ))
        parts.append(silence(0.07))
    # Long trailing "wa-a-a" fading into silence
    parts.append(syllable(
        0.65, 510, 150,
        vibrato_hz=4, vibrato_depth=0.18,
        wave_type="triangle",
    ))
    return join(*parts)


def make_done():
    """Long happy completion: crescendo that rises to a joyful peak then settles."""
    return join(
        syllable(0.10, 550,  700, vibrato_hz=16, vibrato_depth=0.06),
        silence(0.035),
        syllable(0.12, 700,  950, vibrato_hz=20, vibrato_depth=0.08),
        silence(0.035),
        syllable(0.15, 850, 1200, vibrato_hz=22, vibrato_depth=0.09),
        silence(0.040),
        syllable(0.58, 950, 2300, vibrato_hz=26, vibrato_depth=0.11),  # long joyful rise ↑
        silence(0.050),
        syllable(0.20, 1900, 1600, vibrato_hz=20, vibrato_depth=0.07), # settle happily ↘
    )


def make_oops():
    """Short mechanical 'bzzt-bzzt' — a command failed mid-work.
    Square wave so it reads as a fault, not a sad ending."""
    parts = []
    for _ in range(2):
        parts.append(syllable(0.11, 290, 230, vibrato_hz=40, vibrato_depth=0.25,
                              wave_type="square"))
        parts.append(silence(0.05))
    return join(*parts)


PRESETS = {
    "chirp":    make_chirp,
    "working":  make_working,
    "excited":  make_excited,
    "alarm":    make_alarm,
    "greeting": make_greeting,
    "question": make_question,
    "sad":      make_sad,
    "done":     make_done,
    "oops":     make_oops,
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
    write_last_ts(time.time())
    try:
        pid = os.fork()
    except OSError:
        return
    if pid != 0:
        return  # parent returns immediately

    # child: synth + play, then exit
    try:
        os.setsid()
    except OSError:
        pass
    try:
        set_current_voice()
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


def stop_from_stdin():
    """Read Claude Code Stop-hook JSON from stdin and play done or sad."""
    try:
        data = json.loads(sys.stdin.read())
        reason = data.get("reason", "end_turn")
    except Exception:
        reason = "end_turn"
    if reason in ("max_turns", "interrupted"):
        play("sad", force=True)
    else:
        play("done", force=True)


def _tool_failed(resp):
    """Best-effort failure detection across hook payload shapes."""
    if not isinstance(resp, dict):
        return False
    if resp.get("interrupted") or resp.get("is_error") or resp.get("isError"):
        return True
    if resp.get("success") is False:
        return True
    code = resp.get("exit_code", resp.get("exitCode"))
    return isinstance(code, int) and code != 0


def posttool_from_stdin():
    """Read PostToolUse JSON from stdin; buzz if the tool call failed."""
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return
    if _tool_failed(data.get("tool_response")):
        play("oops")


# ---------------- CLI ----------------

HELP = """\
commands:
  /friend on            enable sounds
  /friend off           disable sounds (persists across sessions)
  /friend status        show on/off state and the voice used here
  /friend test          play every sound in this directory's voice
  /friend voice         show the voice used in this directory
  /friend voice list    list voices: classic, whistle, wood, chime
  /friend voice <name>  set this directory's voice (each project can differ)
  /friend voice reset   back to the default voice (classic)
  /friend help          show this help

extras (shell): python3 ~/.claude/friend/friend.py <sound> [--force]
  sounds: chirp working excited alarm greeting question sad done oops
env overrides: FRIEND_OFF=1 mutes a session, FRIEND_VOICE=<name> forces a voice\
"""


def print_status():
    print("friend:", "enabled" if is_enabled() else "disabled")
    print(f"voice here: {resolve_voice_name()} ({os.getcwd()})")


def main():
    args = sys.argv[1:]
    if not args:
        args = ["help"]

    cmd = args[0]

    if cmd == "help":
        print_status()
        print()
        print(HELP)
        return 0

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
        print_status()
        last = read_last_ts()
        if last:
            print(f"last play: {time.time() - last:.1f}s ago")
        else:
            print("last play: never")
        return 0

    if cmd == "voice":
        sub = args[1] if len(args) > 1 else None
        if sub is None or sub == "list":
            current = resolve_voice_name()
            for name, v in VOICES.items():
                mark = "*" if name == current else " "
                print(f"{mark} {name:7s} — {v['blurb']}")
            print(f"voice here: {current} ({os.getcwd()})")
            return 0
        mapping = read_voice_map()
        if sub == "reset":
            mapping.pop(os.getcwd(), None)
            PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
            VOICES_FILE.write_text(json.dumps(mapping, indent=2))
            print(f"friend: voice here reset to {DEFAULT_VOICE}")
            play("greeting", force=True)
            return 0
        if sub not in VOICES:
            print(f"friend: unknown voice {sub!r}; options: "
                  + ", ".join(VOICES) + ", reset", file=sys.stderr)
            return 2
        mapping[os.getcwd()] = sub
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        VOICES_FILE.write_text(json.dumps(mapping, indent=2))
        print(f"friend: voice here is now {sub} — {VOICES[sub]['blurb']}")
        play("greeting", force=True)
        return 0

    if cmd == "test":
        print(f"voice: {resolve_voice_name()}")
        for k in ("greeting", "chirp", "working", "excited", "question", "oops", "sad", "done"):
            print("playing", k)
            play(k, force=True)
            time.sleep(1.8)
        return 0

    if cmd == "stop":
        stop_from_stdin()
        return 0

    if cmd == "posttool":
        posttool_from_stdin()
        return 0

    if cmd in PRESETS:
        force = "--force" in args
        play(cmd, force=force)
        return 0

    print(f"friend: unknown command {cmd!r} — try '/friend help'", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
