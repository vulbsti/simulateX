# Activity Simulator v2 — Test & Evaluation Suite

## Quick Start

### Unit Tests Only (No X11 Required)
```bash
cd /path/to/project
python3 -m unittest tests.test_unit -v
```

### Full Evaluation (Requires X11 Desktop)
```bash
# On a real Ubuntu desktop with X running:
python3 tests/run_evaluation.py

# Specific claim only:
python3 tests/run_evaluation.py --claim M1

# Unit tests only:
python3 tests/run_evaluation.py --unit-only

# Integration tests only:
python3 tests/run_evaluation.py --integration-only
```

### Headless / CI (Xvfb)
```bash
xvfb-run -a python3 tests/run_evaluation.py
```

## Test Structure

| File | What It Tests | Needs X11? |
|------|---------------|------------|
| `test_unit.py` | State machine, safety governor, temporal model, screen math | No |
| `test_motion.py` | Bézier curves, velocity profile, overshoot, danger zones | Yes |
| `test_typing.py` | Real keystrokes, timing, errors, sandbox isolation | Yes |
| `test_integration.py` | End-to-end session stability, fatigue, sandbox lifecycle | Yes |
| `run_evaluation.py` | Full Expected vs Actual report with pass/fail matrix | Mixed |

## Expected vs Actual Claims

See `evaluation_plan.md` for the complete verification matrix. Each claim maps to:
- **MUST**: Critical requirement. Any failure rejects the implementation.
- **SHOULD**: Recommended requirement. Failure is noted but not fatal.

## Interpreting Results

### PASS
The implementation matches the design specification for this claim.

### FAIL
The implementation deviates from specification. Check the test output for:
- Assertion messages showing expected vs observed values
- Stack traces for exceptions
- "SKIPPED" means the test couldn't run (usually missing X11)

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "No X11 display available" | Running over SSH without X forwarding | Use `ssh -X` or run locally |
| "Keyboard capture unavailable" | xinput can't find keyboard device | Run on a real desktop session |
| "Too few samples captured" | xdotool polling too slow / display frozen | Check X11 responsiveness |
| "Sandbox window was never focused" | wmctrl/xdotool window focus blocked by WM | Test on a standard Ubuntu session |
