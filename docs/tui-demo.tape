# VHS Tape for Deep Research TUI Demo
# https://github.com/charmbracelet/vhs

Output docs/images/tui-demo.gif

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

# Navigate to Provider (press down a few times)
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 500ms

# Select Gemini provider using Right arrow
Right
Sleep 500ms

# Move down to see model updated
Down
Sleep 500ms
Down
Sleep 500ms

# Navigate to Query area
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 500ms
Down
Sleep 500ms

# Type a research query
Type "What are the most promising approaches to nuclear fusion energy in 2026?"
Sleep 1s

# Press 'r' to run research
Type "r"
Sleep 2s

# Wait for research to start (showing the loading state)
Sleep 5s

# Quit the app
Type "q"
Sleep 1s
