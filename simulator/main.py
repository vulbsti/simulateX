#!/usr/bin/env python3
"""CLI entrypoint for Activity Simulator v2.1 (Kernel-Level Input)."""
import argparse
import sys
import signal

from simulator.orchestrator import Orchestrator
from simulator.utils.x11 import X11Error


def check_deps():
    missing = []
    for tool in ['xdotool', 'wmctrl', 'xrandr']:
        try:
            import subprocess
            subprocess.run(['which', tool], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            missing.append(tool)
    if missing:
        print("Missing required tools. Install with:")
        print(f"  sudo apt install {' '.join(missing)}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Activity Simulator v2.1 — Kernel-Level Human Activity Engine'
    )
    parser.add_argument('--safe', action='store_true',
                        help='Dry-run mode: log actions without sending inputs')
    parser.add_argument('--quiet', action='store_true',
                        help='Minimal logging')
    parser.add_argument('--no-uinput', action='store_true',
                        help='Force xdotool fallback (disable kernel uinput)')
    parser.add_argument('--error-rate', type=float, default=0.025,
                        help='Typing error rate (0.0–1.0)')
    args = parser.parse_args()

    if not check_deps():
        sys.exit(1)

    orch = Orchestrator(
        safe_mode=args.safe,
        verbose=not args.quiet,
        use_uinput=not args.no_uinput
    )
    orch.typing.error_rate = args.error_rate

    def sig_handler(sig, frame):
        print("\nReceived interrupt, stopping gracefully...")
        orch.stop()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        orch.run()
    except X11Error as e:
        print(f"X11 error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
