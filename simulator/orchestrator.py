"""Main simulation orchestrator: kernel-level input when possible,
realistic activity density, and safety-first typing.

Key architecture:
  1. Try uinput (kernel virtual device) for real evdev events.
  2. If uinput unavailable, fall back to xdotool + sandbox.
  3. Constant tremor thread provides continuous micro-mouse-movement.
  4. Typing goes to the REAL active window ONLY if window type is safe.
  5. InputWatchdog pauses everything when user returns.
"""
import random
import time
import threading
from typing import Optional

from simulator.context.windows import WindowManager, WindowType
from simulator.context.screen import ScreenManager
from simulator.input_engine.motion import small_nudge
from simulator.input_engine.typing import TypingModel
from simulator.input_engine.watchdog import InputWatchdog
from simulator.input_engine.tremor import TremorThread
from simulator.input_engine.uinput_device import UInputDevice
from simulator.safety.sandbox import SandboxWindow
from simulator.safety.governor import SafetyGovernor
from simulator.behavior.content import ContentGenerator
from simulator.behavior.fatigue import TemporalModel
from simulator.state_machine import BehaviorStateMachine, MacroState, MicroAction
from simulator.utils import (
    get_mouse_pos, send_key, click_button, get_active_window_id, focus_window,
    move_mouse_raw
)


class Orchestrator:
    PAUSE_AFTER_USER_ACTIVITY = 3.0
    POLL_INTERVAL = 0.2

    # Window types considered SAFE to type into (no command execution risk)
    SAFE_TYPE_WINDOWS = {WindowType.BROWSER, WindowType.EDITOR, WindowType.OTHER}

    def __init__(self, safe_mode: bool = False, verbose: bool = True,
                 use_uinput: bool = True):
        self.safe_mode = safe_mode
        self.verbose = verbose
        self.use_uinput = use_uinput

        # Context
        self.windows = WindowManager(cache_ttl=2.0)
        self.screen = ScreenManager()

        # Input engines
        self.typing = TypingModel(error_rate=0.025)
        self.uinput = UInputDevice()
        self.sandbox = SandboxWindow()

        # Safety
        self.governor = SafetyGovernor(safe_mode=safe_mode)

        # Behavior
        self.content = ContentGenerator()
        self.temporal = TemporalModel()
        self.hsm = BehaviorStateMachine()

        # User activity watchdog
        self.watchdog = InputWatchdog(
            mouse_threshold_px=5,
            idle_timeout_sec=self.PAUSE_AFTER_USER_ACTIVITY
        )

        # Tremor thread (constant micro mouse movement)
        self.tremor: Optional[TremorThread] = None

        # State
        self.running = False
        self.stats = {
            'keystrokes': 0,
            'switches': 0,
            'scrolls': 0,
            'mouse_nudges': 0,
            'actions': 0,
            'user_interrupts': 0,
            'tremor_moves': 0,
        }
        self._uinput_ok = False
        self._previous_active_id: Optional[int] = None

    def log(self, msg: str):
        if self.verbose:
            ts = time.strftime('%H:%M:%S')
            print(f"[{ts}] {msg}")

    def _setup_uinput(self) -> bool:
        """Initialize uinput virtual keyboard+mouse. Returns True on success."""
        if not self.use_uinput:
            return False
        if not self.uinput.is_available():
            self.log("uinput: /dev/uinput not writable (try sudo or add user to 'input' group)")
            return False
        ok = self.uinput.open()
        if ok:
            self.log("uinput: virtual keyboard+mouse active (kernel-level events)")
        else:
            self.log("uinput: failed to create virtual device")
        return ok

    def _setup_tremor(self):
        """Start the background tremor thread."""
        should_pause = lambda: self.watchdog.is_user_active
        if self._uinput_ok:
            # Kernel-level relative motion
            def move(dx, dy):
                self.uinput.move_relative(dx, dy)
            self.tremor = TremorThread(move, min_interval=0.05, max_interval=0.25, max_amplitude=2, should_pause=should_pause)
        else:
            # xdotool fallback: relative moves
            def move(dx, dy):
                from simulator.utils import run_cmd
                run_cmd(['xdotool', 'mousemove_relative', '--', str(dx), str(dy)], timeout=2)
            self.tremor = TremorThread(move, min_interval=0.10, max_interval=0.40, max_amplitude=2, should_pause=should_pause)
        self.tremor.start()
        self.log("tremor: constant micro-movement thread started")

    def _pre_action(self, desc: str) -> bool:
        if self.safe_mode:
            self.log(f"[SAFE] {desc}")
            self.governor.log(desc)
            return False
        self.log(desc)
        return True

    def _get_context_window(self):
        self.windows.refresh()
        return self.windows.active

    def _is_safe_to_type(self, ctx) -> bool:
        """Return True if current window is safe for typing."""
        if ctx is None:
            return False
        return ctx.window_type in self.SAFE_TYPE_WINDOWS

    def action_type_burst(self):
        ctx = self._get_context_window()
        wtype = ctx.window_type if ctx else WindowType.OTHER

        text = self.content.generate(wtype)
        if not self.governor.check_type_text(text):
            self.log("Governor blocked unsafe text")
            return

        if self._pre_action(f"TYPE [{wtype.name}]: {text[:40].replace(chr(10), ' ')}"):
            if self._uinput_ok and self._is_safe_to_type(ctx):
                # Kernel-level typing into real active window
                self.uinput.type_text(text, base_delay=0.08)
                self.stats['keystrokes'] += len(text)
            elif self.sandbox.win_id is not None:
                # Fallback: sandbox focus dance
                self._previous_active_id = get_active_window_id()
                ok = self.sandbox.focus()
                if ok:
                    self.typing.type_burst(text, with_shortcuts=True)
                    self.stats['keystrokes'] += len(text)
                    self.sandbox.unfocus()
                    if self._previous_active_id:
                        focus_window(self._previous_active_id)
                else:
                    self.log("WARNING: Could not focus sandbox; skipping typing")
            else:
                self.log("WARNING: No input method available; skipping typing")

    def action_scroll(self):
        ctx = self._get_context_window()
        direction = random.choice(['up', 'down', 'down', 'down'])
        amount = random.randint(2, 6)
        if ctx and ctx.is_terminal:
            amount = random.randint(1, 3)

        button = '4' if direction == 'up' else '5'
        if self._pre_action(f"SCROLL {direction} x{amount}"):
            for _ in range(amount):
                if self._uinput_ok:
                    # Map scroll wheel to relative Y (simplified)
                    # uinput doesn't have scroll buttons; use key taps for now
                    # or stick with xdotool click which is reliable for scroll
                    click_button(button)
                else:
                    click_button(button)
                time.sleep(random.uniform(0.06, 0.14))
            self.stats['scrolls'] += 1

    def action_mouse_nudge(self):
        """Small mouse movement via xdotool (visible to X11 trackers)."""
        if self._pre_action("MOUSE nudge"):
            small_nudge()
            self.stats['mouse_nudges'] += 1

    def action_switch_tab(self):
        ctx = self._get_context_window()
        if ctx and ctx.is_browser:
            if self._pre_action("SWITCH browser tab"):
                if self._uinput_ok:
                    self.uinput.shortcut('LEFTCTRL', 'TAB')
                else:
                    send_key('ctrl+Tab')
                self.stats['switches'] += 1
                return
        if ctx and ctx.is_terminal:
            if self._pre_action("SWITCH terminal tab"):
                send_key('ctrl+Page_Down')
                self.stats['switches'] += 1
                return
        if self._pre_action("SWITCH alt+tab"):
            if self._uinput_ok:
                self.uinput.shortcut('LEFTALT', 'TAB')
            else:
                send_key('alt+Tab')
            self.stats['switches'] += 1

    def action_switch_window(self):
        self.windows.refresh()
        active = self.windows.active
        others = [w for w in self.windows.windows if w != active]
        if not others:
            return
        target = random.choice(others)
        if self._pre_action(f"SWITCH window to {target.title[:40]}"):
            if self._uinput_ok and active:
                # Alt+Tab sequence with uinput
                self.uinput.shortcut('LEFTALT', 'TAB')
            else:
                focus_window(target.id)
            self.stats['switches'] += 1

    def action_reading_pause(self):
        duration = self.temporal.reading_pause_duration()
        if self._pre_action(f"PAUSE reading {duration:.1f}s"):
            time.sleep(duration)

    def execute_micro_action(self, action: MicroAction):
        handlers = {
            MicroAction.TYPE_BURST: self.action_type_burst,
            MicroAction.SCROLL: self.action_scroll,
            MicroAction.MOUSE_NUDGE: self.action_mouse_nudge,
            MicroAction.SWITCH_TAB: self.action_switch_tab,
            MicroAction.SWITCH_WINDOW: self.action_switch_window,
            MicroAction.READING_PAUSE: self.action_reading_pause,
        }
        handler = handlers.get(action)
        if handler:
            handler()
        self.stats['actions'] += 1

    def run(self):
        self.running = True
        self.log("=" * 55)
        self.log("Activity Simulator v2.1 (Kernel-Level Input)")
        self.log(f"Safe mode: {self.safe_mode}")
        self.log("User input detected -> simulation PAUSES")
        self.log("=" * 55)

        # Try uinput first
        self._uinput_ok = self._setup_uinput()

        # Spawn sandbox only if uinput failed
        if not self._uinput_ok:
            sb_id = self.sandbox.spawn()
            if sb_id:
                self.log(f"Sandbox ready (hidden): {sb_id}")
            else:
                self.log("WARNING: No sandbox; typing disabled")
        else:
            self.log("Typing via kernel injection (no sandbox needed)")

        # Start tremor thread
        self._setup_tremor()

        # Context scan
        self.windows.refresh()
        self.log(f"Detected {len(self.windows.windows)} windows")
        for w in self.windows.windows:
            self.log(f"  [{w.window_type.name}] {w.title[:50]}")

        # Start watchdog
        self.watchdog.start()
        self.log("Watchdog active (mouse + keyboard)")

        start = time.time()
        last_minute_log = 0

        while self.running:
            try:
                # --- USER INPUT CHECK ---
                if self.watchdog.is_user_active:
                    if self.stats['actions'] % 20 == 0:
                        self.log(f"USER ACTIVE (idle {self.watchdog.seconds_since_activity:.1f}s) — PAUSED")
                    self.stats['user_interrupts'] += 1
                    time.sleep(self.POLL_INTERVAL)
                    continue

                # --- SAFE TO SIMULATE ---
                break_prob = self.temporal.break_probability()
                transitioned = self.hsm.force_transition(fatigue_break_prob=break_prob)
                if transitioned:
                    self.log(f"=== State: {self.hsm.state.name} ===")

                action = self.hsm.sample_action()
                self.execute_micro_action(action)

                pause = self.temporal.pause_between_actions()
                time.sleep(pause)

                # Periodic stats
                elapsed = int((time.time() - start) / 60)
                if elapsed > last_minute_log:
                    last_minute_log = elapsed
                    tremor_moves = self.tremor.stats['moves'] if self.tremor else 0
                    self.log(
                        f"Stats @ {elapsed}min | "
                        f"state={self.hsm.state.name} | "
                        f"keys={self.stats['keystrokes']} | "
                        f"switches={self.stats['switches']} | "
                        f"scrolls={self.stats['scrolls']} | "
                        f"tremor={tremor_moves} | "
                        f"interrupts={self.stats['user_interrupts']}"
                    )

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"ERROR: {e}")
                time.sleep(1)

        self._shutdown(start)

    def _shutdown(self, start_time: float):
        self.log("Shutting down...")
        self.watchdog.stop()
        if self.tremor:
            self.tremor.stop()
            self.stats['tremor_moves'] = self.tremor.stats['moves']
        self.sandbox.cleanup()
        if self._uinput_ok:
            self.uinput.close()
        elapsed = (time.time() - start_time) / 60
        print("\n" + "=" * 55)
        print("FINAL STATISTICS")
        print("=" * 55)
        print(f"Duration:        {elapsed:.1f} min")
        print(f"Keystrokes:      {self.stats['keystrokes']} ({self.stats['keystrokes']/max(1,elapsed):.1f}/min)")
        print(f"Window switches: {self.stats['switches']} ({self.stats['switches']/max(1,elapsed):.1f}/min)")
        print(f"Scrolls:         {self.stats['scrolls']} ({self.stats['scrolls']/max(1,elapsed):.1f}/min)")
        print(f"Mouse nudges:    {self.stats['mouse_nudges']} ({self.stats['mouse_nudges']/max(1,elapsed):.1f}/min)")
        print(f"Tremor moves:    {self.stats['tremor_moves']} ({self.stats['tremor_moves']/max(1,elapsed):.1f}/min)")
        print(f"User interrupts: {self.stats['user_interrupts']}")
        print(f"Total actions:   {self.stats['actions']}")
        print("=" * 55)

    def stop(self):
        self.running = False
