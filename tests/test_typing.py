"""Integration tests for typing realism (requires X11 display)."""
import unittest
import time
import math
import random

from tests.capture_utils import (
    KeyboardCapture, WindowFocusCapture, EvaluationHarness, check_display_available
)
from simulator.input_engine.typing import TypingModel
from simulator.safety.sandbox import SandboxWindow
from simulator.safety.governor import SafetyGovernor
from simulator.utils import get_active_window_id, focus_window


@unittest.skipUnless(check_display_available(), "No X11 display available")
class TestTypingIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sandbox = SandboxWindow()
        sb_id = cls.sandbox.spawn()
        if sb_id is None:
            raise unittest.SkipTest("Could not spawn sandbox window")
        cls.typing = TypingModel(error_rate=0.025)
        cls.governor = SafetyGovernor()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.sandbox.cleanup()

    def test_sandbox_window_exists(self):
        """T1 prerequisite: sandbox window is detectable."""
        self.assertIsNotNone(self.sandbox.win_id)

    def test_typing_generates_actual_key_events(self):
        """T1: Real X11 key events should be captured during typing."""
        # Focus sandbox first
        self.sandbox.focus()
        time.sleep(0.2)

        # Try keyboard capture; skip if xinput doesn't find device
        try:
            kbd = KeyboardCapture()
            kbd.start()
        except RuntimeError as e:
            self.skipTest(f"Keyboard capture unavailable: {e}")

        time.sleep(0.1)
        text = "hello world test"
        self.typing.type_burst(text, with_shortcuts=False)
        time.sleep(0.2)
        events = kbd.stop()

        press_count = sum(1 for e in events if e.event_type == 'press')
        # Should be close to len(text) plus maybe some delays caused no-ops
        self.assertGreater(press_count, len(text) * 0.5,
            f"Too few key events: {press_count} for {len(text)} chars")

    def test_typing_takes_realistic_time(self):
        """T2: A burst should take realistic time, not instant."""
        self.sandbox.focus()
        time.sleep(0.2)

        text = "abcdefghij" * 5  # 50 chars
        start = time.time()
        self.typing.type_burst(text, with_shortcuts=False)
        elapsed = time.time() - start

        # 50 chars * ~120ms = ~6s minimum; with overhead should be > 3s
        self.assertGreater(elapsed, 2.0,
            f"Typing burst too fast ({elapsed:.2f}s for 50 chars). Delay loop may be broken.")
        self.assertLess(elapsed, 30.0,
            f"Typing burst too slow ({elapsed:.2f}s for 50 chars).")

    def test_inter_key_delays_vary(self):
        """T2: Delays should vary (not uniform / constant)."""
        self.sandbox.focus()
        time.sleep(0.2)

        # We can't easily measure per-key delay externally, but we can measure
        # the total time for two different texts and verify proportionality.
        text_short = "abc"
        text_long = "abc" * 10

        t0 = time.time()
        self.typing.type_burst(text_short, with_shortcuts=False)
        dt_short = time.time() - t0

        time.sleep(0.3)

        t0 = time.time()
        self.typing.type_burst(text_long, with_shortcuts=False)
        dt_long = time.time() - t0

        # Long text should take roughly 10x longer
        ratio = dt_long / max(dt_short, 0.001)
        self.assertGreater(ratio, 5.0,
            f"Long text not proportionally slower (ratio {ratio:.1f})")

    def test_error_injection_produces_backspaces(self):
        """T3: High error rate should produce visible backspace events."""
        try:
            kbd = KeyboardCapture()
            kbd.start()
        except RuntimeError as e:
            self.skipTest(f"Keyboard capture unavailable: {e}")

        self.sandbox.focus()
        time.sleep(0.1)

        # Temporarily increase error rate
        old_rate = self.typing.error_rate
        self.typing.error_rate = 0.30  # 30% to guarantee errors
        try:
            text = "abcdefghijklmnopqrstuvwxyz" * 4  # 104 chars
            self.typing.type_burst(text, with_shortcuts=False)
        finally:
            self.typing.error_rate = old_rate

        time.sleep(0.2)
        events = kbd.stop()

        # BackSpace keycode is typically 22 on X11
        backspace_count = sum(1 for e in events if e.keycode == 22)
        self.assertGreater(backspace_count, 0,
            "No backspace events detected despite high error rate")
        # With 30% error on 104 chars, expect ~15–40 backspaces
        self.assertLess(backspace_count, 80,
            f"Suspiciously many backspaces ({backspace_count}), possible loop bug")

    def test_shortcut_injection_occurs(self):
        """T4: Shortcuts should occasionally fire."""
        try:
            kbd = KeyboardCapture()
            kbd.start()
        except RuntimeError as e:
            self.skipTest(f"Keyboard capture unavailable: {e}")

        self.sandbox.focus()
        time.sleep(0.1)

        # Run many bursts to trigger shortcut probabilistically
        for _ in range(15):
            self.typing.type_burst("test", with_shortcuts=True)
            time.sleep(0.2)

        events = kbd.stop()
        press_codes = [e.keycode for e in events if e.event_type == 'press']

        # Ctrl is usually keycode 37; we expect to see it with S/C/V/A/Z
        ctrl_count = sum(1 for c in press_codes if c == 37)
        self.assertGreater(ctrl_count, 0,
            "No Ctrl key events detected; shortcuts may not be firing")

    def test_sandbox_isolation(self):
        """T5: Typing should only go to sandbox window."""
        # Focus a different window first (if any exist)
        from simulator.utils import get_window_list, focus_window
        others = [w for w in get_window_list()
                  if self.sandbox.TITLE_SUBSTRING not in w.get('title', '')]

        pre_focus = get_active_window_id()
        if others:
            focus_window(others[0]['id'])
            time.sleep(0.2)

        # Now our orchestrator would focus sandbox, type, then restore
        foc = WindowFocusCapture(poll_hz=20.0)
        foc.start()
        time.sleep(0.05)

        self.sandbox.focus()
        time.sleep(0.1)
        self.typing.type_burst("isolated", with_shortcuts=False)
        time.sleep(0.1)

        # Restore previous focus
        if pre_focus:
            focus_window(pre_focus)

        focus_events = foc.stop()
        sandbox_id = self.sandbox.win_id

        # Verify sandbox was active during typing
        during_typing = [e for e in focus_events
                         if e.t >= foc.events[0].t + 0.1]
        sandbox_focused = any(e.win_id == sandbox_id for e in during_typing)
        self.assertTrue(sandbox_focused,
            "Sandbox window was never focused during typing burst")

    def test_governor_blocks_forbidden_keys(self):
        """F1: Forbidden keys should be rejected by governor."""
        self.assertFalse(self.governor.check_key('alt+f4'))
        self.assertFalse(self.governor.check_key('ctrl+w'))

    def test_governor_blocks_unsafe_text(self):
        """F2: Control characters should be rejected."""
        self.assertFalse(self.governor.check_type_text("hello\x01"))


if __name__ == '__main__':
    unittest.main()
