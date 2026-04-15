#!/usr/bin/env python3
"""
Preview the e-ink dashboard as a PNG file.

Use this to iterate on the layout without the physical display.
Generates preview.png in the current directory and also opens it
if a display is available.
"""

import sys
import os
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_claude import UsageBucket
from render import render_dashboard

# ─── Sample Data ──────────────────────────────────────────────────

now_utc = datetime.now(timezone.utc)

# Simulate various usage levels to see how the layout handles them
SCENARIOS = {
    "normal": {
        "claude": [
            UsageBucket("Current session", 72.0, now_utc + timedelta(hours=2, minutes=48)),
            UsageBucket("Weekly", 48.0, now_utc + timedelta(days=3, hours=5)),
        ],
        "codex": [
            UsageBucket("Current session", 82.0, now_utc + timedelta(hours=3, minutes=13)),
            UsageBucket("Weekly", 36.0, now_utc + timedelta(days=2, hours=1)),
        ],
    },
    "low": {
        "claude": [
            UsageBucket("Current session", 15.0, now_utc + timedelta(hours=1)),
            UsageBucket("Weekly", 8.0, now_utc + timedelta(days=1)),
        ],
        "codex": [
            UsageBucket("Current session", 22.0, now_utc + timedelta(hours=2)),
            UsageBucket("Weekly", 5.0, now_utc + timedelta(days=4)),
        ],
    },
    "full": {
        "claude": [
            UsageBucket("Current session", 95.0, now_utc + timedelta(hours=4)),
            UsageBucket("Weekly", 88.0, now_utc + timedelta(days=6)),
        ],
        "codex": [
            UsageBucket("Current session", 100.0, now_utc + timedelta(hours=5)),
            UsageBucket("Weekly", 92.0, now_utc + timedelta(days=5)),
        ],
    },
    "empty": {
        "claude": [
            UsageBucket("Current session", 0.0, now_utc + timedelta(hours=0, minutes=30)),
            UsageBucket("Weekly", 3.0, now_utc + timedelta(hours=12)),
        ],
        "codex": [
            UsageBucket("Current session", 0.0, now_utc + timedelta(hours=1)),
            UsageBucket("Weekly", 0.0, now_utc + timedelta(days=1)),
        ],
    },
    "unavailable": {
        "claude": [
            UsageBucket("Current session", -1),
            UsageBucket("Weekly", -1),
        ],
        "codex": [
            UsageBucket("Current session", -1),
            UsageBucket("Weekly", -1),
        ],
    },
}


def main():
    scenario = "normal"

    # Allow choosing scenario from command line
    if len(sys.argv) > 1:
        scenario = sys.argv[1]

    if scenario == "all":
        # Render all scenarios
        for name, data in SCENARIOS.items():
            img = render_dashboard(data["claude"], data["codex"])
            filename = f"preview_{name}.png"
            img.save(filename)
            print(f"Saved {filename}")

            # Also save a scaled-up version for easier viewing
            scaled = img.resize((1600, 960), resample=0)  # nearest neighbor
            scaled.save(f"preview_{name}_2x.png")

        print(f"\nGenerated {len(SCENARIOS)} preview images")
        return

    if scenario not in SCENARIOS:
        print(f"Unknown scenario: {scenario}")
        print(f"Available: {', '.join(SCENARIOS.keys())}, all")
        sys.exit(1)

    data = SCENARIOS[scenario]
    img = render_dashboard(data["claude"], data["codex"])

    # Save at native resolution
    filename = "preview.png"
    img.save(filename)
    print(f"Saved {filename} (800×480, scenario: {scenario})")

    # Also save 2x for easier viewing on HiDPI screens
    scaled = img.resize((1600, 960), resample=0)
    scaled.save("preview_2x.png")
    print("Saved preview_2x.png (1600×960, 2x scale)")

    # Try to open the image
    try:
        if sys.platform == "darwin":
            os.system(f"open {filename}")
        elif sys.platform == "linux" and os.environ.get("DISPLAY"):
            os.system(f"xdg-open {filename} &")
    except Exception:
        pass

    print(f"\nTip: Run `python3 preview.py all` to generate all scenarios")
    print(f"Scenarios: {', '.join(SCENARIOS.keys())}")


if __name__ == "__main__":
    main()
