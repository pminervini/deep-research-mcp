# VHS Tape for Deep Research TUI Demo
# https://github.com/charmbracelet/vhs
#
# After recording, speed up the waiting portion:
# ffmpeg -i docs/images/tui-demo-raw.gif -filter_complex "[0:v]setpts=0.3*PTS[v]" -map "[v]" docs/images/tui-demo.gif

Output docs/images/tui-demo-raw.gif

Set Shell "zsh"
Set FontSize 14
Set Width 1400
Set Height 900
Set Padding 20
Set Theme "Catppuccin Mocha"

# Start the TUI
Type "cd /Users/pminervi/workspace/deep-research-mcp && uv run python cli/deep-research-tui.py"
Enter
Sleep 3s

# Navigate to API Style
Down
Sleep 150ms
Down
Sleep 150ms
Down
Sleep 150ms
Down
Sleep 150ms

# Change to Chat Completions
Right
Sleep 300ms

# Navigate to Query area
Down
Sleep 150ms
Down
Sleep 150ms
Down
Sleep 150ms
Down
Sleep 150ms
Down
Sleep 150ms
Down
Sleep 150ms

# Type the research query
Type "What are the top 3 nuclear fusion breakthroughs in 2025?"
Sleep 500ms

# Tab to Research button
Tab
Sleep 150ms
Tab
Sleep 150ms
Tab
Sleep 150ms

# Press Enter to run research
Enter

# Brief pause showing "Starting research"
Sleep 2s

# Wait for results (API takes ~25s, we'll speed this up with ffmpeg)
Sleep 28s

# Show results
Sleep 4s

# Quit
Type "q"
Sleep 500ms
