"""Constant background mouse tremor to mimic a real hand on a mouse.

Real humans never hold the mouse completely still. There are constant
micro-adjustments (1-3px) every 100-500ms while reading, thinking, etc.

TimeDoctor and similar apps typically count "mouse movements" by polling
cursor position every 1-5 seconds. If the mouse is completely still during
the entire poll interval, no movement is counted. A constant tremor ensures
the cursor is always slightly in motion.
"""
import random
import time
import threading
from typing import Optional, Callable


class TremorThread:
    """Background thread that generates tiny mouse movements.

    Uses uinput (preferred) for kernel-level relative motion events,
    or falls back to xdotool mousemove_relative.
    """

    def __init__(self,
                 move_func: Callable[[int, int], None],
                 min_interval: float = 0.05,
                 max_interval: float = 0.30,
                 max_amplitude: int = 3,
                 should_pause: Optional[Callable[[], bool]] = None):
        """
        Args:
            move_func: callable(dx, dy) that moves the mouse relatively.
            min_interval: shortest sleep between micro-moves (seconds)
            max_interval: longest sleep between micro-moves (seconds)
            max_amplitude: max pixels per micro-move
            should_pause: optional callable returning True to pause tremor
        """
        self.move_func = move_func
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.max_amplitude = max_amplitude
        self.should_pause = should_pause

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.stats = {'moves': 0}

    def start(self):
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self):
        while not self._stop_event.is_set():
            if self.should_pause and self.should_pause():
                self._stop_event.wait(0.2)
                continue
            dx = random.randint(-self.max_amplitude, self.max_amplitude)
            dy = random.randint(-self.max_amplitude, self.max_amplitude)
            if dx != 0 or dy != 0:
                try:
                    self.move_func(dx, dy)
                    self.stats['moves'] += 1
                except Exception:
                    pass
            # Sleep with jitter
            sleep_time = random.uniform(self.min_interval, self.max_interval)
            self._stop_event.wait(sleep_time)
