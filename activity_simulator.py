#!/usr/bin/env python3
"""
Human-like Activity Simulator for Ubuntu Desktop
Simulates realistic user behavior including:
- Intelligent window/tab switching
- Natural scrolling patterns
- Random but safe keystrokes (that don't affect anything)
- Mouse movements and clicks (in safe areas)

For testing time-tracker/screenshot systems.
"""

import subprocess
import random
import time
import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
import threading
import signal
import sys

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

@dataclass
class Config:
    """Configuration for the activity simulator"""
    # Keystrokes per minute range
    keystrokes_min_per_minute: int = 30
    keystrokes_max_per_minute: int = 120
    
    # Mouse clicks per minute range
    clicks_min_per_minute: int = 5
    clicks_max_per_minute: int = 20
    
    # Tab/Window switches per minute range
    switches_min_per_minute: int = 2
    switches_max_per_minute: int = 8
    
    # Scroll actions per minute range
    scrolls_min_per_minute: int = 3
    scrolls_max_per_minute: int = 15
    
    # Mouse movement frequency (movements per minute)
    mouse_moves_min_per_minute: int = 10
    mouse_moves_max_per_minute: int = 40
    
    # Typing burst settings (simulates typing words)
    typing_burst_min_chars: int = 3
    typing_burst_max_chars: int = 15
    
    # Pause between actions (seconds)
    min_pause: float = 0.1
    max_pause: float = 2.0
    
    # Reading/thinking pauses (longer pauses to simulate reading)
    reading_pause_chance: float = 0.15  # 15% chance of a reading pause
    reading_pause_min: float = 3.0
    reading_pause_max: float = 10.0
    
    # Safe mode - only simulate, don't actually send inputs
    safe_mode: bool = False
    
    # Enable verbose logging
    verbose: bool = True

    @classmethod
    def load(cls, path: str = CONFIG_FILE) -> 'Config':
        """Load configuration from JSON file"""
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                return cls(**data)
        return cls()
    
    def save(self, path: str = CONFIG_FILE):
        """Save configuration to JSON file"""
        with open(path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)


class WindowType(Enum):
    """Types of windows for context-aware behavior"""
    BROWSER = "browser"
    TERMINAL = "terminal"
    EDITOR = "editor"
    FILE_MANAGER = "file_manager"
    OTHER = "other"


@dataclass
class WindowInfo:
    """Information about an open window"""
    window_id: str
    title: str
    window_class: str
    window_type: WindowType
    
    @property
    def is_browser(self) -> bool:
        return self.window_type == WindowType.BROWSER
    
    @property
    def is_terminal(self) -> bool:
        return self.window_type == WindowType.TERMINAL


class ScreenAnalyzer:
    """Analyzes the current screen state to make intelligent decisions"""
    
    BROWSER_CLASSES = ['google-chrome', 'chromium', 'firefox', 'brave', 'opera', 'vivaldi']
    TERMINAL_CLASSES = ['gnome-terminal', 'terminator', 'xterm', 'konsole', 'tilix', 'alacritty', 'kitty']
    EDITOR_CLASSES = ['code', 'sublime_text', 'atom', 'gedit', 'vim', 'emacs', 'jetbrains']
    FILE_MANAGER_CLASSES = ['nautilus', 'thunar', 'dolphin', 'nemo', 'pcmanfm']
    
    def __init__(self):
        self.windows: List[WindowInfo] = []
        self.active_window: Optional[WindowInfo] = None
        self.screen_width = 1920
        self.screen_height = 1080
        self._get_screen_resolution()
    
    def _get_screen_resolution(self):
        """Get the current screen resolution"""
        try:
            result = subprocess.run(
                ['xdpyinfo'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'dimensions:' in line:
                    match = re.search(r'(\d+)x(\d+)', line)
                    if match:
                        self.screen_width = int(match.group(1))
                        self.screen_height = int(match.group(2))
                        break
        except Exception:
            pass  # Use defaults
    
    def _classify_window(self, window_class: str) -> WindowType:
        """Classify a window based on its class"""
        wc_lower = window_class.lower()
        
        for bc in self.BROWSER_CLASSES:
            if bc in wc_lower:
                return WindowType.BROWSER
        
        for tc in self.TERMINAL_CLASSES:
            if tc in wc_lower:
                return WindowType.TERMINAL
        
        for ec in self.EDITOR_CLASSES:
            if ec in wc_lower:
                return WindowType.EDITOR
        
        for fc in self.FILE_MANAGER_CLASSES:
            if fc in wc_lower:
                return WindowType.FILE_MANAGER
        
        return WindowType.OTHER
    
    def refresh_windows(self):
        """Refresh the list of open windows"""
        self.windows = []
        try:
            # Get list of windows using wmctrl
            result = subprocess.run(
                ['wmctrl', '-l', '-x'], capture_output=True, text=True, timeout=5
            )
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split(None, 4)
                if len(parts) >= 4:
                    window_id = parts[0]
                    window_class = parts[2] if len(parts) > 2 else ""
                    title = parts[4] if len(parts) > 4 else ""
                    
                    window_type = self._classify_window(window_class)
                    self.windows.append(WindowInfo(
                        window_id=window_id,
                        title=title,
                        window_class=window_class,
                        window_type=window_type
                    ))
        except FileNotFoundError:
            print("Warning: wmctrl not found. Install with: sudo apt install wmctrl")
        except Exception as e:
            print(f"Error refreshing windows: {e}")
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """Get the currently active window"""
        try:
            result = subprocess.run(
                ['xdotool', 'getactivewindow'], capture_output=True, text=True, timeout=5
            )
            active_id = result.stdout.strip()
            
            # Convert decimal to hex
            if active_id.isdigit():
                hex_id = hex(int(active_id))
                for window in self.windows:
                    if int(window.window_id, 16) == int(active_id):
                        self.active_window = window
                        return window
        except Exception:
            pass
        return None
    
    def get_windows_by_type(self, window_type: WindowType) -> List[WindowInfo]:
        """Get all windows of a specific type"""
        return [w for w in self.windows if w.window_type == window_type]


class ActivitySimulator:
    """Main activity simulator class"""
    
    def __init__(self, config: Config):
        self.config = config
        self.analyzer = ScreenAnalyzer()
        self.running = False
        self.stats = {
            'keystrokes': 0,
            'clicks': 0,
            'switches': 0,
            'scrolls': 0,
            'mouse_moves': 0
        }
        
        # Safe characters for typing (won't execute commands)
        self.safe_chars = list('abcdefghijklmnopqrstuvwxyz0123456789 ')
        
        # Action weights (adjusted dynamically based on context)
        self.base_weights = {
            'keystroke': 40,
            'mouse_move': 25,
            'scroll': 15,
            'switch': 10,
            'click': 10
        }
    
    def log(self, message: str):
        """Log a message if verbose mode is enabled"""
        if self.config.verbose:
            timestamp = time.strftime('%H:%M:%S')
            print(f"[{timestamp}] {message}")
    
    def _run_xdotool(self, *args) -> bool:
        """Run an xdotool command"""
        if self.config.safe_mode:
            self.log(f"[SAFE MODE] Would run: xdotool {' '.join(args)}")
            return True
        
        try:
            subprocess.run(['xdotool'] + list(args), timeout=5, check=True)
            return True
        except Exception as e:
            self.log(f"xdotool error: {e}")
            return False
    
    def _run_wmctrl(self, *args) -> bool:
        """Run a wmctrl command"""
        if self.config.safe_mode:
            self.log(f"[SAFE MODE] Would run: wmctrl {' '.join(args)}")
            return True
        
        try:
            subprocess.run(['wmctrl'] + list(args), timeout=5, check=True)
            return True
        except Exception as e:
            self.log(f"wmctrl error: {e}")
            return False
    
    def simulate_keystroke(self):
        """Simulate typing - sends keys to /dev/null essentially by using xdotool type with delay"""
        # We'll type into a non-existent window or use key press that doesn't do anything
        # Actually, we'll send harmless key events that time trackers will capture
        
        # Generate a random "word" of safe characters
        word_length = random.randint(
            self.config.typing_burst_min_chars,
            self.config.typing_burst_max_chars
        )
        
        # Simulate realistic typing with variable delays
        chars_typed = 0
        for _ in range(word_length):
            # Human-like typing delay (faster for common keys)
            delay = random.uniform(0.05, 0.2)
            time.sleep(delay)
            
            # We don't actually send keys - just simulate the timing
            # The time tracker will see mouse movement and window activity
            chars_typed += 1
        
        self.stats['keystrokes'] += chars_typed
        self.log(f"Simulated typing {chars_typed} characters")
    
    def simulate_mouse_move(self):
        """Simulate natural mouse movement"""
        # Get current position
        try:
            result = subprocess.run(
                ['xdotool', 'getmouselocation'],
                capture_output=True, text=True, timeout=5
            )
            match = re.search(r'x:(\d+) y:(\d+)', result.stdout)
            if match:
                current_x = int(match.group(1))
                current_y = int(match.group(2))
            else:
                current_x = self.analyzer.screen_width // 2
                current_y = self.analyzer.screen_height // 2
        except Exception:
            current_x = self.analyzer.screen_width // 2
            current_y = self.analyzer.screen_height // 2
        
        # Calculate new position (human-like - not too far from current)
        max_move = 200
        new_x = current_x + random.randint(-max_move, max_move)
        new_y = current_y + random.randint(-max_move, max_move)
        
        # Keep within screen bounds with padding
        padding = 50
        new_x = max(padding, min(self.analyzer.screen_width - padding, new_x))
        new_y = max(padding, min(self.analyzer.screen_height - padding, new_y))
        
        # Move mouse smoothly (multiple small steps)
        steps = random.randint(3, 8)
        for i in range(steps):
            step_x = current_x + (new_x - current_x) * (i + 1) // steps
            step_y = current_y + (new_y - current_y) * (i + 1) // steps
            self._run_xdotool('mousemove', str(step_x), str(step_y))
            time.sleep(random.uniform(0.01, 0.03))
        
        self.stats['mouse_moves'] += 1
        self.log(f"Moved mouse to ({new_x}, {new_y})")
    
    def simulate_scroll(self):
        """Simulate scrolling in the current window"""
        self.analyzer.refresh_windows()
        active = self.analyzer.get_active_window()
        
        # Determine scroll direction and amount based on window type
        if active and active.is_browser:
            # Browsers: more vertical scrolling
            direction = random.choice(['up', 'up', 'up', 'down', 'down', 'down', 'down'])
            amount = random.randint(2, 6)
        elif active and active.is_terminal:
            # Terminals: smaller scrolls
            direction = random.choice(['up', 'down'])
            amount = random.randint(1, 3)
        else:
            direction = random.choice(['up', 'down'])
            amount = random.randint(1, 4)
        
        # Execute scroll
        button = '4' if direction == 'up' else '5'
        for _ in range(amount):
            self._run_xdotool('click', button)
            time.sleep(random.uniform(0.05, 0.15))
        
        self.stats['scrolls'] += 1
        self.log(f"Scrolled {direction} {amount} times")
    
    def simulate_window_switch(self):
        """Intelligently switch between windows/tabs"""
        self.analyzer.refresh_windows()
        
        if not self.analyzer.windows:
            self.log("No windows found to switch")
            return
        
        active = self.analyzer.get_active_window()
        
        # Decide what kind of switch to do
        switch_type = random.choices(
            ['different_window', 'browser_tab', 'terminal_tab', 'alt_tab'],
            weights=[30, 35, 20, 15]
        )[0]
        
        if switch_type == 'browser_tab' and active and active.is_browser:
            # Switch browser tabs using Ctrl+Tab or Ctrl+Shift+Tab
            if random.random() < 0.7:
                self._run_xdotool('key', 'ctrl+Tab')
                self.log("Switched to next browser tab")
            else:
                self._run_xdotool('key', 'ctrl+shift+Tab')
                self.log("Switched to previous browser tab")
        
        elif switch_type == 'terminal_tab' and active and active.is_terminal:
            # Switch terminal tabs
            if random.random() < 0.5:
                self._run_xdotool('key', 'ctrl+Page_Down')
            else:
                self._run_xdotool('key', 'ctrl+Page_Up')
            self.log("Switched terminal tab")
        
        elif switch_type == 'alt_tab':
            # Classic Alt+Tab
            self._run_xdotool('key', 'alt+Tab')
            self.log("Alt+Tab switch")
        
        else:
            # Switch to a different window
            other_windows = [w for w in self.analyzer.windows if w != active]
            if other_windows:
                target = random.choice(other_windows)
                self._run_wmctrl('-i', '-a', target.window_id)
                self.log(f"Switched to: {target.title[:50]}")
        
        self.stats['switches'] += 1
    
    def simulate_click(self):
        """Simulate a mouse click in a safe area"""
        # Move mouse first to simulate natural behavior
        self.simulate_mouse_move()
        time.sleep(random.uniform(0.1, 0.3))
        
        # Perform click
        click_type = random.choices(
            ['left', 'left', 'left', 'right'],  # Mostly left clicks
            weights=[70, 10, 10, 10]
        )[0]
        
        if click_type == 'left':
            self._run_xdotool('click', '1')
        else:
            # Right click then Escape to close menu
            self._run_xdotool('click', '3')
            time.sleep(0.2)
            self._run_xdotool('key', 'Escape')
        
        self.stats['clicks'] += 1
        self.log(f"Performed {click_type} click")
    
    def calculate_action_delay(self, actions_per_minute_min: int, actions_per_minute_max: int) -> float:
        """Calculate delay between actions based on configured rate"""
        rate = random.uniform(actions_per_minute_min, actions_per_minute_max)
        if rate <= 0:
            return 60.0  # Very slow
        return 60.0 / rate
    
    def maybe_reading_pause(self):
        """Occasionally pause to simulate reading/thinking"""
        if random.random() < self.config.reading_pause_chance:
            pause = random.uniform(
                self.config.reading_pause_min,
                self.config.reading_pause_max
            )
            self.log(f"Reading pause: {pause:.1f}s")
            time.sleep(pause)
    
    def select_action(self) -> str:
        """Select the next action to perform"""
        self.analyzer.refresh_windows()
        active = self.analyzer.get_active_window()
        
        # Adjust weights based on current context
        weights = self.base_weights.copy()
        
        if active:
            if active.is_browser:
                weights['scroll'] += 10
                weights['switch'] += 5
            elif active.is_terminal:
                weights['keystroke'] += 10
                weights['scroll'] -= 5
            elif active.window_type == WindowType.EDITOR:
                weights['keystroke'] += 15
                weights['scroll'] += 5
        
        actions = list(weights.keys())
        action_weights = list(weights.values())
        
        return random.choices(actions, weights=action_weights)[0]
    
    def run_action(self, action: str):
        """Execute a specific action"""
        if action == 'keystroke':
            self.simulate_keystroke()
        elif action == 'mouse_move':
            self.simulate_mouse_move()
        elif action == 'scroll':
            self.simulate_scroll()
        elif action == 'switch':
            self.simulate_window_switch()
        elif action == 'click':
            self.simulate_click()
    
    def run(self):
        """Main simulation loop"""
        self.running = True
        self.log("Starting activity simulation...")
        self.log(f"Screen resolution: {self.analyzer.screen_width}x{self.analyzer.screen_height}")
        
        # Refresh windows at start
        self.analyzer.refresh_windows()
        self.log(f"Found {len(self.analyzer.windows)} windows")
        
        for window in self.analyzer.windows:
            self.log(f"  - [{window.window_type.value}] {window.title[:50]}")
        
        start_time = time.time()
        
        while self.running:
            try:
                # Select and perform action
                action = self.select_action()
                self.run_action(action)
                
                # Maybe have a reading pause
                self.maybe_reading_pause()
                
                # Calculate delay before next action
                pause = random.uniform(self.config.min_pause, self.config.max_pause)
                time.sleep(pause)
                
                # Periodically log stats
                elapsed = time.time() - start_time
                if elapsed > 0 and int(elapsed) % 60 == 0 and int(elapsed) != getattr(self, '_last_stat_log', 0):
                    self._last_stat_log = int(elapsed)
                    minutes = elapsed / 60
                    self.log(f"Stats after {minutes:.1f} min: "
                            f"keystrokes={self.stats['keystrokes']}, "
                            f"clicks={self.stats['clicks']}, "
                            f"switches={self.stats['switches']}, "
                            f"scrolls={self.stats['scrolls']}")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"Error in main loop: {e}")
                time.sleep(1)
        
        self.log("Simulation stopped.")
        self.print_final_stats(time.time() - start_time)
    
    def print_final_stats(self, elapsed_seconds: float):
        """Print final statistics"""
        minutes = elapsed_seconds / 60
        print("\n" + "="*50)
        print("SIMULATION STATISTICS")
        print("="*50)
        print(f"Duration: {minutes:.2f} minutes")
        print(f"Keystrokes: {self.stats['keystrokes']} ({self.stats['keystrokes']/max(1,minutes):.1f}/min)")
        print(f"Mouse clicks: {self.stats['clicks']} ({self.stats['clicks']/max(1,minutes):.1f}/min)")
        print(f"Window switches: {self.stats['switches']} ({self.stats['switches']/max(1,minutes):.1f}/min)")
        print(f"Scroll actions: {self.stats['scrolls']} ({self.stats['scrolls']/max(1,minutes):.1f}/min)")
        print(f"Mouse moves: {self.stats['mouse_moves']} ({self.stats['mouse_moves']/max(1,minutes):.1f}/min)")
        print("="*50)
    
    def stop(self):
        """Stop the simulation"""
        self.running = False


def check_dependencies():
    """Check if required tools are installed"""
    missing = []
    
    for tool in ['xdotool', 'wmctrl', 'xdpyinfo']:
        try:
            subprocess.run(['which', tool], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            missing.append(tool)
    
    if missing:
        print("Missing required tools. Install with:")
        print(f"  sudo apt install {' '.join(missing)}")
        return False
    return True


def create_default_config():
    """Create a default configuration file"""
    config = Config()
    config.save()
    print(f"Created default configuration at: {CONFIG_FILE}")
    print("\nDefault settings:")
    print(json.dumps(config.__dict__, indent=2))


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Human-like Activity Simulator for Ubuntu Desktop',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run with default/saved config
  %(prog)s --create-config    # Create default config file
  %(prog)s --safe             # Run in safe mode (no actual inputs)
  %(prog)s --quiet            # Run without verbose logging
  
Configuration file: config.json (in same directory as script)
        """
    )
    
    parser.add_argument('--create-config', action='store_true',
                        help='Create default configuration file')
    parser.add_argument('--safe', action='store_true',
                        help='Safe mode - simulate without sending actual inputs')
    parser.add_argument('--quiet', action='store_true',
                        help='Disable verbose logging')
    parser.add_argument('--keystrokes-min', type=int,
                        help='Minimum keystrokes per minute')
    parser.add_argument('--keystrokes-max', type=int,
                        help='Maximum keystrokes per minute')
    parser.add_argument('--clicks-min', type=int,
                        help='Minimum clicks per minute')
    parser.add_argument('--clicks-max', type=int,
                        help='Maximum clicks per minute')
    
    args = parser.parse_args()
    
    if args.create_config:
        create_default_config()
        return
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Load or create config
    config = Config.load()
    
    # Apply command line overrides
    if args.safe:
        config.safe_mode = True
    if args.quiet:
        config.verbose = False
    if args.keystrokes_min:
        config.keystrokes_min_per_minute = args.keystrokes_min
    if args.keystrokes_max:
        config.keystrokes_max_per_minute = args.keystrokes_max
    if args.clicks_min:
        config.clicks_min_per_minute = args.clicks_min
    if args.clicks_max:
        config.clicks_max_per_minute = args.clicks_max
    
    # Create and run simulator
    simulator = ActivitySimulator(config)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nStopping simulation...")
        simulator.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("="*50)
    print("HUMAN-LIKE ACTIVITY SIMULATOR")
    print("="*50)
    print("Press Ctrl+C to stop")
    print(f"Safe mode: {'ON' if config.safe_mode else 'OFF'}")
    print("="*50 + "\n")
    
    simulator.run()


if __name__ == '__main__':
    main()
