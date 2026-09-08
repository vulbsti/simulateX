# Activity Simulator v2 — Architecture & Design Document

## 1. Philosophy

The original simulator was a **random action generator**. An ideal system is a **behavioral simulation engine** that models:

1. **Biomechanics** — How human hands actually move (acceleration, curves, fatigue)
2. **Cognitive State** — What the "virtual user" is trying to do (read, type, navigate)
3. **Task Structure** — Real work happens in sessions, bursts, and flows
4. **Safety Isolation** — Input must reach time-trackers without touching real user data

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SIMULATION ORCHESTRATOR                   │
│  (TemporalModel + SessionPlanner + FatigueModel)            │
└───────────────────────┬─────────────────────────────────────┘
                        │ decides macro-state
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              BEHAVIORAL STATE MACHINE (HSM)                  │
│                                                              │
│   ┌─────────┐   ┌──────────┐   ┌─────────┐   ┌─────────┐   │
│   │  FOCUS  │◄─►│ BROWSING │◄─►│RESEARCH │◄─►│  BREAK  │   │
│   │(typing) │   │(scrolling│   │(switch  │   │ (idle)  │   │
│   └────┬────┘   │ + click) │   │ + read) │   └────┬────┘   │
│        │        └────┬─────┘   └────┬────┘        │        │
│        │             │              │             │        │
│        ▼             ▼              ▼             ▼        │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              ACTION GENERATOR                        │  │
│   │  (Typed by context: code, prose, commands, etc.)    │  │
│   └────────────────────┬────────────────────────────────┘  │
└────────────────────────┼────────────────────────────────────┘
                         │ action plan
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              SAFETY GOVERNOR & SANDBOX                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Window      │  │  Danger Zone │  │   Scratch Pad    │   │
│  │ Validator   │  │   Detector   │  │   (Type Target)  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ sanitized action
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              PHYSICS-BASED INPUT ENGINE                      │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ MotionPlanner  │  │   TypingModel  │  │   ClickMap   │  │
│  │ (Bezier curves │  │ (Error model,  │  │ (Semantic UI │  │
│  │  + noise)      │  │  shortcuts)    │  │  targets)    │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                    ┌────┴────┐
                    │ xdotool │
                    │ /uinput │
                    └─────────┘
```

---

## 3. Component Specifications

### 3.1 Physics-Based Input Engine

#### 3.1.1 Mouse Motion — `MotionPlanner`

**Problem:** Original used linear stepping (3–8 jumps). Humans move in smooth curves with acceleration profiles.

**Solution:** Cubic Bézier splines with a velocity profile.

```
Control Point Layout:
P0 = start position
P1 = start + velocity_vector (extends trajectory naturally)
P2 = target + approach_vector (creates curve direction)
P3 = target

Perpendicular offset: shift P1/P2 by rand(-D, +D) perpendicular to P0→P3
  where D ≈ distance * 0.15 (human curvature constant)

Velocity Profile (ease-in-out-sine):
  t' = 0.5 * (1 - cos(π * t))   [0..1]
  This models: slow start → fast middle → slow landing

Overshoot Model:
  15% chance of overshooting target by 5–20%
  If overshoot: continue past target, then corrective micro-movement
  This is the #1 signal of "human vs. bot" in input analysis.

Noise: Add Perlin/simplex noise to each interpolated point for hand tremor.
```

**Why this fools trackers:** Time-tracking systems that analyze screenshots or input patterns look for smooth acceleration curves. Linear interpolation with 3–8 steps is trivial to detect.

#### 3.1.2 Keystrokes — `TypingModel`

**Problem:** Original was a complete no-op (only slept).

**Solution:** Send real keys via `xdotool` into a **dedicated scratchpad window**.

```
Architecture:
  1. On startup, spawn a hidden/minimized text editor (or tkinter window)
     titled "__ACTIVITY_SANDBOX__". This window is the typing sink.
  2. Before typing burst: focus the sandbox via wmctrl
  3. Type using xdotool with per-character delays
  4. Return focus to previous window (optional, for seamlessness)

Typing Dynamics:
  - Keypress latency follows log-normal distribution:
      mean = 120ms, sigma = 0.35  (natural human variance)
  - Burst structure: words of 3–12 chars, pause 0.2–1.2s between words
  - Error model (~2.5% error rate):
      a) Substitution: "teh" → "the", "adn" → "and"
      b) Double-strike: "letter" → "lettter"
      c) Omission: "typing" → "typng"
    Correction behaviors:
      - 70% immediate backspace
      - 20% arrow-key navigation + delete
      - 10% ignore (noticed too late)
  - Shortcut injection (~5% of bursts):
      Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+S, Ctrl+Z
      These are high-frequency in real workflows.

Content Sources:
  - Code: snippets from a local corpus (Python, JS, etc.)
  - Prose: lorem-ipsum variants, markdown docs
  - Commands: shell-like text for terminal context
  Context-sensitive selection (see §3.3).
```

**Why this fools trackers:** ActivityWatch, RescueTime, and screenshot tools all register X11 KeyPress events. A sandboxed real window generates genuine events with realistic inter-key timing — indistinguishable from human typing to input hooks.

#### 3.1.3 Clicks — `ClickMap`

**Problem:** Original clicked randomly anywhere on screen.

**Solution:** Semantic click targeting.

```
Strategy:
  1. Do NOT click blindly. Instead:
     a) If active window is browser → scroll is preferred over click
     b) If click is chosen → move to a "safe zone" within active window
        Safe zone = center 60% of window, avoiding edges (close buttons)
  2. Danger Zone Blacklist (screen coordinates):
     - Top 30px: system menu bars, window title bars
     - Top-right corner: close/minimize/maximize buttons
     - Bottom panels: system trays, docks
     - Any coordinate matching known notification popups
  3. Click patterns:
     - Single left click (70%)
     - Double click (15%) — with 80–180ms inter-click gap
     - Right click → Escape (10%)
     - Drag operation (5%) — press, move 50–200px, release
```

---

### 3.2 Behavioral State Machine (HSM)

**Problem:** Original picked actions from a weighted bag every 0.1–2s with no memory.

**Solution:** Hierarchical Finite State Machine with sticky states and minimum durations.

```
MACRO STATES (duration 30s – 15min):

┌─────────────┬────────────────────────────┬─────────────────────────────┐
│ State       │ Actions                    │ Exit Conditions             │
├─────────────┼────────────────────────────┼─────────────────────────────┤
│ DEEP_FOCUS  │ Typing bursts, shortcuts,  │ After 3–10 min OR if        │
│             │ occasional mouse-to-line,  │ reading_pause_trigger       │
│             │ scroll within document     │                             │
├─────────────┼────────────────────────────┼─────────────────────────────┤
│ BROWSING    │ Scroll dominant, some      │ After 2–8 min OR finding a  │
│             │ clicks on links, tab       │ target → switch to RESEARCH │
│             │ switches every 1–3 min     │                             │
├─────────────┼────────────────────────────┼─────────────────────────────┤
│ RESEARCH    │ Rapid window switching,    │ After 1–5 min OR settling   │
│             │ reading pauses, copying    │ on source → DEEP_FOCUS      │
│             │ text between windows       │                             │
├─────────────┼────────────────────────────┼─────────────────────────────┤
│ MULTITASK   │ Alt+Tab chains, short      │ After 30s–2min OR fatigue   │
│             │ visits to many windows     │ drop → BREAK or FOCUS       │
├─────────────┼────────────────────────────┼─────────────────────────────┤
│ BREAK       │ Mouse idle, very rare      │ After 1–5 min OR random     │
│             │ micro-movements            │ resume                      │
└─────────────┴────────────────────────────┴─────────────────────────────┘

State Entry Behavior:
  - On entering DEEP_FOCUS from RESEARCH: 40% chance of pasting
    previously "copied" text (simulates bringing reference material)
  - On entering BROWSING: reset scroll counter, pick a scroll anchor
  - On entering RESEARCH: increase switch probability by 3x

Micro-State within DEEP_FOCUS:
  TYPING_BURST    → 3–20 chars → PAUSE
  PAUSE           → 0.3–2.0s  → TYPING_BURST or SCROLL
  SCROLL          → 1–5 lines → back to TYPING_BURST
  LINE_NAVIGATE   → click line number / arrow keys → TYPING_BURST
```

**Key insight:** Real humans don't "decide" every 0.5 seconds. They enter a mode and stay there. The HSM enforces minimum state durations and contextual action availability.

---

### 3.3 Context Analyzer

**Problem:** Original classified windows but never used the classification for meaningful behavior.

**Solution:** Context drives both content selection and action availability.

```
Window Classification:
  BROWSER   → typing = URLs/search terms; scroll = large vertical
  TERMINAL  → typing = shell commands; scroll = small; lots of Enter
  EDITOR    → typing = code/prose; Ctrl+S every 2–3 min; scroll = medium
  CHAT      → typing = short messages; Enter-heavy; emoji rarely
  FILE_MGR  → click-heavy; typing = filenames; minimal scroll

Content Selection per Context:
  EDITOR + Python file open → type Python snippets
  TERMINAL → type "ls -la", "git status", "docker ps" style commands
  BROWSER → type search queries, URLs

Active Window Detection Fix:
  Normalize IDs: wmctrl returns 0x-prefixed hex. xdotool returns decimal.
  Store all IDs as integers internally. No string comparison.
```

---

### 3.4 Safety Governor

**Problem:** Original could click anywhere and never sent keys.

**Solution:** Defense in depth.

```
Layer 1 — Scratchpad Isolation:
  - Spawn a background gedit/xterm/tkinter window at startup.
  - All typing bursts focus this window first, type, then (optionally)
    restore previous focus.
  - Window title: "__sim_sandbox__" so user knows what it is.

Layer 2 — Danger Zones:
  - Maintain a live mask of forbidden screen regions:
    * Title bars (top 30px of each window)
    * Screen corners (close buttons)
    * Notification popups (detected by window class / position)
  - Before ANY click: verify coordinate is not in danger zone.

Layer 3 — Action Whitelist:
  - Keystrokes: only printable ASCII + common shortcuts
  - NEVER send: Alt+F4, Ctrl+Alt+Del, Ctrl+W (close tab), Super+L
  - Mouse: never click at screen edges

Layer 4 — Dry-Run Mode:
  - Safe mode logs actions to a structured JSONL file.
  - A replay viewer can visualize what WOULD have happened.
```

---

### 3.5 Temporal & Fatigue Model

**Problem:** Original used flat random distributions regardless of runtime.

**Solution:** Time-varying parameters.

```
Circadian Modulation:
  productivity(t) = base * (0.7 + 0.3 * sin(2π * (hour - 6) / 24))
  Morning (8–12): longer DEEP_FOCUS states
  Post-lunch (13–15): more BREAK, shorter focus
  Late afternoon (16–18): more MULTITASK

Session Fatigue (cumulative within a run):
  fatigue = 1 - exp(-elapsed_minutes / 90)   # approaches 1 over ~2hrs
  Effect: increases BREAK probability, reduces burst length

Break Structure:
  - Micro-break: 5–15s pause within a state (eye re-focus)
  - Short break: 1–3 min BREAK state every 20–40 min
  - Long break: 5–10 min BREAK state every 1.5–2 hours
```

---

## 4. Implementation Roadmap

### Phase 1 — Foundation (critical fixes)
1. `MotionPlanner` with Bézier curves
2. `TypingModel` with sandbox scratchpad + real xdotool keys
3. `SafetyGovernor` with danger zones
4. Fix window ID normalization

### Phase 2 — Intelligence
5. Hierarchical State Machine
6. Context-aware content selection
7. Error model + shortcuts in typing

### Phase 3 — Realism Polish
8. Temporal/fatigue models
9. Drag-and-drop, double-click
10. Multi-monitor support via xrandr
11. Structured logging + replay analyzer

---

## 5. File Structure

```
activity_simulator_v2/
├── __init__.py
├── main.py              # CLI entrypoint
├── orchestrator.py      # Simulation loop + temporal model
├── state_machine.py     # HSM definition
├── input_engine/
│   ├── __init__.py
│   ├── motion.py        # Bézier mouse planner
│   ├── typing.py        # TypingModel + error injection
│   └── clicks.py        # Semantic click targeting
├── context/
│   ├── __init__.py
│   ├── windows.py       # Window detection (fixed IDs)
│   ├── screen.py        # Multi-monitor + danger zones
│   └── classifier.py    # Window type classifier
├── safety/
│   ├── __init__.py
│   ├── governor.py      # Action validation
│   └── sandbox.py       # Scratchpad window manager
├── behavior/
│   ├── __init__.py
│   ├── content.py       # Text corpora per context
│   └── fatigue.py       # Temporal modulation
└── utils/
    ├── __init__.py
    └── x11.py           # xdotool/wmctrl wrappers
```

---

## 6. Key Algorithms (Pseudocode)

### 6.1 Bézier Mouse Move

```python
def bezier_move(target_x, target_y, duration=0.8):
    x0, y0 = get_mouse_pos()
    x3, y3 = target_x, target_y

    # Control points with perpendicular curvature
    dx, dy = x3 - x0, y3 - y0
    dist = sqrt(dx*dx + dy*dy)
    perp_x, perp_y = -dy/dist, dx/dist
    offset = dist * random.gauss(0.15, 0.05)

    x1 = x0 + dx*0.3 + perp_x * offset
    y1 = y0 + dy*0.3 + perp_y * offset
    x2 = x3 - dx*0.3 + perp_x * offset
    y2 = y3 - dy*0.3 + perp_y * offset

    steps = max(20, int(duration * 60))  # 60Hz update
    for i in range(steps):
        t = i / steps
        # Ease-in-out-sine velocity profile
        t_vel = 0.5 * (1 - cos(pi * t))
        x = cubic_bezier(t_vel, x0, x1, x2, x3)
        y = cubic_bezier(t_vel, y0, y1, y2, y3)
        # Add hand tremor
        x += random.gauss(0, 0.5)
        y += random.gauss(0, 0.5)
        xdotool_mousemove(int(x), int(y))
        sleep(duration / steps)

    # Optional overshoot
    if random.random() < 0.15:
        overshoot_x = x3 + (x3-x0)*random.uniform(0.05, 0.2)
        overshoot_y = y3 + (y3-y0)*random.uniform(0.05, 0.2)
        bezier_move(overshoot_x, overshoot_y, duration=0.15)
        sleep(random.uniform(0.08, 0.2))
        bezier_move(x3, y3, duration=0.2)
```

### 6.2 Typing with Error Model

```python
def type_text(text: str):
    focus_sandbox_window()
    for i, intended_char in enumerate(text):
        # Decide if this char is an error
        if random.random() < ERROR_RATE:
            error_type = random.choice(['substitution', 'double', 'omission'])
            if error_type == 'substitution':
                typed = substitute_error(intended_char)
                xdotool_type(typed)
                sleep(lognormal(0.08, 0.03))
                # Correct it
                xdotool_key('BackSpace')
                sleep(lognormal(0.1, 0.04))
                xdotool_type(intended_char)
            elif error_type == 'double':
                xdotool_type(intended_char * 2)
                sleep(lognormal(0.08, 0.03))
                xdotool_key('BackSpace')
                sleep(lognormal(0.1, 0.04))
            # omission: just don't type, continue (rare)
        else:
            xdotool_type(intended_char)

        # Human inter-key delay
        delay = lognormal(0.12, 0.04)
        if intended_char in ' .,;:\n':
            delay *= random.uniform(1.2, 2.0)  # punctuation pause
        sleep(delay)

    # Occasional post-burst shortcut
    if random.random() < 0.05:
        shortcut = random.choice(['ctrl+s', 'ctrl+a', 'ctrl+c'])
        xdotool_key(shortcut)
```

### 6.3 HSM State Selection

```python
class SimulatorOrchestrator:
    def __init__(self):
        self.state = State.BREAK
        self.state_entry_time = time.time()
        self.fatigue = 0.0

    def select_next_action(self):
        state_age = time.time() - self.state_entry_time
        min_duration = STATE_MIN_DURATIONS[self.state]

        # Sticky: don't leave state before minimum time
        if state_age < min_duration:
            return self.state.sample_action()

        # Probabilistic transition based on fatigue + time-of-day
        transition_probs = get_transition_matrix(
            current=self.state,
            fatigue=self.fatigue,
            hour=datetime.now().hour
        )
        next_state = random.choices(
            list(transition_probs.keys()),
            weights=list(transition_probs.values())
        )[0]

        if next_state != self.state:
            self.enter_state(next_state)
        return next_state.sample_action()
```

---

## 7. Safety Checklist

| Threat | Mitigation |
|--------|------------|
| Types into wrong window (chat, terminal) | All typing goes to dedicated sandbox window |
| Clicks "Delete" or "Close" | Danger zone blacklist + edge avoidance |
| Sends Alt+F4 / Ctrl+W | Action whitelist — these combos blocked |
| Fills disk with typed text | Sandbox window is `tail -f /dev/null` or capped buffer |
| Runs at 3am looking suspicious | Optional time-of-day gate (only run 08:00–18:00) |
| Detected as xdotool script | Bézier motion + timing jitter + statefulness make signature human |

---

## 8. Why This Design Succeeds Where v1 Fails

| Flaw in v1 | v2 Solution |
|------------|-------------|
| Keystrokes are no-ops | Real keys to sandbox window with log-normal timing |
| Linear mouse stepping | Cubic Bézier + ease-in-out velocity + overshoot |
| Memoryless action bag | Hierarchical State Machine with 30s–15min sticky states |
| Random clicks anywhere | Semantic targeting + danger zone blacklist |
| No error correction | 2.5% error injection with realistic backspace patterns |
| No shortcuts | Ctrl+S/C/V/Z injected at realistic frequencies |
| Flat random distributions | Temporal model modulates by time-of-day & fatigue |
| Broken window ID compare | All IDs normalized to `int` at ingestion |
| Single hardcoded resolution | Multi-monitor via `xrandr` |
| No drag, double-click, etc. | Expanded action vocabulary |
