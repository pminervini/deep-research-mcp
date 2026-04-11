#!/usr/bin/env bash
# Shorten the "Please wait..." section in docs/images/tui-demo.gif after a full VHS
# recording. Keeps: intro, ~4s of loading UI, then the completed report and shell demo.
#
# Requires: ffmpeg (palette filters). Tune times with ffmpeg scene detection if the
# tape layout changes:
#   ffmpeg -i docs/images/tui-demo.gif -vf "select='gt(scene,0.015)',showinfo" -f null - 2>&1
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

# Seconds (playback time in the source GIF). Re-tune after UI or tape changes:
#   ffmpeg -i docs/images/tui-demo.gif -vf "select='gt(scene,0.015)',showinfo" -f null - 2>&1
intro_end=9
load_start=9
load_end=13
result_start=177

ffmpeg -y -i "$src" -filter_complex "\
[0:v]trim=end=${intro_end},setpts=PTS-STARTPTS[v1];\
[0:v]trim=start=${load_start}:end=${load_end},setpts=PTS-STARTPTS[v2];\
[0:v]trim=start=${result_start},setpts=PTS-STARTPTS[v3];\
[v1][v2][v3]concat=n=3:v=1[v];\
[v]split[vt][vp];\
[vp]palettegen=reserve_transparent=1:stats_mode=diff[p];\
[vt][p]paletteuse=dither=bayer:bayer_scale=5[out]" \
  -map "[out]" "$tmp"
mv "$tmp" "$src"

echo "Updated: $src"
