#!/usr/bin/env bash
#
# Generate the documentation screenshots in docs/screenshots/.
#
# Requires charmbracelet/freeze (renders a command's output to PNG):
#   go install github.com/charmbracelet/freeze@latest   # or: brew install freeze
#   https://github.com/charmbracelet/freeze
#
# Commands that hit the API need a saved token first (htb init) and an active
# machine for the `active` shots. Run from anywhere:
#
#   scripts/screenshots.sh            # capture all
#   scripts/screenshots.sh vpn-servers speedrun   # capture a subset
#
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=docs/screenshots
mkdir -p "$OUT"

if ! command -v freeze >/dev/null 2>&1; then
  echo "freeze not found. Install it: https://github.com/charmbracelet/freeze" >&2
  exit 1
fi

HTB="./htb --color always"

# name -> command. Edit targets to taste.
declare -A SHOTS=(
  [vpn-servers]="$HTB vpn servers"
  [machine-list]="$HTB machine list"
  [machine-search]="$HTB machine search board"
  [machine-active]="$HTB machine active"
  [machine-oneline]="$HTB machine active --oneline"
  [user-info]="$HTB user info"
  [completion]="./htb completion bash"
  [speedrun]="python3 scripts/demo_speedrun.py"
)

names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  names=("${!SHOTS[@]}")
fi

for name in "${names[@]}"; do
  cmd=${SHOTS[$name]:-}
  if [ -z "$cmd" ]; then
    echo "unknown shot: $name (known: ${!SHOTS[*]})" >&2
    continue
  fi
  echo "capturing $name -> $OUT/$name.png"
  freeze --execute "$cmd" --output "$OUT/$name.png"
done

echo "done -> $OUT"
