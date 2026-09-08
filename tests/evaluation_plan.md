# Activity Simulator v2 — Comprehensive Evaluation Plan

## Objective

Verify that the implemented simulator behaves exactly as specified in `DESIGN.md`. Every claim about physics, statefulness, safety, and realism must be tested against actual X11 behavior.

---

## 1. Evaluation Taxonomy

| ID | Component | What We Claim | How To Verify | Pass Criteria |
|----|-----------|---------------|---------------|---------------|
| M1 | Mouse Physics | Bézier curves with ease-in-out | Capture (x,y) at 100Hz during move; fit curvature | Path is non-linear; R² of linear fit < 0.95 |
| M2 | Mouse Physics | Hand tremor (Gaussian jitter) | Measure point-to-point delta variance | Stddev > 0.2px and < 2.0px |
| M3 | Mouse Physics | Overshoot on ~12% of moves | Run 100 moves; count overshoots | 8–20 overshoots observed |
| M4 | Mouse Physics | No danger-zone clicks | Attempt 50 random clicks; verify coordinates | 0 clicks in danger zones |
| T1 | Typing | Real X11 KeyPress events | Use `xinput test` or window content diff | Events registered; text appears in sandbox |
| T2 | Typing | Log-normal inter-key delay | Timestamp every key event | Delay distribution passes Shapiro-Wilk for lognormality |
| T3 | Typing | Error rate ~2.5% | Type 1000 chars; count backspace corrections | 15–40 error corrections observed |
| T4 | Typing | Shortcuts injected (~6%) | Run burst sampling | Ctrl+S/C/V/Z observed in event stream |
| T5 | Typing | Sandbox isolation | Type burst while different window is "active" | Text appears only in sandbox window |
| S1 | State Machine | Sticky minimum durations | Log state entry/exit timestamps | No state exits before its min duration |
| S2 | State Machine | Contextual action weights | Sample 500 actions per state | Action frequencies match weight table within ±10% |
| S3 | State Machine | Fatigue increases breaks | Run 2 hours; plot break frequency | Break probability increases monotonically with elapsed time |
| C1 | Context | Window ID normalization | Create test windows; compare wmctrl vs xdotool IDs | 100% match rate; no type confusion |
| C2 | Context | Danger zone blacklist | Query screen zones; attempt clicks near edges | Clicks blocked in top 40px, bottom 40px, top-right 120px |
| F1 | Safety | Forbidden keys blocked | Attempt Alt+F4, Ctrl+W, etc. | All blocked; no window closes |
| F2 | Safety | Unsafe text blocked | Attempt text with control chars | Governor rejects before sending |
| I1 | Integration | End-to-end session | Run 5-minute session; capture all events | No crashes; all stats increase; no destructive actions |

---

## 2. Test Infrastructure

### 2.1 Real-Time Capture Backend

We need to observe actual system state during tests:

```
Mouse Capture:    poll `xdotool getmouselocation` at 60–100Hz
Keyboard Capture: `xinput test <keyboard_id>` piped to parser
Window Capture:   `xdotool getactivewindow` polled at 10Hz
Content Capture:  `xprop -id <sandbox_id> WM_NAME` or direct window read
```

### 2.2 Test Modes

1. **Unit Mode**: Test logic in isolation (no X11 calls). Fast. Deterministic.
2. **Integration Mode**: Uses real X11. Requires display. May be run inside Xvfb for CI.
3. **Long-Run Mode**: 30+ minute sessions to verify fatigue and circadian models.

### 2.3 Metrics & Analysis

- **Path curvature**: Fit polynomial to mouse track; measure max deviation from straight line
- **Jitter spectrum**: FFT of position deltas to verify noise isn't periodic
- **Timing accuracy**: Compare intended delay vs actual sleep (account for scheduler jitter)
- **State coverage**: Markov chain coverage matrix

---

## 3. Evaluation Procedures

### Procedure M: Mouse Physics Evaluation

```
Setup:
  1. Start X11 capture polling at 100Hz
  2. Execute 50 bezier_move() calls to random targets
  3. For each move, record [(t0,x0,y0), (t1,x1,y1), ...]

Analysis:
  A. Straightness: For each path, compute linear interpolation between endpoints.
     Measure max perpendicular distance from any sample to this line.
     PASS if median max deviation > 15px.

  B. Velocity profile: Compute speed between consecutive samples.
     Verify it rises then falls (peak in middle 40% of duration).
     PASS if > 80% of moves show this pattern.

  C. Overshoot: Detect if final samples exceed target then return.
     PASS if 8–24 of 50 moves show overshoot.

  D. Tremor: Compute diff series dx,dy. Verify Gaussian via histogram.
     PASS if stddev in [0.2, 2.0] and no periodic spikes.
```

### Procedure T: Typing Evaluation

```
Setup:
  1. Spawn sandbox window
  2. Start `xinput test <kbd>` in background, log to file
  3. Execute 20 typing bursts of ~50 chars each
  4. Also run xdotool-type sequences with known timing

Analysis:
  A. Event count: Count key press events in log.
     PASS if events ≈ chars typed + backspaces + shortcuts.

  B. Timing: Parse key timestamps. Compute inter-key delays.
     PASS if distribution is right-skewed (log-normal), not uniform.

  C. Error rate: Count backspace events / total char events.
     PASS if ratio is 0.015–0.045.

  D. Sandbox focus: Before each burst, verify active window is sandbox.
     After burst, verify focus can be restored.
     PASS if 100% focus correctness.
```

### Procedure S: State Machine Evaluation

```
Setup:
  1. Run simulator in safe_mode=True for 30 minutes
  2. Log every state entry, exit, sampled action

Analysis:
  A. Minimum duration: For each state instance, compute duration.
     PASS if no instance is shorter than STATE_MIN_DURATION[state].min.

  B. Action distribution: Per state, count action frequencies.
     PASS if frequencies are within ±15% of weight ratios.

  C. Transition graph: Build observed transition matrix.
     PASS if all non-zero transitions from design are observed at least once.

  D. Fatigue: Group session into 5-minute buckets.
     Compute break rate per bucket.
     PASS if break rate increases over time (Spearman ρ > 0.3).
```

### Procedure C: Context & Safety Evaluation

```
Setup:
  1. Open a browser, terminal, and editor window
  2. Run window classification
  3. Attempt 20 clicks in each window
  4. Attempt forbidden keystrokes

Analysis:
  A. Classification accuracy: Compare detected type vs known type.
     PASS if 100% accuracy on known windows.

  B. Danger zone: For each click, verify coordinate.
     PASS if 0 clicks in danger zones.

  C. Forbidden keys: Verify governor rejects Alt+F4, Ctrl+W.
     PASS if rejection rate = 100%.
```

---

## 4. Acceptance Thresholds

| Category | Must Pass | Should Pass |
|----------|-----------|-------------|
| Mouse physics | M1, M4 | M2, M3 |
| Typing | T1, T5 | T2, T3, T4 |
| State machine | S1 | S2, S3 |
| Context | C1 | C2 |
| Safety | F1, F2 | — |
| Integration | I1 | — |

If any "Must Pass" fails, the implementation is rejected.

---

## 5. CI / Automation

For headless testing, use Xvfb:
```bash
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 python -m pytest tests/ --integration
```

Long-run tests should be parameterized:
```bash
python tests/run_evaluation.py --mode=longrun --duration=120
```
