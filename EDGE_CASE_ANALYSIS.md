# Activity Simulator v2 — Edge Case Analysis

This document traces the exact code paths for the four critical operational concerns:
1. Browser / device tab switching
2. RAM bloat prevention (no random window spam)
3. Typing without affecting open work
4. Mouse clicks without affecting open work

Each section shows the **exact execution flow**, **failure modes**, and **mitigations**.

---

## 1. Browser Tab Switching & Device Window Switching

### 1.1 How It Works

Tab/window switching is handled by `Orchestrator.action_switch_tab()` and `Orchestrator.action_switch_window()`.

**Code path for tab switching:**
```python
def action_switch_tab(self):
    ctx = self._get_context_window()      # calls WindowManager.refresh() + get_active_window_id()
    if ctx and ctx.is_browser:            # WindowType.BROWSER detected via _BROWSER_KEYS
        send_key('ctrl+Tab')              # xdotool key ctrl+Tab
        self.stats['switches'] += 1
        return
    if ctx and ctx.is_terminal:           # WindowType.TERMINAL
        send_key('ctrl+Page_Down')        # terminal tab switch
        self.stats['switches'] += 1
        return
    # Fallback: generic Alt+Tab
    send_key('alt+Tab')
```

**Code path for window switching:**
```python
def action_switch_window(self):
    self.windows.refresh()
    others = [w for w in self.windows.windows if w != self.windows.active]
    if not others:
        return                            # GUARD: no other windows = no-op
    target = random.choice(others)
    focus_window(target.id)               # xdotool windowactivate <id>
```

### 1.2 Edge Cases & Mitigations

| Edge Case | What Happens | Mitigation |
|-----------|-------------|------------|
| **No other windows open** | `others` list is empty; `action_switch_window()` returns immediately without any X11 call | Guard clause `if not others: return` |
| **Active window is None** (minimized/hidden) | `ctx` is None; `action_switch_tab()` falls through to `alt+Tab` | Fallback to system-level alt+tab, which cycles whatever windows exist |
| **Browser not recognized** (e.g., niche browser) | `_BROWSER_KEYS` doesn't match; `ctx.is_browser` is False | Falls through to alt+Tab. User can add browser key to `_BROWSER_KEYS` |
| **Ctrl+Tab intercepted by app** (e.g., Emacs uses Ctrl+Tab) | Key goes to active window; behavior depends on app | Terminal fallback uses `ctrl+Page_Down` instead. For editors, alt+Tab is safer |
| **Alt+Tab visual switcher opens** (GNOME/Cinnamon) | The OS switcher UI appears for ~200ms | This is *realistic* — humans use alt+tab. Switcher disappears after key release |
| **Window ID stale after app closes** | `focus_window()` targets a dead window ID | xdotool returns error; orchestrator catches it via try/except in `run()` loop |
| **User was actively typing in a chat** | Watchdog detects real keypress → simulation **PAUSED** for 3s | `InputWatchdog` prevents tab-switch mid-conversation |
| **Only 1 browser tab open** | `ctrl+Tab` wraps around to same tab | No harm done; browser simply re-selects current tab. Time tracker still sees activity |

### 1.3 When Tab Switching Is Selected

The state machine controls when switching happens:

```python
MacroState.SWITCHING: {
    MicroAction.SWITCH_WINDOW: 45,   # 45% chance: switch to different app window
    MicroAction.SWITCH_TAB: 35,      # 35% chance: switch tab in current app
    ...
}
```

- Minimum duration in SWITCHING state: **5–30 seconds**
- So the simulator does not spam switches; it enters a "switching mode" for a realistic period
- Transition probability from READING → SWITCHING is 30%, so it happens naturally after a reading session

---

## 2. RAM Bloat Prevention (No Random Window Spam)

### 2.1 The Original Problem

v1 could spawn unlimited terminals. v2's `SandboxWindow` is designed to create **exactly one** hidden window.

### 2.2 How It Works

**Code path:**
```python
class SandboxWindow:
    def spawn(self) -> Optional[int]:
        existing = self._find_existing()      # scans wmctrl -l -x for "__sim_sandbox__"
        if existing:
            self._win_id = existing
            self._hide()                      # reuse + re-hide
            return existing

        # Try terminal emulators ONE BY ONE
        for cmd in term_cmds:                 # xterm, gnome-terminal, urxvt, alacritty, kitty
            try:
                self._proc = subprocess.Popen(cmd, ...)
                for _ in range(10):           # wait up to 3 seconds
                    time.sleep(0.3)
                    wid = self._find_existing()
                    if wid:
                        self._win_id = wid
                        self._hide()
                        return wid
                # FAILED — kill it before trying next
                self._proc.terminate()
                self._proc.wait(timeout=2)
                self._proc = None
            except FileNotFoundError:
                continue                        # try next terminal
        return None                            # nothing worked
```

### 2.3 Edge Cases & Mitigations

| Edge Case | What Happens | Mitigation |
|-----------|-------------|------------|
| **Simulator restarted** | `spawn()` checks for existing sandbox window first | `_find_existing()` returns the old window ID; no new process created |
| **Sandbox process crashes** | `_find_existing()` returns None on next `spawn()` call | A new sandbox is spawned. Old zombie process is not cleaned up (OS handles it) |
| **No terminal emulator installed** | All `term_cmds` raise `FileNotFoundError` | Returns None. Orchestrator detects this and disables typing: `if self.sandbox.win_id is None: log("WARNING: No sandbox; skipping typing"); return` |
| **Terminal spawns but doesn't register with WM** | `_find_existing()` never finds it | After 3s timeout, `terminate()` + `wait()` kills it. No orphan window |
| **Multiple copies of simulator running** | Each copy calls `spawn()` independently | Each copy finds the SAME existing window (shared title substring). Only 1 window total. However, each copy has its own subprocess reference; cleanup by one copy may kill the window for others. | **Mitigation:** Use a file lock or PID file if running multiple instances |
| **User manually closes sandbox window** | `_find_existing()` returns None; typing is skipped | Simulator logs warning and continues with scroll/switch actions only |
| **Window manager ignores off-screen coordinates** | Some WMs (i3, Awesome) force windows onto screen | `_hide()` also calls `xdotool windowminimize`. Minimized windows are invisible even if coordinates are clamped |
| **Sandbox window appears in alt+tab** | Yes, it is a real window | Title is `__sim_sandbox__` so user knows what it is. It is minimized so it doesn't steal focus. It appears rarely because user is not switching windows during simulation (they're away) |

### 2.4 RAM Impact

| Component | Memory Cost | When Freed |
|-----------|------------|------------|
| 1 xterm/gnome-terminal | ~15–40 MB | On `cleanup()` or process termination |
| Python simulator process | ~20–30 MB | On exit |
| xdotool subprocesses | ~2–5 MB each, transient | Immediately after command returns |
| **Total steady-state** | **~35–70 MB** | — |

Compare to v1 (unlimited terminal spam): RAM would grow linearly with session duration.

---

## 3. Typing Without Affecting Open Work

### 3.1 The Threat Model

If typing goes to the wrong window, it can:
- Send messages in Slack/Discord
- Execute commands in a real terminal (`rm -rf /`)
- Edit and save production code with garbage
- Type passwords into visible chat windows

### 3.2 How It Works (Defense in Depth)

**Layer 1 — Sandbox Isolation:**
```python
def action_type_burst(self):
    ...
    if self.sandbox.win_id is None:
        self.log("WARNING: No sandbox; skipping typing")
        return                          # HARD GUARD: no sink = no typing
```

**Layer 2 — Focus Switching:**
```python
    self._previous_active_id = get_active_window_id()   # Remember where we were
    ok = self._focus_sandbox()                           # Focus hidden sandbox
    if not ok:
        return                                              # If focus fails, bail out
    self.typing.type_burst(text, with_shortcuts=True)    # Type ONLY into sandbox
    self._unfocus_sandbox()                              # Hide sandbox again
    self._restore_previous_window()                      # Return to user's window
```

**Layer 3 — Content Whitelist:**
```python
# SafetyGovernor
def check_type_text(self, text: str) -> bool:
    return bool(self.ALLOWED_CHARS_RE.match(text))      # Only printable ASCII
```

**Layer 4 — No Dangerous Shortcuts:**
```python
# TypingModel never sends Alt+F4, Ctrl+W, Super+L, etc.
# Shortcuts used: ctrl+s, ctrl+a, ctrl+c, ctrl+v, ctrl+z only
```

**Layer 5 — User Input Watchdog:**
```python
if self.watchdog.is_user_active:
    time.sleep(self.POLL_INTERVAL)
    continue                        # If user is typing, WE DO NOTHING
```

### 3.3 Edge Cases & Mitigations

| Edge Case | What Happens | Mitigation |
|-----------|-------------|------------|
| **Sandbox focus fails** (WM blocks it) | `focus_window()` returns False | `action_type_burst()` returns immediately. Text is NOT sent anywhere |
| **Window manager doesn't allow off-screen focus** | Sandbox is at (0,0) during focus, then hidden after | `focus()` moves it on-screen briefly, `unfocus()` hides it again. Brief flash is possible but harmless |
| **Previous window was closed while typing** | `_restore_previous_window()` focuses a dead ID | xdotool error is swallowed. User may need to click their app manually. This is a **graceful degradation** |
| **Sandbox title collides with real window** | `_find_existing()` might match a user window named "__sim_sandbox__" | Probability is near-zero. Title uses double underscores which is uncommon. Could be hardened with UUID |
| **User returns during typing burst** | Watchdog detects mouse/key → simulation pauses | BUT: the typing burst is already in progress in the sandbox. This is SAFE because it's going to the sandbox, not the user's active window |
| **Clipboard sync poisoned** | `ctrl+c` in sandbox copies sandbox text to clipboard | Yes, this happens. Mitigation: sandbox text is harmless random code/prose. Could be improved by using `xclip` to restore original clipboard |
| **gnome-terminal interprets typed text as commands** | Text is typed into the sandbox terminal | The terminal will try to execute newlines as commands. This is fine — it's a hidden sandbox. The commands are harmless (e.g., `ls -la`, `git status`) |

### 3.4 What Could Still Go Wrong

| Risk | Likelihood | Impact | Mitigation Needed |
|------|-----------|--------|-------------------|
| xdotool sends keys to wrong window due to race condition | Low | High (garbage typed into active window) | Add `xdotool windowfocus --sync` before typing; verify active window is sandbox |
| WM ignores `windowmove` and keeps sandbox visible | Low | Low (annoyance) | Already mitigated with `windowminimize` |
| User had unsaved work in terminal; simulator switches to sandbox then back; terminal loses focus but no data loss | Medium | None | Focus change alone doesn't destroy data |

---

## 4. Mouse Clicks Without Affecting Open Work

### 4.1 Philosophy

**The revised simulator almost never clicks.**

Looking at the state machine action weights:
```python
MacroState.READING: {
    MicroAction.SCROLL: 50,        # scroll wheel
    MicroAction.MOUSE_NUDGE: 20,   # small cursor movement only
    MicroAction.READING_PAUSE: 25, # do nothing
    MicroAction.SWITCH_TAB: 5,     # keyboard shortcut
}
```

There is **no `CLICK` micro-action** in the current state machine. The only mouse interaction is:
1. **SCROLL** — wheel events (button 4/5) at current cursor position
2. **MOUSE_NUDGE** — moves cursor ≤100px, no click

The old `ClickPlanner` still exists in the codebase but is **not invoked** by the orchestrator.

### 4.2 How Scrolling Works

```python
def action_scroll(self):
    ctx = self._get_context_window()
    direction = random.choice(['up', 'down', 'down', 'down'])
    amount = random.randint(2, 6)
    if ctx and ctx.is_terminal:
        amount = random.randint(1, 3)    # smaller scrolls in terminal

    button = '4' if direction == 'up' else '5'
    for _ in range(amount):
        click_button(button)             # xdotool click 4 or click 5
        time.sleep(random.uniform(0.06, 0.14))
```

### 4.3 How Mouse Nudge Works

```python
def small_nudge():
    x0, y0 = get_mouse_pos()
    max_nudge = 100                      # ONLY 100px max!
    tx = x0 + random.randint(-100, 100)
    ty = y0 + random.randint(-100, 100)
    return bezier_move(tx, ty, duration=0.3-0.6, overshoot_prob=0)
```

### 4.4 Edge Cases & Mitigations

| Edge Case | What Happens | Mitigation |
|-----------|-------------|------------|
| **Cursor is over a "Delete" button** | Scroll wheel doesn't click; it only scrolls the content under the cursor | Scroll is harmless in almost all contexts |
| **Cursor is over a modal dialog** | Scroll might dismiss or interact with the dialog | Probability is low (dialogs are temporary). If critical, user input watchdog will detect mouse movement and pause simulation |
| **Cursor over terminal; scroll sends escape sequences** | Terminal interprets scroll as history navigation | This is expected terminal behavior and harmless |
| **Cursor over image editor; scroll zooms unexpectedly** | Scroll zooms in/out of image | Slightly annoying but non-destructive. Mitigation: mouse nudge (which moves cursor) happens more often than scroll, so cursor doesn't stay in one place forever |
| **Mouse nudge moves cursor onto close button** | No click is performed, so window doesn't close | Nudge is movement only. No button press |
| **User returns and grabs mouse; cursor is somewhere unexpected** | Cursor moved ≤100px from where user left it | 100px is small enough that user won't be disoriented. If this is unacceptable, disable `MOUSE_NUDGE` entirely by setting its weight to 0 |
| **Cursor nudged off-screen** (single monitor) | `bezier_move()` clamps to screen bounds via `move_mouse_raw` | xdotool handles off-screen coordinates gracefully |
| **Scroll in a dropdown menu** | May change the selected option | Dropdowns close when they lose focus. Since we don't click, the dropdown stays open only briefly. Risk is minimal |

### 4.5 What About the Old Click Code?

`ClickPlanner` (in `simulator/input_engine/clicks.py`) has these safety features if ever re-enabled:

```python
def click_in_window(self, window, button='1', double=False):
    geo = get_window_geometry(window.id)
    point = self.screen.safe_point_in_window(
        geo['x'], geo['y'], geo['width'], geo['height']
    )
    # safe_point_in_window avoids:
    #   - Top 40px (title bar)
    #   - Bottom 40px (dock)
    #   - Top-right 120px (close buttons)
```

But as stated, **no click actions are currently scheduled** by the state machine. The click code exists only as a safety-hardened utility for future extensions.

---

## 5. Summary Matrix

| Concern | Primary Mechanism | Secondary Guard | Tertiary Guard |
|---------|------------------|-----------------|----------------|
| **Browser tabs** | `ctrl+Tab` when `ctx.is_browser` | `alt+Tab` fallback | State machine limits switching frequency |
| **Window tabs** | `xdotool windowactivate` on existing window | `others` list filter excludes self | No-op if no other windows |
| **RAM bloat** | `_find_existing()` reuses window | `terminate()` + `wait()` if spawn fails | Cleanup on shutdown |
| **Typing safety** | Hidden sandbox + focus switch | Governor whitelists printable chars | Watchdog pauses if user active |
| **Click safety** | **No clicks scheduled** | Scroll wheel only (no button 1/3) | Mouse nudge ≤100px |
| **User override** | InputWatchdog pauses simulation | 3-second cooldown after activity | Keyboard + mouse both monitored |

---

## 6. Known Gaps & Recommendations

| Gap | Recommendation |
|-----|----------------|
| Sandbox title collision risk | Append UUID: `__sim_sandbox_<pid>__` |
| Clipboard pollution from `ctrl+c` | Save/restore clipboard via `xclip` around typing bursts |
| No check that sandbox is ACTUALLY focused before typing | Add `assert get_active_window_id() == sandbox.win_id` before `type_burst()` |
| Scroll over sensitive UI | Add `get_window_geometry` check to avoid scrolling over small modal windows |
| Multiple simulator instances share sandbox | Add PID-based file lock in `/tmp/simulator.lock` |
| No way to disable mouse nudge entirely | Add CLI flag `--no-mouse` to set `MOUSE_NUDGE` weight to 0 |
