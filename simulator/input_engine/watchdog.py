"""Real user input detection. When the user moves mouse or types,
the simulator must pause to avoid fighting for control."""
import subprocess
import threading
import time
import re
from typing import Optional


class InputWatchdog:
    """Monitors mouse and keyboard to detect real user activity.

    Usage:
        watchdog = InputWatchdog(mouse_threshold_px=5, idle_timeout_sec=3.0)
        watchdog.start()
        ...
        if watchdog.is_user_active:
            # don't simulate
        ...
        watchdog.stop()
    """

    def __init__(self, mouse_threshold_px: int = 5, idle_timeout_sec: float = 3.0):
        self.mouse_threshold = mouse_threshold_px
        self.idle_timeout = idle_timeout_sec
        self.last_activity = time.time()
        self.last_mouse_pos: Optional[tuple] = None
        self.running = False
        self._threads: list = []
        self._stop_event = threading.Event()

    def start(self):
        self.running = True
        self._stop_event.clear()
        self.last_activity = time.time()

        t_mouse = threading.Thread(target=self._mouse_loop, daemon=True)
        t_mouse.start()
        self._threads.append(t_mouse)

        t_kbd = threading.Thread(target=self._keyboard_loop, daemon=True)
        t_kbd.start()
        self._threads.append(t_kbd)

    def stop(self):
        self.running = False
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=1.0)
        self._threads.clear()

    @property
    def is_user_active(self) -> bool:
        """True if the user has moved mouse or typed recently."""
        return (time.time() - self.last_activity) < self.idle_timeout

    @property
    def seconds_since_activity(self) -> float:
        return time.time() - self.last_activity

    def poke(self):
        """Manually mark user as active (e.g., when simulation performs
        a window switch and the user might have noticed)."""
        self.last_activity = time.time()

    def _mouse_loop(self):
        """Poll mouse position at 10 Hz. If moved beyond threshold,
        mark user as active."""
        poll_interval = 0.1
        while not self._stop_event.is_set():
            try:
                result = subprocess.run(
                    ['xdotool', 'getmouselocation'],
                    capture_output=True, text=True, timeout=0.5
                )
                m = re.search(r'x:(\d+)\s+y:(\d+)', result.stdout)
                if m:
                    pos = (int(m.group(1)), int(m.group(2)))
                    if self.last_mouse_pos is not None:
                        dx = abs(pos[0] - self.last_mouse_pos[0])
                        dy = abs(pos[1] - self.last_mouse_pos[1])
                        if dx > self.mouse_threshold or dy > self.mouse_threshold:
                            self.last_activity = time.time()
                    self.last_mouse_pos = pos
            except Exception:
                pass
            self._stop_event.wait(poll_interval)

    def _keyboard_loop(self):
        """Monitor keyboard via xinput test. Any keypress = user active."""
        kbd_id = self._find_keyboard_id()
        if kbd_id is None:
            return

        proc = None
        try:
            proc = subprocess.Popen(
                ['xinput', 'test', kbd_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            while not self._stop_event.is_set():
                # Use select/poll to read with timeout so we can exit promptly
                import select
                if proc.poll() is not None:
                    break
                ready, _, _ = select.select([proc.stdout], [], [], 0.2)
                if ready:
                    line = proc.stdout.readline()
                    if 'key press' in line or 'key release' in line:
                        self.last_activity = time.time()
        except Exception:
            pass
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def _find_keyboard_id(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ['xinput', 'list'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if 'keyboard' in line.lower() and 'id=' in line.lower():
                    m = re.search(r'id=(\d+)', line)
                    if m:
                        return m.group(1)
            # fallback: master keyboard
            for line in result.stdout.splitlines():
                if 'master keyboard' in line.lower():
                    m = re.search(r'id=(\d+)', line)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        return None
