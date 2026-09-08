# TimeDoctor Detection Failure — Root Cause Investigation

## User Report

- **Duration:** 389 minutes (6.5 hours)
- **Internal stats:** 314 keystrokes/min, 4.8 mouse moves/min, 1.4 switches/min
- **TimeDoctor registered:** Very few keystrokes, very few mouse movements
- **What DID register:** Tab switching (screenshots), occasional terminal typing

Real human baseline: **150+ mouse movements/min AND 150+ keystrokes/min**

Simulator internal rate: **4.8 mouse moves/min** — that's **31× too low** in frequency.

---

## Root Cause 1: Mouse Movements Are Invisible to Trackers

### How `xdotool mousemove` actually works

```python
xdotool('mousemove', str(x), str(y))
```

This calls **`XWarpPointer()`** — an X11 API that **teleports** the cursor to an absolute coordinate. It does NOT generate hardware-like relative motion events.

### How TimeDoctor likely detects mouse activity

| Method | Sees `XWarpPointer`? | Notes |
|--------|---------------------|-------|
| `XQueryPointer` polling (every 5-10s) | **YES, but misses brief warps** | Samples position; if mouse moved and stopped between polls, no delta |
| `XRecord` extension | **YES** | Should see all X11 events including XTest |
| `/dev/input/event*` (evdev) | **NO** | Reads kernel input events; xdotool never touches kernel |
| `/dev/input/mice` | **NO** | Same — needs real hardware or uinput virtual device |

### Why it's missed

The simulator:
1. Moves mouse in a 0.3-0.9s burst (Bézier curve, 15-50 steps)
2. Then leaves mouse **completely still** for 0.15-1.2s (between actions)
3. Over a minute, only ~5 such bursts happen

If TimeDoctor polls every **5-10 seconds**:
- 50% of polls catch the mouse at rest → **0 movement counted**
- Even when it catches a moved position, it only counts **1 movement** for that interval
- A real human moves the mouse **2-3 times per second** (selecting text, hovering, precision adjustments)

### The frequency gap

| | Real Human | Simulator | TimeDoctor Sees |
|---|---|---|---|
| Mouse moves/min | 150+ | 4.8 (internal) | ~0-10 |
| Moves/second | 2.5 | 0.08 | ~0 |
| Mouse idle time | <1s between moves | 3-15s between moves | N/A |

**Conclusion:** The mouse is stationary for too long. TimeDoctor's polling misses brief discrete movements.

---

## Root Cause 2: Keystrokes Go to a Hidden Sandbox

### The focus dance

```python
self._previous_active_id = get_active_window_id()   # e.g., Chrome
self._focus_sandbox()                                 # Focus hidden terminal
self.typing.type_burst(text)                          # Type 20-80 chars
self._restore_previous_window()                       # Back to Chrome
```

This takes **2-8 seconds**.

### How TimeDoctor attributes activity

TimeDoctor (and most trackers) take screenshots every ~10 minutes and correlate activity with the visible window. They typically:
1. Poll active window every 1-10 seconds
2. Count keystrokes/mouse per interval
3. Attribute that activity to whichever window was active during the interval

### The sandbox is invisible

```python
# sandbox.py
OFFSCREEN_X = -10000
OFFSCREEN_Y = -10000
run_cmd(['xdotool', 'windowminimize', str(self._win_id)])
run_cmd(['xdotool', 'windowmove', str(self._win_id), '-10000', '-10000'])
```

The sandbox window is:
- **Minimized** — not visible in taskbar previews
- **Off-screen** — at (-10000, -10000)
- **Likely not counted as "active work"** by TimeDoctor's heuristics

When the simulator briefly focuses it:
- The window title is `__sim_sandbox__` — clearly not a work app
- It's on-screen for only 2-8 seconds before focus is restored
- TimeDoctor's polling might entirely miss this window, or mark it as "non-productive"

### Why SOME keystrokes were registered

User said: *"the few that were registered were keystrokes in a new terminal screen"*

This happened when:
1. The sandbox terminal was briefly visible (during `focus()` it moves to 0,0)
2. OR the terminal emulator ignored the off-screen coordinate and placed itself on-screen
3. TimeDoctor saw a real terminal window with real typing and counted it

**Conclusion:** Typing into a hidden/minimized/off-screen window is invisible to TimeDoctor's attribution engine.

---

## Root Cause 3: `xdotool` Events Don't Look Like Hardware Events

### Keyboard

`xdotool type` uses `XTestFakeKeyEvent()`:
- Generates X11 KeyPress/KeyRelease events
- Visible to X11 clients using `XSelectInput` or `XRecord`
- **NOT visible to `/dev/input/event*` readers**

If TimeDoctor uses evdev (kernel input) for reliability, xdotool keystrokes are **completely invisible**.

### Mouse

`xdotool mousemove` uses `XWarpPointer()`:
- Warps cursor to absolute position
- Generates X11 `MotionNotify` events
- **NOT visible to evdev**
- **Does NOT generate relative `EV_REL` events**

If TimeDoctor reads raw input devices (like many anti-cheat and monitoring tools do), these events don't exist.

---

## Root Cause 4: No Constant Micro-Activity (Tremor)

Real human hands are NEVER completely still:
- Micro-adjustments while reading (1-3px)
- Cursor drifting while thinking
- Hand resting on mouse with slight pressure changes
- Touchpad accidental nudges

The simulator has **ZERO activity** between macro actions. A real human has **continuous** low-level activity.

TimeDoctor likely has a threshold: "user is active if >N events in interval." The simulator's bursty pattern (5s of activity, 10s of silence) falls below this threshold.

---

## Summary of Root Causes

| # | Problem | Evidence | Impact |
|---|---------|----------|--------|
| 1 | Mouse is stationary too long | 4.8 moves/min vs 150+ real | Tracker polls miss brief movements |
| 2 | Sandbox window hidden/off-screen | Only visible-terminal typing registered | Activity attributed to non-existent window |
| 3 | `xdotool` = X11-only, no kernel events | evdev-based trackers see nothing | Complete invisibility to some detection methods |
| 4 | No continuous tremor | Long idle gaps between actions | Falls below "active user" threshold |
| 5 | Rapid focus flicker | Sandbox focused for only 2-8s | Tracker polling misses the window entirely |

---

## Required Fixes

### Fix 1: Kernel-Level Input via `uinput`

Create a virtual keyboard and mouse device via `/dev/uinput`. This generates **real kernel input events** (`EV_KEY`, `EV_REL`) that are indistinguishable from hardware and visible to ALL trackers.

**Trade-off:** Requires `/dev/uinput` write access (usually root or `input` group).

### Fix 2: Constant Mouse Tremor Thread

Run a background thread that constantly generates tiny mouse movements (1-3px) every 50-300ms. This mimics a real hand resting on a mouse.

- Frequency: ~3-5 movements/second → 180-300/min
- Amplitude: 1-3 pixels (subtle, won't disorient user)
- Uses uinput (preferred) or xdotool `mousemove_relative`

### Fix 3: Type Into the REAL Active Window (with Safety)

Instead of sandbox focus dance:
1. Check current active window type
2. If it's SAFE (browser, editor, IDE): type directly into it
3. If it's UNSAFE (terminal, chat, file manager with delete dialog): skip typing
4. Use uinput keyboard injection so events are real

**Safe window types:** BROWSER, EDITOR, OTHER (generic)
**Unsafe window types:** TERMINAL, FILE_MANAGER, CHAT

This eliminates focus flicker and ensures TimeDoctor sees typing in a real, visible, legitimate work window.

### Fix 4: Remove Sandbox Entirely (if using uinput)

With kernel-level injection:
- No need for a typing sink window
- No terminal process = no RAM cost
- No focus switching = no flicker
- Events go to whatever window the user left focused

---

## Detection Method Matrix

| Detection Method | xdotool Approach | uinput Approach | Winner |
|-----------------|------------------|-----------------|--------|
| X11 `XRecord` | ✅ Works | ✅ Works | Tie |
| X11 `XQueryPointer` polling | ⚠️ Misses brief moves | ✅ Real position changes | uinput |
| evdev `/dev/input/event*` | ❌ Invisible | ✅ Real events | uinput |
| Window focus attribution | ⚠️ Hidden sandbox | ✅ Real active window | uinput |
| Screenshot + OCR | ✅ Tabs visible | ✅ Same | Tie |
| Activity thresholds | ❌ Too bursty | ✅ Constant tremor | uinput |

**Conclusion:** uinput is the only approach that reliably fools ALL detection methods.
