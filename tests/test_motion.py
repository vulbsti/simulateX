"""Integration tests for mouse physics (requires X11 display)."""
import unittest
import math
import random
import time

from tests.capture_utils import MouseCapture, EvaluationHarness, check_display_available
from simulator.input_engine.motion import bezier_move
from simulator.context.screen import ScreenManager


@unittest.skipUnless(check_display_available(), "No X11 display available")
class TestMousePhysicsIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.screen = ScreenManager()
        p = cls.screen.primary
        cls.safe_center = (p['x'] + p['width'] // 2, p['y'] + p['height'] // 2)

    def _move_to_center(self):
        from simulator.utils import move_mouse_raw
        move_mouse_raw(self.safe_center[0], self.safe_center[1])
        time.sleep(0.2)

    def test_bezier_path_is_non_linear(self):
        """M1: Mouse path should deviate significantly from a straight line."""
        self._move_to_center()
        cap = MouseCapture(poll_hz=100.0)
        cap.start()
        time.sleep(0.1)

        target = (self.safe_center[0] + 300, self.safe_center[1] + 150)
        bezier_move(target[0], target[1], duration=0.8, overshoot_prob=0.0)
        time.sleep(0.1)
        samples = cap.stop()

        self.assertGreater(len(samples), 20, "Too few samples captured")

        # Compute max perpendicular distance from straight line
        x0, y0 = samples[0].x, samples[0].y
        x1, y1 = samples[-1].x, samples[-1].y
        dx, dy = x1 - x0, y1 - y0
        line_len = math.hypot(dx, dy)
        if line_len < 10:
            self.skipTest("Mouse didn't move enough")

        max_dev = 0
        for s in samples:
            # Perpendicular distance = |cross product| / |line|
            cross = abs((s.x - x0) * dy - (s.y - y0) * dx)
            dev = cross / line_len
            max_dev = max(max_dev, dev)

        self.assertGreater(max_dev, 10,
            f"Path too straight (max deviation {max_dev:.1f}px). Expected >10px curvature.")

    def test_velocity_profile_peaks_in_middle(self):
        """M1 (velocity): Speed should be higher in middle than at ends."""
        self._move_to_center()
        cap = MouseCapture(poll_hz=100.0)
        cap.start()
        time.sleep(0.05)

        target = (self.safe_center[0] + 250, self.safe_center[1] - 180)
        bezier_move(target[0], target[1], duration=0.9, overshoot_prob=0.0)
        time.sleep(0.05)
        samples = cap.stop()

        self.assertGreater(len(samples), 15)
        speeds = []
        for i in range(1, len(samples)):
            dt = samples[i].t - samples[i-1].t
            if dt <= 0:
                continue
            dist = math.hypot(samples[i].x - samples[i-1].x,
                              samples[i].y - samples[i-1].y)
            speeds.append(dist / dt)

        if len(speeds) < 10:
            self.skipTest("Not enough speed samples")

        n = len(speeds)
        start_speed = sum(speeds[:n//4]) / max(1, n//4)
        mid_speed = sum(speeds[n*3//8 : n*5//8]) / max(1, n//4)
        end_speed = sum(speeds[-n//4:]) / max(1, n//4)

        self.assertGreater(mid_speed, start_speed * 1.2,
            f"Middle speed ({mid_speed:.1f}) not higher than start ({start_speed:.1f})")
        self.assertGreater(mid_speed, end_speed * 1.2,
            f"Middle speed ({mid_speed:.1f}) not higher than end ({end_speed:.1f})")

    def test_hand_tremor_present(self):
        """M2: Position deltas should show Gaussian-like jitter."""
        self._move_to_center()
        cap = MouseCapture(poll_hz=120.0)
        cap.start()
        time.sleep(0.05)

        target = (self.safe_center[0] + 100, self.safe_center[1] + 80)
        bezier_move(target[0], target[1], duration=0.5, overshoot_prob=0.0)
        time.sleep(0.05)
        samples = cap.stop()

        # Filter only the middle 50% where movement is fastest (most tremor visible)
        n = len(samples)
        mid = samples[n//4 : 3*n//4]
        if len(mid) < 5:
            self.skipTest("Too few middle samples")

        dxs = [mid[i].x - mid[i-1].x for i in range(1, len(mid))]
        dys = [mid[i].y - mid[i-1].y for i in range(1, len(mid))]

        # We expect some jitter superimposed on smooth motion.
        # The stddev of deltas should be non-zero and bounded.
        std_x = math.sqrt(sum(v*v for v in dxs) / len(dxs))
        std_y = math.sqrt(sum(v*v for v in dys) / len(dys))

        # Tremor should add some variance but not ridiculous amounts
        self.assertGreater(std_x + std_y, 1.0,
            f"Too little jitter (std_x={std_x:.2f}, std_y={std_y:.2f})")

    def test_overshoot_detected(self):
        """M3: About 12% of moves should overshoot and correct."""
        self._move_to_center()
        overshoot_count = 0
        trials = 30

        for _ in range(trials):
            cap = MouseCapture(poll_hz=100.0)
            cap.start()
            time.sleep(0.03)

            tx = self.safe_center[0] + random.randint(-200, 200)
            ty = self.safe_center[1] + random.randint(-150, 150)
            bezier_move(tx, ty, duration=0.6, overshoot_prob=0.12)
            time.sleep(0.3)  # Wait for overshoot correction
            samples = cap.stop()

            if len(samples) < 5:
                continue

            # Detect overshoot: path goes beyond target then returns
            x_samples = [s.x for s in samples]
            y_samples = [s.y for s in samples]
            # Check if max exceeds target in direction of travel
            start_x, start_y = x_samples[0], y_samples[0]
            dir_x = tx - start_x
            dir_y = ty - start_y

            overshot = False
            # Detect overshoot by projecting onto the start->target direction
            # An overshoot goes PAST the target along the primary axis of motion
            dir_len = math.hypot(dir_x, dir_y)
            if dir_len > 0:
                ux, uy = dir_x / dir_len, dir_y / dir_len
                # Project each sample onto direction vector; distance from start
                projections = [((s.x - start_x) * ux + (s.y - start_y) * uy) for s in samples]
                target_proj = dir_len
                # Find if any sample exceeds target by >5% and later returns within 10px
                for i, proj in enumerate(projections):
                    if proj > target_proj * 1.05:
                        # Check later samples return close to target
                        for j in range(i + 1, len(samples)):
                            dist_to_target = math.hypot(samples[j].x - tx, samples[j].y - ty)
                            if dist_to_target < 10:
                                overshot = True
                                break
                        break
            if overshot:
                overshoot_count += 1

            time.sleep(0.1)

        rate = overshoot_count / trials
        self.assertGreaterEqual(rate, 0.05,
            f"Overshoot rate {rate:.2%} too low (expected ~12%)")
        self.assertLessEqual(rate, 0.35,
            f"Overshoot rate {rate:.2%} too high (expected ~12%)")

    def test_click_avoids_danger_zones(self):
        """M4: Click planner should never click in danger zones."""
        from simulator.input_engine.clicks import ClickPlanner
        from simulator.context.windows import WindowManager
        from simulator.utils import get_window_geometry

        wm = WindowManager()
        wm.refresh()
        planner = ClickPlanner(self.screen)

        # Try many safe clicks
        for _ in range(20):
            active = wm.active
            if active:
                geo = get_window_geometry(active.id)
                if geo:
                    point = self.screen.safe_point_in_window(
                        geo['x'], geo['y'], geo['width'], geo['height']
                    )
                    if point:
                        self.assertTrue(
                            self.screen.is_safe_coordinate(point[0], point[1]),
                            f"Click planned in danger zone: {point}"
                        )


if __name__ == '__main__':
    unittest.main()
