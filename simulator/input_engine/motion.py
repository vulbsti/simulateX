"""Physics-based mouse movement using cubic Bézier curves."""
import math
import random
import time
from typing import Tuple
from simulator.utils import get_mouse_pos, move_mouse_raw


def _cubic_bezier(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    """Evaluate cubic Bézier at parameter t."""
    mt = 1 - t
    return (
        mt**3 * p0
        + 3 * mt**2 * t * p1
        + 3 * mt * t**2 * p2
        + t**3 * p3
    )


def _ease_in_out_sine(t: float) -> float:
    """Smooth velocity profile: slow start, fast middle, slow end."""
    return 0.5 * (1 - math.cos(math.pi * t))


def bezier_move(
    target_x: int,
    target_y: int,
    duration: float = 0.6,
    overshoot_prob: float = 0.12,
) -> Tuple[int, int]:
    """Move mouse from current position to target using a human-like
    cubic Bézier curve with ease-in-out velocity, Gaussian hand-tremor,
    and occasional overshoot-and-correct.

    Returns the final (x, y) coordinate.
    """
    x0, y0 = get_mouse_pos()
    x3, y3 = float(target_x), float(target_y)

    dx = x3 - x0
    dy = y3 - y0
    dist = math.hypot(dx, dy)
    if dist < 5:
        return int(x3), int(y3)

    # Control points with perpendicular curvature (~15% of distance)
    perp_x, perp_y = -dy / dist, dx / dist
    curvature = dist * random.gauss(0.15, 0.06)

    x1 = x0 + dx * 0.35 + perp_x * curvature
    y1 = y0 + dy * 0.35 + perp_y * curvature
    x2 = x3 - dx * 0.30 + perp_x * curvature
    y2 = y3 - dy * 0.30 + perp_y * curvature

    # Target 60Hz update rate; at least 15 steps
    steps = max(15, int(duration * 60.0))
    step_dt = duration / steps

    for i in range(steps):
        t = i / steps
        t_vel = _ease_in_out_sine(t)
        x = _cubic_bezier(t_vel, x0, x1, x2, x3)
        y = _cubic_bezier(t_vel, y0, y1, y2, y3)

        # Hand tremor (sub-pixel jitter)
        x += random.gauss(0.0, 0.4)
        y += random.gauss(0.0, 0.4)

        move_mouse_raw(int(x), int(y))
        time.sleep(step_dt)

    # Overshoot with 12% probability
    if random.random() < overshoot_prob:
        overshoot_x = x3 + dx * random.uniform(0.05, 0.18)
        overshoot_y = y3 + dy * random.uniform(0.05, 0.18)
        # Quick overshoot
        bezier_move(int(overshoot_x), int(overshoot_y), duration=0.12, overshoot_prob=0.0)
        time.sleep(random.uniform(0.06, 0.18))
        # Correct back
        bezier_move(int(x3), int(y3), duration=0.18, overshoot_prob=0.0)
        return int(x3), int(y3)

    return int(x3), int(y3)


def small_nudge() -> Tuple[int, int]:
    """Small, safe mouse movement within ~100px of current position.
    Used during idle simulation to avoid fighting the user."""
    x0, y0 = get_mouse_pos()
    max_nudge = 100
    tx = x0 + random.randint(-max_nudge, max_nudge)
    ty = y0 + random.randint(-max_nudge, max_nudge)
    return bezier_move(tx, ty, duration=random.uniform(0.3, 0.6), overshoot_prob=0.0)
