#!/usr/bin/env python3
"""
Comprehensive Evaluation Runner for Activity Simulator v2.

Runs unit tests + integration tests, collects metrics, and produces
an Expected vs Actual report.

Usage:
    python tests/run_evaluation.py [--unit-only] [--integration-only]

Requires X11 display for integration tests. Use xvfb for headless:
    xvfb-run python tests/run_evaluation.py
"""
import sys
import os
import argparse
import time
import unittest
import math
from typing import Dict, List, Tuple

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.capture_utils import check_display_available


# Expected vs Actual claims matrix
CLAIMS: List[Dict] = [
    {
        "id": "M1", "component": "Mouse Physics", "claim": "Bézier curves with ease-in-out velocity",
        "criteria": "Path non-linear; max deviation from straight line > 10px; velocity peaks in middle",
        "test_module": "tests.test_motion", "test_class": "TestMousePhysicsIntegration",
        "needs_display": True, "severity": "MUST"
    },
    {
        "id": "M2", "component": "Mouse Physics", "claim": "Hand tremor (Gaussian jitter)",
        "criteria": "Position delta stddev in [0.2, 2.0] px during motion",
        "test_module": "tests.test_motion", "test_class": "TestMousePhysicsIntegration",
        "needs_display": True, "severity": "SHOULD"
    },
    {
        "id": "M3", "component": "Mouse Physics", "claim": "Overshoot on ~12% of moves",
        "criteria": "8–35% of 30 trials show overshoot-and-correct pattern",
        "test_module": "tests.test_motion", "test_class": "TestMousePhysicsIntegration",
        "needs_display": True, "severity": "SHOULD"
    },
    {
        "id": "M4", "component": "Mouse Physics", "claim": "No danger-zone clicks",
        "criteria": "All planned click coordinates outside ScreenManager danger zones",
        "test_module": "tests.test_motion", "test_class": "TestMousePhysicsIntegration",
        "needs_display": True, "severity": "MUST"
    },
    {
        "id": "T1", "component": "Typing", "claim": "Real X11 KeyPress events generated",
        "criteria": "xinput test captures > 0.5 * len(text) key press events",
        "test_module": "tests.test_typing", "test_class": "TestTypingIntegration",
        "needs_display": True, "severity": "MUST"
    },
    {
        "id": "T2", "component": "Typing", "claim": "Log-normal inter-key delay",
        "criteria": "Burst duration proportional to text length; not instant",
        "test_module": "tests.test_typing", "test_class": "TestTypingIntegration",
        "needs_display": True, "severity": "SHOULD"
    },
    {
        "id": "T3", "component": "Typing", "claim": "Error rate ~2.5% with backspace correction",
        "criteria": "Backspace keycode events observed under high error rate",
        "test_module": "tests.test_typing", "test_class": "TestTypingIntegration",
        "needs_display": True, "severity": "SHOULD"
    },
    {
        "id": "T4", "component": "Typing", "claim": "Shortcuts injected (~6%)",
        "criteria": "Ctrl key events observed during multi-burst sampling",
        "test_module": "tests.test_typing", "test_class": "TestTypingIntegration",
        "needs_display": True, "severity": "SHOULD"
    },
    {
        "id": "T5", "component": "Typing", "claim": "Sandbox isolation",
        "criteria": "Window focus logs show sandbox focused during typing",
        "test_module": "tests.test_typing", "test_class": "TestTypingIntegration",
        "needs_display": True, "severity": "MUST"
    },
    {
        "id": "S1", "component": "State Machine", "claim": "Sticky minimum durations enforced",
        "criteria": "can_transition() returns False before min duration",
        "test_module": "tests.test_unit", "test_class": "TestStateMachineUnit",
        "needs_display": False, "severity": "MUST"
    },
    {
        "id": "S2", "component": "State Machine", "claim": "Contextual action weights",
        "criteria": "Sampled action frequencies match weight table within ±10%",
        "test_module": "tests.test_unit", "test_class": "TestStateMachineUnit",
        "needs_display": False, "severity": "SHOULD"
    },
    {
        "id": "S3", "component": "State Machine", "claim": "Fatigue increases break probability",
        "criteria": "fatigue_factor() increases monotonically with elapsed time",
        "test_module": "tests.test_integration", "test_class": "TestIntegration",
        "needs_display": False, "severity": "SHOULD"
    },
    {
        "id": "C1", "component": "Context", "claim": "Window ID normalization",
        "criteria": "wmctrl hex IDs and xdotool decimal IDs match 100%",
        "test_module": "tests.test_integration", "test_class": "TestIntegration",
        "needs_display": True, "severity": "SHOULD"
    },
    {
        "id": "F1", "component": "Safety", "claim": "Forbidden keys blocked",
        "criteria": "Governor rejects Alt+F4, Ctrl+W, etc.",
        "test_module": "tests.test_unit", "test_class": "TestSafetyGovernorUnit",
        "needs_display": False, "severity": "MUST"
    },
    {
        "id": "F2", "component": "Safety", "claim": "Unsafe text blocked",
        "criteria": "Governor rejects strings with control characters",
        "test_module": "tests.test_unit", "test_class": "TestSafetyGovernorUnit",
        "needs_display": False, "severity": "MUST"
    },
    {
        "id": "I1", "component": "Integration", "claim": "End-to-end session stable",
        "criteria": "30s run: no crashes, all stats increase, no destructive actions",
        "test_module": "tests.test_integration", "test_class": "TestIntegration",
        "needs_display": True, "severity": "MUST"
    },
]


# Map claim IDs to specific test method names
CLAIM_TEST_METHODS: Dict[str, str] = {
    "M1": "test_bezier_path_is_non_linear",
    "M2": "test_hand_tremor_present",
    "M3": "test_overshoot_detected",
    "M4": "test_click_avoids_danger_zones",
    "T1": "test_typing_generates_actual_key_events",
    "T2": "test_inter_key_delays_vary",
    "T3": "test_error_injection_produces_backspaces",
    "T4": "test_shortcut_injection_occurs",
    "T5": "test_sandbox_isolation",
    "S1": "test_cannot_transition_before_min_duration",
    "S2": "test_action_distribution_roughly_matches_weights",
    "S3": "test_fatigue_increases_over_session",
    "C1": "test_window_classification_non_empty",
    "F1": "test_forbidden_keys_blocked",
    "F2": "test_unsafe_text_blocked",
    "I1": "test_orchestrator_runs_without_crash",
}


def load_tests_from_claim(claim: Dict) -> unittest.TestSuite:
    """Dynamically load the specific test method for a claim."""
    module_name = claim["test_module"]
    class_name = claim["test_class"]
    method_name = CLAIM_TEST_METHODS.get(claim["id"])
    try:
        __import__(module_name)
        module = sys.modules[module_name]
        test_class = getattr(module, class_name)
        if method_name:
            suite = unittest.TestSuite()
            suite.addTest(test_class(method_name))
            return suite
        return unittest.TestLoader().loadTestsFromTestCase(test_class)
    except Exception as e:
        print(f"  ERROR loading {module_name}.{class_name}.{method_name}: {e}")
        return unittest.TestSuite()


def run_claim(claim: Dict, runner: unittest.TextTestRunner) -> Tuple[bool, str]:
    """Run tests for a single claim. Returns (passed, details)."""
    if claim["needs_display"] and not check_display_available():
        return False, "SKIPPED (no X11 display)"

    suite = load_tests_from_claim(claim)
    if suite.countTestCases() == 0:
        return False, "NO TESTS LOADED"

    # Capture output by giving stream=io.StringIO if we want quiet
    result = runner.run(suite)
    passed = result.wasSuccessful()
    details = f"ran={result.testsRun} errors={len(result.errors)} failures={len(result.failures)}"
    return passed, details


def print_banner(text: str, width: int = 70):
    print("\n" + "=" * width)
    print(text.center(width))
    print("=" * width)


def main():
    parser = argparse.ArgumentParser(description="Activity Simulator v2 Evaluation")
    parser.add_argument("--unit-only", action="store_true",
                        help="Only run unit tests (no X11 required)")
    parser.add_argument("--integration-only", action="store_true",
                        help="Only run integration tests (requires X11)")
    parser.add_argument("--claim", type=str, default=None,
                        help="Run only a specific claim ID (e.g., M1, T1)")
    args = parser.parse_args()

    display_ok = check_display_available()
    print_banner("ACTIVITY SIMULATOR v2 — EVALUATION REPORT")
    print(f"Display available: {display_ok}")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    claims_to_run = CLAIMS
    if args.claim:
        claims_to_run = [c for c in CLAIMS if c["id"] == args.claim]
        if not claims_to_run:
            print(f"Unknown claim ID: {args.claim}")
            sys.exit(1)
    elif args.unit_only:
        claims_to_run = [c for c in CLAIMS if not c["needs_display"]]
    elif args.integration_only:
        claims_to_run = [c for c in CLAIMS if c["needs_display"]]

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)

    results: List[Dict] = []
    must_pass_failed = 0
    total_passed = 0
    total_failed = 0

    for claim in claims_to_run:
        print_banner(f"CLAIM {claim['id']}: {claim['claim']}", width=70)
        print(f"Component : {claim['component']}")
        print(f"Criteria  : {claim['criteria']}")
        print(f"Severity  : {claim['severity']}")
        print(f"Needs X11 : {claim['needs_display']}")
        print("-" * 70)

        start = time.time()
        passed, details = run_claim(claim, runner)
        elapsed = time.time() - start

        status = "PASS" if passed else "FAIL"
        if not passed and claim["severity"] == "MUST":
            must_pass_failed += 1

        if passed:
            total_passed += 1
        else:
            total_failed += 1

        results.append({
            **claim,
            "status": status,
            "details": details,
            "elapsed": elapsed,
        })
        print(f"\nResult: {status} ({details}) [{elapsed:.1f}s]\n")

    # Summary table
    print_banner("EVALUATION SUMMARY", width=70)
    print(f"{'ID':<5} {'Severity':<6} {'Status':<6} {'Component':<18} {'Claim'}")
    print("-" * 70)
    for r in results:
        print(f"{r['id']:<5} {r['severity']:<6} {r['status']:<6} {r['component']:<18} {r['claim'][:40]}")

    print("\n" + "=" * 70)
    print(f"Total claims evaluated: {len(results)}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"MUST-pass failures: {must_pass_failed}")
    print("=" * 70)

    if must_pass_failed > 0:
        print("\n❌ EVALUATION FAILED: One or more MUST-pass criteria were not met.")
        sys.exit(1)
    elif total_failed > 0:
        print("\n⚠️  EVALUATION CONDITIONAL: All MUST-pass criteria met, but some SHOULD-pass failed.")
        sys.exit(0)
    else:
        print("\n✅ EVALUATION PASSED: All criteria met.")
        sys.exit(0)


if __name__ == '__main__':
    main()
