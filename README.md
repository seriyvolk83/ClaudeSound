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
| Claude finishes the turn                                    | `done`     | always  | task complete                |

`alarm` (descending) is also defined and can be played manually with `friend.py alarm`, but is not wired to any event by default.

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
/friend          # show status
/friend on       # enable sounds
/friend off      # disable sounds (persistent across sessions)
/friend test     # play one of every sound
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
