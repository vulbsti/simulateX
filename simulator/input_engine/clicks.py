"""Semantic, safety-aware click generation."""
import random
import time
from typing import Optional, Tuple
from simulator.input_engine.motion import bezier_move
from simulator.utils import click_button, send_key, get_window_geometry
from simulator.context.screen import ScreenManager
from simulator.context.windows import WindowInfo


class ClickPlanner:
    """Plans clicks that avoid danger zones and respect window context."""

    def __init__(self, screen: ScreenManager):
        self.screen = screen

    def click_in_window(self, window: Optional[WindowInfo],
                        button: str = '1',
                        double: bool = False) -> bool:
        """Move to a safe point inside a window and click.
        Returns True if a click was performed.
        """
        if window is None:
            return False
        geo = get_window_geometry(window.id)
        if geo is None:
            return False

        point = self.screen.safe_point_in_window(
            geo['x'], geo['y'], geo['width'], geo['height']
        )
        if point is None:
            return False

        px, py = point
        bezier_move(px, py, duration=random.uniform(0.4, 0.9))
        time.sleep(random.uniform(0.08, 0.25))

        if double:
            click_button(button)
            time.sleep(random.uniform(0.08, 0.16))
            click_button(button)
        else:
            click_button(button)

        return True

    def safe_click_anywhere(self) -> Optional[Tuple[int, int]]:
        """Fallback: pick a random safe coordinate on primary monitor."""
        mx, my, mw, mh = self.screen.get_bounds()
        padding = 60
        for _ in range(50):
            x = mx + padding + random.randint(0, max(10, mw - padding * 2))
            y = my + padding + random.randint(0, max(10, mh - padding * 2))
            if self.screen.is_safe_coordinate(x, y):
                bezier_move(x, y, duration=random.uniform(0.5, 1.0))
                time.sleep(random.uniform(0.1, 0.3))
                click_button('1')
                return x, y
        return None

    def right_click_and_dismiss(self, window: Optional[WindowInfo]):
        """Right-click safely, then press Escape to dismiss menu."""
        if self.click_in_window(window, button='3'):
            time.sleep(0.3)
            send_key('Escape')
