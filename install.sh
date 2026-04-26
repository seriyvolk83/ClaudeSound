#!/usr/bin/env bash
# Installer for the friend mode plugin for Claude Code.
#
# Copies the script and slash command into ~/.claude/, then merges the
# hook config from settings.hooks.json into ~/.claude/settings.json
# (preserving any existing keys; idempotent — safe to re-run).

set -euo pipefail

REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLAUDE_DIR="${HOME}/.claude"
PLUGIN_DIR="${CLAUDE_DIR}/friend"
COMMANDS_DIR="${CLAUDE_DIR}/commands"
SETTINGS="${CLAUDE_DIR}/settings.json"
HOOKS_SRC="${REPO_DIR}/settings.hooks.json"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "error: macOS only (depends on /usr/bin/afplay)" >&2
  exit 1
fi
command -v afplay  >/dev/null || { echo "error: afplay not found"  >&2; exit 1; }
command -v python3 >/dev/null || { echo "error: python3 not found" >&2; exit 1; }

mkdir -p "${PLUGIN_DIR}" "${COMMANDS_DIR}"

install -m 0755 "${REPO_DIR}/friend.py"          "${PLUGIN_DIR}/friend.py"
install -m 0644 "${REPO_DIR}/commands/friend.md" "${COMMANDS_DIR}/friend.md"
echo "installed: ${PLUGIN_DIR}/friend.py"
echo "installed: ${COMMANDS_DIR}/friend.md"

python3 - "$SETTINGS" "$HOOKS_SRC" <<'PY'
import json, os, shutil, sys, time

settings_path, hooks_path = sys.argv[1], sys.argv[2]
fragment = json.load(open(hooks_path))

if os.path.exists(settings_path):
    backup = f"{settings_path}.bak.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(settings_path, backup)
    print(f"backup:    {backup}")
    settings = json.load(open(settings_path))
else:
    settings = {}

# Strip pre-existing friend.py hook entries so re-running is a no-op.
existing = settings.get("hooks", {})
cleaned = {}
for event, configs in existing.items():
    kept_configs = []
    for cfg in configs:
        kept = [h for h in cfg.get("hooks", [])
                if "friend.py" not in h.get("command", "")]
        if kept:
            new_cfg = dict(cfg)
            new_cfg["hooks"] = kept
            kept_configs.append(new_cfg)
    if kept_configs:
        cleaned[event] = kept_configs

# Append fresh hooks.
for event, configs in fragment["hooks"].items():
    cleaned.setdefault(event, []).extend(configs)
settings["hooks"] = cleaned

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(f"merged:    {settings_path}")
PY

echo
echo "Done. Restart your claude session, then run: /friend test"
