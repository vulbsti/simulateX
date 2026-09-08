"""Screen geometry, multi-monitor support, and danger zone calculation."""
from typing import List, Dict, Tuple, Optional
from simulator.utils import get_all_monitors, get_window_list, get_window_geometry


class ScreenManager:
    """Manages screen geometry and calculates forbidden click zones."""

    def __init__(self):
        self.monitors: List[Dict] = []
        self._refresh()

    def _refresh(self):
        self.monitors = get_all_monitors()
        if not self.monitors:
            self.monitors = [{'name': 'fallback', 'primary': True,
                              'width': 1920, 'height': 1080, 'x': 0, 'y': 0}]

    @property
    def primary(self) -> Dict:
        for m in self.monitors:
            if m.get('primary'):
                return m
        return self.monitors[0]

    def get_bounds(self, monitor_name: Optional[str] = None) -> Tuple[int, int, int, int]:
        """Return (x, y, width, height) for a monitor or primary."""
        m = self.primary if monitor_name is None else next(
            (x for x in self.monitors if x['name'] == monitor_name), self.primary
        )
        return m['x'], m['y'], m['width'], m['height']

    def danger_zones(self) -> List[Tuple[int, int, int, int]]:
        """Return list of (x, y, w, h) rectangles that are unsafe to click.
        Includes top 40px of every monitor (title bars) and known system areas.
        """
        zones = []
        for m in self.monitors:
            mx, my, mw, mh = m['x'], m['y'], m['width'], m['height']
            # Top bar / title bar area
            zones.append((mx, my, mw, 40))
            # Bottom dock area (common)
            zones.append((mx, my + mh - 40, mw, 40))
            # Top-right corner (close buttons on many DEs)
            zones.append((mx + mw - 120, my, 120, 40))
        return zones

    def is_safe_coordinate(self, x: int, y: int) -> bool:
        """Check if a coordinate is outside all danger zones."""
        for zx, zy, zw, zh in self.danger_zones():
            if zx <= x < zx + zw and zy <= y < zy + zh:
                return False
        return True

    def safe_point_in_window(self, wx: int, wy: int, ww: int, wh: int,
                             padding: int = 60) -> Optional[Tuple[int, int]]:
        """Return a random safe point inside a window's client area,
        avoiding edges and global danger zones.
        """
        import random
        inner_x = wx + padding
        inner_y = wy + padding
        inner_w = ww - padding * 2
        inner_h = wh - padding * 2
        if inner_w <= 0 or inner_h <= 0:
            return None
        for _ in range(20):
            px = inner_x + random.randint(0, inner_w)
            py = inner_y + random.randint(0, inner_h)
            if self.is_safe_coordinate(px, py):
                return px, py
        # Fallback: center
        cx, cy = wx + ww // 2, wy + wh // 2
        if self.is_safe_coordinate(cx, cy):
            return cx, cy
        return None
