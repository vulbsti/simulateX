"""Single hidden sandbox window for isolated typing.
Spawns at most ONE window, hides it off-screen, and reuses it.
"""
import subprocess
import time
from typing import Optional
from simulator.utils import get_window_list, focus_window, run_cmd


class SandboxWindow:
    """Manages a single dedicated hidden window to receive keystrokes."""

    TITLE_SUBSTRING = "__sim_sandbox__"
    # Off-screen coordinates to hide window from user view
    OFFSCREEN_X = -10000
    OFFSCREEN_Y = -10000

    def __init__(self):
        self._win_id: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None

    def spawn(self) -> Optional[int]:
        """Launch ONE background terminal and hide it off-screen."""
        existing = self._find_existing()
        if existing:
            self._win_id = existing
            self._hide()
            return existing

        # Try terminal emulators in order of preference
        term_cmds = [
            # xterm with iconic (minimized) start
            ['xterm', '-T', self.TITLE_SUBSTRING, '-iconic',
             '-bg', 'black', '-fg', 'green'],
            # gnome-terminal
            ['gnome-terminal', '--title', self.TITLE_SUBSTRING,
             '--hide-menubar', '--geometry=1x1+0+0'],
            # urxvt
            ['urxvt', '-title', self.TITLE_SUBSTRING, '-iconic'],
            # alacritty
            ['alacritty', '--title', self.TITLE_SUBSTRING],
            # kitty
            ['kitty', '--title', self.TITLE_SUBSTRING],
        ]

        for cmd in term_cmds:
            try:
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                # Wait for window to appear
                for _ in range(10):
                    time.sleep(0.3)
                    wid = self._find_existing()
                    if wid:
                        self._win_id = wid
                        self._hide()
                        return wid
                # Window never appeared; kill the process
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None
            except FileNotFoundError:
                continue

        return None

    def _find_existing(self) -> Optional[int]:
        for w in get_window_list():
            if self.TITLE_SUBSTRING in w.get('title', ''):
                return w['id']
        return None

    def _hide(self):
        """Move window off-screen so user never sees it."""
        if self._win_id is None:
            return
        try:
            # Minimize
            run_cmd(['xdotool', 'windowminimize', str(self._win_id)], timeout=2)
            # Move off-screen
            run_cmd(['xdotool', 'windowmove', str(self._win_id),
                     str(self.OFFSCREEN_X), str(self.OFFSCREEN_Y)], timeout=2)
        except Exception:
            pass

    @property
    def win_id(self) -> Optional[int]:
        if self._win_id is None:
            self._win_id = self._find_existing()
        return self._win_id

    def focus(self) -> bool:
        """Focus the sandbox window so keystrokes go there."""
        wid = self.win_id
        if wid is None:
            return False
        # Move on-screen briefly so the WM allows focus
        try:
            run_cmd(['xdotool', 'windowmove', str(wid), '0', '0'], timeout=2)
            result = focus_window(wid)
            return result
        except Exception:
            return False

    def unfocus(self):
        """Return window to hiding."""
        self._hide()

    def cleanup(self):
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
            self._win_id = None
