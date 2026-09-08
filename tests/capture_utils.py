"""Real-time X11 capture utilities for evaluating simulator behavior."""
import subprocess
import threading
import time
import re
from typing import List, Tuple, Optional, Dict, Callable
from dataclasses import dataclass, field


@dataclass
class MouseSample:
    t: float
    x: int
    y: int


@dataclass
class KeyEvent:
    t: float
    event_type: str  # 'press' or 'release'
    keycode: int


@dataclass
class WindowEvent:
    t: float
    win_id: Optional[int]


class MouseCapture:
    """Polls mouse position at high frequency to build movement tracks."""

    def __init__(self, poll_hz: float = 100.0):
        self.poll_interval = 1.0 / poll_hz
        self.samples: List[MouseSample] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self._stop.clear()
        self.samples = []
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> List[MouseSample]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        return self.samples

    def _loop(self):
        while not self._stop.is_set():
            try:
                result = subprocess.run(
                    ['xdotool', 'getmouselocation'],
                    capture_output=True, text=True, timeout=0.5
                )
                m = re.search(r'x:(\d+)\s+y:(\d+)', result.stdout)
                if m:
                    self.samples.append(MouseSample(
                        t=time.time(),
                        x=int(m.group(1)),
                        y=int(m.group(2))
                    ))
            except Exception:
                pass
            time.sleep(self.poll_interval)


class KeyboardCapture:
    """Captures key events via xinput test."""

    def __init__(self):
        self.events: List[KeyEvent] = []
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _find_keyboard_id(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ['xinput', 'list'], capture_output=True, text=True, timeout=5
            )
            # Look for lines containing "keyboard" or "Keyboard"
            for line in result.stdout.splitlines():
                if 'keyboard' in line.lower() and 'id=' in line.lower():
                    m = re.search(r'id=(\d+)', line)
                    if m:
                        return m.group(1)
            # Fallback: find first device with "key" in name
            for line in result.stdout.splitlines():
                if 'master keyboard' in line.lower():
                    m = re.search(r'id=(\d+)', line)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        return None

    def start(self):
        self.events = []
        self._stop.clear()
        kbd_id = self._find_keyboard_id()
        if kbd_id is None:
            raise RuntimeError("Could not find keyboard device via xinput")

        self._proc = subprocess.Popen(
            ['xinput', 'test', kbd_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        if self._proc is None or self._proc.stdout is None:
            return
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            # Lines look like: "key press   36" or "key release 36"
            m = re.search(r'key\s+(press|release)\s+(\d+)', line)
            if m:
                self.events.append(KeyEvent(
                    t=time.time(),
                    event_type=m.group(1),
                    keycode=int(m.group(2))
                ))

    def stop(self) -> List[KeyEvent]:
        self._stop.set()
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._thread:
            self._thread.join(timeout=2)
        return self.events


class WindowFocusCapture:
    """Polls active window ID to track focus changes."""

    def __init__(self, poll_hz: float = 10.0):
        self.poll_interval = 1.0 / poll_hz
        self.events: List[WindowEvent] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        self._stop.clear()
        self.events = []
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> List[WindowEvent]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        return self.events

    def _loop(self):
        while not self._stop.is_set():
            try:
                result = subprocess.run(
                    ['xdotool', 'getactivewindow'],
                    capture_output=True, text=True, timeout=0.5
                )
                out = result.stdout.strip()
                win_id = int(out) if out.isdigit() else None
                self.events.append(WindowEvent(t=time.time(), win_id=win_id))
            except Exception:
                self.events.append(WindowEvent(t=time.time(), win_id=None))
            time.sleep(self.poll_interval)


class EvaluationHarness:
    """Orchestrates multiple capture backends during a test run."""

    def __init__(self):
        self.mouse = MouseCapture(poll_hz=100.0)
        self.keyboard = KeyboardCapture()
        self.focus = WindowFocusCapture(poll_hz=10.0)

    def start_all(self):
        self.mouse.start()
        try:
            self.keyboard.start()
        except RuntimeError as e:
            print(f"Warning: keyboard capture unavailable: {e}")
        self.focus.start()

    def stop_all(self) -> Dict[str, List]:
        return {
            'mouse': self.mouse.stop(),
            'keyboard': self.keyboard.stop(),
            'focus': self.focus.stop(),
        }


def check_display_available() -> bool:
    """Return True if we have an X11 display available."""
    try:
        result = subprocess.run(
            ['xdotool', 'getmouselocation'],
            capture_output=True, text=True, timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False
