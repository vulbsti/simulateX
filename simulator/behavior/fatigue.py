"""Temporal modulation: circadian rhythm and session fatigue."""
import math
import random
import time
from datetime import datetime


class TemporalModel:
    """Modulates simulation parameters based on time-of-day and runtime fatigue."""

    def __init__(self):
        self._start_time = time.time()
        self._start_hour = datetime.now().hour

    @property
    def elapsed_minutes(self) -> float:
        return (time.time() - self._start_time) / 60.0

    def circadian_factor(self) -> float:
        """Productivity peaks around 10:00–11:00, dips after lunch."""
        hour = datetime.now().hour + datetime.now().minute / 60.0
        # Peak at 10.5, trough at 14.5, period ~24h
        return 0.75 + 0.25 * math.sin(2 * math.pi * (hour - 6) / 24)

    def fatigue_factor(self) -> float:
        """Fatigue accumulates over ~90 minutes, then plateaus."""
        return 1.0 - math.exp(-self.elapsed_minutes / 90.0)

    def focus_duration_range(self) -> tuple:
        """Return (min_sec, max_sec) for how long a DEEP_FOCUS state lasts."""
        circ = self.circadian_factor()
        fat = self.fatigue_factor()
        base_min, base_max = 120, 600
        adjusted_min = base_min * circ * (1 - fat * 0.4)
        adjusted_max = base_max * circ * (1 - fat * 0.5)
        return max(30, adjusted_min), max(60, adjusted_max)

    def break_probability(self) -> float:
        """Chance per minute of transitioning to a BREAK state."""
        fat = self.fatigue_factor()
        # Every ~30 min early on, every ~10 min when fatigued
        return 0.03 + fat * 0.07

    def reading_pause_duration(self) -> float:
        """Return seconds for a reading pause."""
        return random.uniform(2.0, 8.0) * (1 + self.fatigue_factor() * 0.5)

    def pause_between_actions(self) -> float:
        """Base inter-action delay, increases with fatigue."""
        return random.uniform(0.15, 1.2) * (1 + self.fatigue_factor() * 0.3)


