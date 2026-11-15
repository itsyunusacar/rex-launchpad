#!/bin/sh
# rex-launchpad installer
#   curl -fsSL https://raw.githubusercontent.com/itsyunusacar/rex-launchpad/main/install.sh | sh
# Options (environment variables):
#   LAUNCHPAD_ROOT  your projects folder (default: first of ~/Projects ~/Project ~/Developer ~/code)
#   LAUNCHPAD_KEY   shortcut (default: cmd+o)
set -eu

REPO="https://github.com/itsyunusacar/rex-launchpad.git"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/rex"
INIT="${REX_CONFIG:-$CONFIG_DIR/init.lua}"
DEST="$CONFIG_DIR/launchpad"

say() { printf '\033[1;34m›\033[0m %s\n' "$1"; }
die() { printf '\033[1;31m✗\033[0m %s\n' "$1" >&2; exit 1; }

command -v rex >/dev/null 2>&1 || die "rex not found. Install Rex first: https://www.superlogical.com/rex"
command -v python3 >/dev/null 2>&1 || die "python3 not found"
command -v git >/dev/null 2>&1 || die "git not found"

if [ -d "$DEST/.git" ]; then
  say "Updating $DEST"
  git -C "$DEST" pull --ff-only -q
else
  say "Installing to $DEST"
  mkdir -p "$CONFIG_DIR"
  git clone -q --depth 1 "$REPO" "$DEST"
fi

if [ -z "${LAUNCHPAD_ROOT:-}" ]; then
  for d in "$HOME/Projects" "$HOME/Project" "$HOME/Developer" "$HOME/code"; do
    if [ -d "$d" ]; then LAUNCHPAD_ROOT="$d"; break; fi
  done
  LAUNCHPAD_ROOT="${LAUNCHPAD_ROOT:-$HOME/Projects}"
fi
mkdir -p "$LAUNCHPAD_ROOT"
ROOT_LUA=$(printf '%s' "$LAUNCHPAD_ROOT" | sed "s|^$HOME|~|")
KEY="${LAUNCHPAD_KEY:-cmd+o}"

touch "$INIT"
if grep -q "launchpad/launchpad.lua" "$INIT"; then
  say "init.lua already loads rex-launchpad, leaving it as is"
else
  cat >> "$INIT" <<EOF

-- rex-launchpad: https://github.com/itsyunusacar/rex-launchpad
local launchpad = dofile("$DEST/launchpad.lua")
launchpad.setup{ root = "$ROOT_LUA", key = "$KEY" }
EOF
  say "Added rex-launchpad to $INIT"
fi

rex config reload >/dev/null 2>&1 || true

printf '\n\033[1m✓ Done.\033[0m Press %s in Rex. Projects folder: %s\n' "$KEY" "$ROOT_LUA"
printf '  To switch sessions from the panel, turn on Rex Settings → Rex Server → Remote Control.\n'
