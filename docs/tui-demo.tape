# VHS Tape for Deep Research TUI Demo
# https://github.com/charmbracelet/vhs
#
# Requires: brew install vhs; GEMINI_API_KEY or GOOGLE_API_KEY for Gemini.
# Regenerate: vhs docs/tui-demo.tape

Output docs/images/tui-demo.gif

Set Shell "zsh"
Set FontSize 14
Set Width 1400
Set Height 900
Set Padding 20
Set Theme "Catppuccin Mocha"

# Gemini via CLI; Save Path preset for the save demo at the end
Type "cd /Users/pasquale/workspace/deep-research-mcp && uv run python cli/deep-research-tui.py --provider gemini --save-path docs/tui-demo-output.md --query 'What are three established facts about the planet Mars?'"
Enter
Sleep 3s

# Start deep research
Type "r"
Sleep 500ms

# Wait for Gemini deep research (typical run is a few minutes; allow headroom)
Sleep 360s

# Hold the completed report on screen
Sleep 8s

# Save output to the path in Save Path (footer: Save)
Type "s"
Sleep 3s

# Quit TUI
Type "q"
Sleep 2s

# Show the file written to disk
Type "wc -c docs/tui-demo-output.md && head -n 35 docs/tui-demo-output.md"
Enter
Sleep 6s
