"""Single verification command to run before every commit: style (ruff) and tests (pytest).

Usage: python check.py

A step that did not actually run is reported as SKIP, never as PASS.
"""

import subprocess
import sys

PYTEST_NO_TESTS_COLLECTED = 5

STEPS = [
    ("Layer 1: style (ruff)", [sys.executable, "-m", "ruff", "check", "."]),
    ("Layer 2: tests (pytest)", [sys.executable, "-m", "pytest", "-q"]),
]


def main() -> int:
    skipped = []
    for name, command in STEPS:
        print(f"\n=== {name} ===")
        code = subprocess.run(command).returncode
        if code == PYTEST_NO_TESTS_COLLECTED and "pytest" in command:
            print(f"[SKIP] {name}: no tests yet")
            skipped.append(name)
        elif code != 0:
            print(f"[FAIL] {name}")
            return 1
        else:
            print(f"[PASS] {name}")

    if skipped:
        print(f"\nVerification incomplete, skipped steps: {', '.join(skipped)}")
    else:
        print("\nAll layers pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
