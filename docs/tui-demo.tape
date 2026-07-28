# VHS Tape for Deep Research TUI Demo
# https://github.com/charmbracelet/vhs
#
# Requires: brew install vhs
# Regenerate: vhs docs/tui-demo.tape

Output docs/images/tui-demo.gif

Set Shell "zsh"
Set FontSize 14
Set Width 1400
Set Height 900
Set Padding 20
Set Framerate 10
Set Theme "Catppuccin Mocha"

# Start a local Dr Tulu-compatible endpoint so the demo is deterministic
Hide
Type "uv run python docs/tui-demo-server.py >/dev/null 2>&1 &"
Enter
Type "DEMO_SERVER_PID=$!"
Enter
Sleep 1s
Type "clear"
Enter
Show

# Launch the TUI with the query and save path preset
Type "uv run python cli/deep-research-tui.py --provider dr-tulu --save-path docs/tui-demo-output.md --query 'What are three established facts about the planet Mars?'"
Enter
Sleep 3s

# Start deep research
Type "r"
Sleep 5s

# Save output to the path in Save Path (footer: Save)
Type "s"
Sleep 3s

# Quit TUI
Type "q"
Sleep 2s

# Stop the local demo endpoint
Hide
Type "kill $DEMO_SERVER_PID && wait $DEMO_SERVER_PID 2>/dev/null"
Enter
Type "clear"
Enter
Show

# Show the file written to disk
Type "wc -c docs/tui-demo-output.md && head -n 35 docs/tui-demo-output.md"
Enter
Sleep 6s
