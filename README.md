# Human-like Activity Simulator for Ubuntu Desktop

A sophisticated Python script that simulates realistic human-like desktop activity for testing time-tracker and screenshot monitoring systems.

## Features

- **Intelligent Window/Tab Switching**: Analyzes open windows and switches between them naturally
- **Context-Aware Behavior**: Different actions based on window type (browser, terminal, editor)
- **Natural Mouse Movement**: Smooth, human-like mouse movements
- **Configurable Rates**: Set min/max actions per minute for all activity types
- **Reading Pauses**: Simulates natural pauses when "reading" content
- **Safe Mode**: Test without actually sending inputs
- **Detailed Statistics**: Track all simulated activity

## Prerequisites

Install required system tools:

```bash
sudo apt install xdotool wmctrl x11-utils
```

## Installation

1. Clone or copy the files to your desired location
2. Make the script executable:
   ```bash
   chmod +x activity_simulator.py
   ```

## Usage

### Basic Usage

```bash
# Run with default configuration
./activity_simulator.py

# Run in safe mode (simulates without sending actual inputs)
./activity_simulator.py --safe

# Run quietly (no verbose logging)
./activity_simulator.py --quiet
```

### Create/Modify Configuration

```bash
# Create default config file
./activity_simulator.py --create-config
```

Then edit `config.json` to customize behavior.

### Command Line Overrides

```bash
# Override specific settings
./activity_simulator.py --keystrokes-min 50 --keystrokes-max 150
./activity_simulator.py --clicks-min 10 --clicks-max 30
```

## Configuration Options

Edit `config.json` to customize:

| Setting | Description | Default |
|---------|-------------|---------|
| `keystrokes_min_per_minute` | Minimum keystrokes per minute | 30 |
| `keystrokes_max_per_minute` | Maximum keystrokes per minute | 120 |
| `clicks_min_per_minute` | Minimum mouse clicks per minute | 5 |
| `clicks_max_per_minute` | Maximum mouse clicks per minute | 20 |
| `switches_min_per_minute` | Minimum window/tab switches per minute | 2 |
| `switches_max_per_minute` | Maximum window/tab switches per minute | 8 |
| `scrolls_min_per_minute` | Minimum scroll actions per minute | 3 |
| `scrolls_max_per_minute` | Maximum scroll actions per minute | 15 |
| `mouse_moves_min_per_minute` | Minimum mouse movements per minute | 10 |
| `mouse_moves_max_per_minute` | Maximum mouse movements per minute | 40 |
| `typing_burst_min_chars` | Minimum characters in typing burst | 3 |
| `typing_burst_max_chars` | Maximum characters in typing burst | 15 |
| `min_pause` | Minimum pause between actions (seconds) | 0.1 |
| `max_pause` | Maximum pause between actions (seconds) | 2.0 |
| `reading_pause_chance` | Probability of a reading pause (0-1) | 0.15 |
| `reading_pause_min` | Minimum reading pause duration (seconds) | 3.0 |
| `reading_pause_max` | Maximum reading pause duration (seconds) | 10.0 |
| `safe_mode` | If true, simulates without actual inputs | false |
| `verbose` | Enable detailed logging | true |

## How It Works

### Window Analysis
The script detects and classifies open windows:
- **Browsers**: Chrome, Firefox, Brave, etc.
- **Terminals**: GNOME Terminal, Terminator, etc.
- **Editors**: VS Code, Sublime Text, etc.
- **File Managers**: Nautilus, Thunar, etc.

### Context-Aware Actions
- **In Browser**: More scrolling, tab switching with Ctrl+Tab
- **In Terminal**: More keyboard activity, terminal-specific tab switching
- **In Editor**: More typing simulation, code-like scrolling patterns

### Action Types
1. **Keystroke Simulation**: Simulates typing timing patterns
2. **Mouse Movement**: Natural, smooth cursor movements
3. **Scrolling**: Direction and amount based on window type
4. **Window Switching**: Alt+Tab, Ctrl+Tab, or direct window activation
5. **Mouse Clicks**: Mostly left-clicks, occasional right-click (with Escape)

### Natural Behavior Patterns
- Variable delays between actions
- Occasional "reading pauses" to simulate human thinking
- Weighted action selection based on current context
- Smooth mouse movements with multiple steps

## Stopping the Simulation

Press `Ctrl+C` to stop gracefully. The script will display final statistics.

## Example Output

```
==================================================
HUMAN-LIKE ACTIVITY SIMULATOR
==================================================
Press Ctrl+C to stop
Safe mode: OFF
==================================================

[14:32:15] Starting activity simulation...
[14:32:15] Screen resolution: 1920x1080
[14:32:15] Found 8 windows
[14:32:15]   - [browser] Google Chrome - GitHub
[14:32:15]   - [terminal] Terminal
[14:32:15]   - [editor] Visual Studio Code
[14:32:16] Moved mouse to (856, 423)
[14:32:17] Scrolled down 4 times
[14:32:19] Switched to next browser tab
[14:32:21] Simulated typing 8 characters
...
```

## Safety Notes

- The script primarily moves the mouse, scrolls, and switches windows
- Keystroke simulation only simulates timing, doesn't type actual characters
- Use `--safe` mode first to test without actual inputs
- The script won't interfere with system shortcuts or critical areas

## Troubleshooting

### "wmctrl not found"
```bash
sudo apt install wmctrl
```

### "xdotool not found"
```bash
sudo apt install xdotool
```

### No windows detected
Make sure you have some windows open before running the script.

### Permission issues
Some Wayland sessions may block xdotool. Use X11 session for full compatibility.

## License

MIT License - Use at your own risk for testing purposes only.
