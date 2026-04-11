#!/usr/bin/env bash
# Shorten the long Gemini wait in docs/images/tui-demo.gif after a full VHS recording.
#
# Uses two segments only (no duplicate "please wait" clip):
#   1) First few seconds: shell, TUI launch, query, press r, brief spinner
#   2) Jump to completed report (scene-detected time from full capture)
#
# Requires: ffmpeg. Re-tune times after UI or tape changes:
#   ffmpeg -i docs/images/tui-demo.gif -vf "select='gt(scene,0.012)',showinfo" -f null - 2>&1
#
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
src="${1:-$root/docs/images/tui-demo.gif}"
tmp="$root/docs/images/tui-demo-trimmed.gif"

dur="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$src")"
if awk -v d="$dur" 'BEGIN{exit !(d < 90)}'; then
  echo "skip: $src duration is ${dur}s (already shortened or not a full VHS capture); expected roughly 3+ minutes" >&2
  exit 0
fi

# Seconds in the *full* VHS GIF (before this script). Re-tune after UI or tape changes.
intro_end=6
result_start=177

ffmpeg -y -i "$src" -filter_complex "\
[0:v]trim=end=${intro_end},setpts=PTS-STARTPTS[v1];\
[0:v]trim=start=${result_start},setpts=PTS-STARTPTS[v2];\
[v1][v2]concat=n=2:v=1[v];\
[v]split[vt][vp];\
[vp]palettegen=reserve_transparent=1:stats_mode=diff[p];\
[vt][p]paletteuse=dither=bayer:bayer_scale=5[out]" \
  -map "[out]" "$tmp"
mv "$tmp" "$src"

echo "Updated: $src"
