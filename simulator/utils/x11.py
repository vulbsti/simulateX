"""Robust wrappers around xdotool, wmctrl, and xrandr.
Handles subprocess failures, timeouts, and normalizes window IDs to integers.
"""
import subprocess
import re
import time
from typing import List, Tuple, Optional, Dict

class X11Error(Exception):
    pass


def run_cmd(args: List[str], timeout: float = 5.0, check: bool = False) -> subprocess.CompletedProcess:
    """Run a command, swallowing common X11 errors gracefully."""
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=check
        )
    except subprocess.TimeoutExpired as e:
        raise X11Error(f"Command timed out: {' '.join(args)}") from e
    except FileNotFoundError as e:
        raise X11Error(f"Binary not found: {args[0]}") from e


def xdotool(*args) -> subprocess.CompletedProcess:
    return run_cmd(['xdotool'] + list(args))


def wmctrl(*args) -> subprocess.CompletedProcess:
    return run_cmd(['wmctrl'] + list(args))


def xrandr() -> subprocess.CompletedProcess:
    return run_cmd(['xrandr'])


def get_mouse_pos() -> Tuple[int, int]:
    """Return current mouse (x, y) or center of primary screen on failure."""
    result = xdotool('getmouselocation')
    match = re.search(r'x:(\d+)\s+y:(\d+)', result.stdout)
    if match:
        return int(match.group(1)), int(match.group(2))
    # fallback
    w, h = get_primary_screen_size()
    return w // 2, h // 2


def move_mouse_raw(x: int, y: int):
    xdotool('mousemove', str(int(x)), str(int(y)))


def click_button(button: str):
    xdotool('click', button)


def send_key(keyspec: str):
    """Send a key or key combo, e.g. 'ctrl+s', 'BackSpace', 'alt+Tab'."""
    xdotool('key', keyspec)


def type_text(text: str):
    """Type a string literally. Be careful with shell metacharacters."""
    xdotool('type', '--delay', '0', text)


def get_active_window_id() -> Optional[int]:
    """Return active window ID as integer (decimal), or None."""
    result = xdotool('getactivewindow')
    out = result.stdout.strip()
    if out.isdigit():
        return int(out)
    return None


def get_window_list() -> List[Dict]:
    """Return list of window dicts with normalized integer IDs."""
    result = wmctrl('-l', '-x')
    windows = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        raw_id = parts[0]
        try:
            win_id = int(raw_id, 16) if raw_id.startswith('0x') else int(raw_id)
        except ValueError:
            continue
        window_class = parts[2] if len(parts) > 2 else ""
        title = parts[4] if len(parts) > 4 else ""
        windows.append({
            'id': win_id,
            'hex_id': f"0x{win_id:08x}",
            'class': window_class,
            'title': title,
        })
    return windows


def focus_window(win_id: int) -> bool:
    """Activate a window by integer ID."""
    result = xdotool('windowactivate', '--sync', str(win_id))
    return result.returncode == 0


def get_primary_screen_size() -> Tuple[int, int]:
    """Return (width, height) of primary screen."""
    result = xrandr()
    # Look for primary line:  "DP-1 connected primary 2560x1440+0+0 ..."
    for line in result.stdout.splitlines():
        if 'primary' in line and 'connected' in line:
            match = re.search(r'(\d+)x(\d+)\+', line)
            if match:
                return int(match.group(1)), int(match.group(2))
    # Fallback: xdpyinfo
    try:
        r2 = run_cmd(['xdpyinfo'])
        for line in r2.stdout.splitlines():
            if 'dimensions:' in line:
                match = re.search(r'(\d+)x(\d+)', line)
                if match:
                    return int(match.group(1)), int(match.group(2))
    except X11Error:
        pass
    return 1920, 1080


def get_all_monitors() -> List[Dict]:
    """Return list of monitors with geometry."""
    result = xrandr()
    monitors = []
    for line in result.stdout.splitlines():
        if ' connected ' in line:
            # e.g. "DP-1 connected primary 2560x1440+0+0 ..."
            name = line.split()[0]
            primary = 'primary' in line
            match = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', line)
            if match:
                monitors.append({
                    'name': name,
                    'primary': primary,
                    'width': int(match.group(1)),
                    'height': int(match.group(2)),
                    'x': int(match.group(3)),
                    'y': int(match.group(4)),
                })
    return monitors


def get_window_geometry(win_id: int) -> Optional[Dict]:
    """Return window absolute geometry {x,y,width,height} or None."""
    result = xdotool('getwindowgeometry', str(win_id))
    pos_match = re.search(r'Position:\s*(\d+),(\d+)', result.stdout)
    size_match = re.search(r'Geometry:\s*(\d+)x(\d+)', result.stdout)
    if pos_match and size_match:
        return {
            'x': int(pos_match.group(1)),
            'y': int(pos_match.group(2)),
            'width': int(size_match.group(1)),
            'height': int(size_match.group(2)),
        }
    return None
