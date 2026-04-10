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

# Navigate to API Style (skip Mode, Save Path, Task ID, Provider)
Down
Sleep 250ms
Down
Sleep 250ms
Down
Sleep 250ms
Down
Sleep 250ms

# Now on API Style - change to Chat Completions for faster demo
Right
Sleep 500ms

# Model auto-updates to gpt-4o-mini, navigate to Query
Down
Sleep 250ms
Down
Sleep 250ms
Down
Sleep 250ms
Down
Sleep 250ms
Down
Sleep 250ms
Down
Sleep 250ms

# Now in Query TextArea - type a research query
Type "What are the top 3 nuclear fusion breakthroughs in 2025?"
Sleep 1s

# Press 'r' to run research
Type "r"

# Wait for research to complete (chat completions is fast ~10s)
Sleep 15s

# Show the results - scroll output if needed
Sleep 5s

# Save the output - press 's'
Type "s"
Sleep 2s

# Quit
Type "q"
Sleep 1s
