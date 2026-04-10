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

# Navigate to API Style (Mode -> Save Path -> Task ID -> Provider -> API Style)
Down
Sleep 200ms
Down
Sleep 200ms
Down
Sleep 200ms
Down
Sleep 200ms

# Change to Chat Completions for faster results
Right
Sleep 400ms

# Navigate to Query area (API Style -> Model -> Base URL -> Include Analysis -> JSON Output -> Query)
Down
Sleep 200ms
Down
Sleep 200ms
Down
Sleep 200ms
Down
Sleep 200ms
Down
Sleep 200ms
Down
Sleep 200ms

# Type the research query
Type "What are the top 3 nuclear fusion breakthroughs in 2025?"
Sleep 1s

# Tab to Research button (Query -> System Prompt -> Clarify -> Research)
Tab
Sleep 200ms
Tab
Sleep 200ms
Tab
Sleep 200ms

# Press Enter to run research
Enter
Sleep 3s

# Wait for research to complete (chat completions takes ~10s)
Sleep 17s

# Show results for a moment
Sleep 5s

# The app shows results - end recording here
# (pressing q while focused on a button should work)
Type "q"
Sleep 1s
