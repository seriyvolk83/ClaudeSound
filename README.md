# Claude Sound

Synthesized robot-beep sound effects for [Claude Code](https://claude.com/claude-code) tool events — the sounds are inspired by R2-D2, so think of it as turning on **R2-D2 friend mode** in your terminal: a chirp when Claude reads files, a happy warble when it edits one, an inquisitive "boodleoop?" when it needs you to come back and answer something, a 3-note flourish when it finishes.

Pure Python stdlib — no `pip install`, no external sound files. Sounds are synthesized at runtime as FM-modulated sine waves and played through `afplay`.

## What you hear

| Claude event                                                | Sound      | Min gap | Why                          |
| ----------------------------------------------------------- | ---------- | ------- | ---------------------------- |
| You submit a prompt                                         | `greeting` | always  | "I heard you"                |
| `Bash` tool starts                                          | `working`  | 6 s     | progress signal              |
| `Read` / `Grep` / `Glob` / `WebFetch` / `WebSearch` starts  | `chirp`    | 10 s    | rare progress tick           |
| `Edit` / `Write` / `MultiEdit` / `NotebookEdit` finishes    | `excited`  | always  | **a file actually changed**  |
| Claude is waiting on you (permission / idle)                | `question` | always  | come back to the computer    |
| A `Bash` command fails (non-zero exit / interrupted)        | `oops`     | 3 s     | something went wrong mid-work |
| Claude finishes the turn                                    | `done`     | always  | task complete                |
| Turn ends by interrupt / max turns                          | `sad`      | always  | it didn't end well           |

`oops` is a short square-wave "bzzt-bzzt" — a mechanical fault, deliberately distinct in timbre from the sine-wave beeps and from the `sad` ending. `alarm` (descending) is also defined and can be played manually with `friend.py alarm`, but is not wired to any event by default.

## Voices

Running two Claude windows side by side? Give each project its own voice so you can tell them apart by ear. All voices play the *same melodies* — same rising/falling contours, same rhythm — but on a completely different instrument, so each window has an unmistakable character while the vocabulary you've learned still applies:

| Voice     | Instrument                                                                  |
| --------- | --------------------------------------------------------------------------- |
| `classic` | the original robot beeps (swept tones + vibrato)                            |
| `whistle` | someone whistling the tunes — pure tone, slow human vibrato                 |
| `wood`    | marimba taps — pitch sweeps become little xylophone runs                    |
| `chime`   | music-box bells — melodies ring out as tiny arpeggios                       |

For the struck voices (`wood`, `chime`) every note is snapped to a major-pentatonic scale, so even the randomized work blips always sound musical.

The voice is stored **per project directory** (`~/.claude/friend/voices.json`), so each window picks it up automatically from its working directory:

```
/friend voice           # show the voice used here
/friend voice list      # list voices
/friend voice wood      # this project now sounds like a marimba
/friend voice reset     # back to classic
```

A `FRIEND_VOICE=wood` environment variable overrides the per-directory setting — handy when two windows share the same directory: `FRIEND_VOICE=chime claude`.

## Requirements

- macOS (uses the built-in `/usr/bin/afplay`)
- `python3` on `PATH` (any 3.x)
- Claude Code CLI

Linux/Windows are not supported out of the box — you'd need to swap `afplay` for `paplay` / `aplay` / `winsound` in `friend.py`.

## Install

```sh
git clone https://github.com/<your-fork>/<repo-name>.git
cd <repo-name>
./install.sh
```

Then press ⭐️ star for this repo 😉

The installer:

1. copies `friend.py` to `~/.claude/friend/friend.py`
2. copies `commands/friend.md` to `~/.claude/commands/friend.md` (provides `/friend`)
3. backs up `~/.claude/settings.json` and merges the hook config from `settings.hooks.json` into it, leaving any of your existing settings untouched.

Re-running `./install.sh` is safe — it strips any prior `friend.py` hook entries before re-adding them.

Restart your `claude` session afterwards (Claude Code reads `settings.json` on launch).

### Manual install

If you'd rather not run the script:

```sh
mkdir -p ~/.claude/friend ~/.claude/commands
cp friend.py          ~/.claude/friend/friend.py
cp commands/friend.md ~/.claude/commands/friend.md
chmod +x ~/.claude/friend/friend.py
```

Then merge the contents of `settings.hooks.json` into `~/.claude/settings.json` under the top-level `"hooks"` key.

## Usage

From inside `claude`:

```
/friend            # status + list of all commands (same as /friend help)
/friend on         # enable sounds
/friend off        # disable sounds (persistent across sessions)
/friend test       # play one of every sound (in this directory's voice)
/friend voice wood # set this project's voice (see Voices above)
```

Or directly from your shell:

```sh
python3 ~/.claude/friend/friend.py status
python3 ~/.claude/friend/friend.py excited     # try a single sound
python3 ~/.claude/friend/friend.py off
FRIEND_OFF=1 claude                            # disable for one session only
```

## Tuning

- **Cadence** — edit the `MIN_INTERVAL` dict at the top of `friend.py` (seconds between consecutive plays of the same sound type).
- **Mapping** — edit the matchers in `~/.claude/settings.json` (or `settings.hooks.json` before installing) to change which tools trigger which sound.
- **The sounds themselves** — each preset is a small Python function in `friend.py` (`make_chirp`, `make_excited`, …). Tweak the frequency sweeps, vibrato depth, and durations to taste.

## Uninstall

```sh
rm -rf ~/.claude/friend
rm -f  ~/.claude/commands/friend.md
```

Then remove the `"hooks"` block (or just the entries whose command contains `friend.py`) from `~/.claude/settings.json`. The installer left a timestamped `.bak` of your original settings next to it.

## Repo layout

```
.
├── friend.py             # synth + player + CLI
├── commands/
│   └── friend.md         # /friend slash command
├── settings.hooks.json   # hook config to merge into ~/.claude/settings.json
├── install.sh            # one-shot installer (idempotent)
└── README.md
```

## License

MIT.
