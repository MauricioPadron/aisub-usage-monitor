#!/usr/bin/env python3
"""
Usage Monitor — Main Loop

Fetches Claude Code and Codex usage data, renders the dashboard,
and displays it on the Waveshare e-ink screen. Repeats every
REFRESH_INTERVAL_MINUTES.
"""

import sys
import time
import signal
import logging
from datetime import datetime

import config
from fetch_claude import fetch_claude_usage
from fetch_codex import fetch_codex_usage
from render import render_dashboard
import display

# ─── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/usage-monitor.log", mode="a"),
    ],
)
logger = logging.getLogger("usage-monitor")

# ─── Graceful shutdown ────────────────────────────────────────────

_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info(f"Received signal {signum}, shutting down...")
    _running = False


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ─── Main ─────────────────────────────────────────────────────────

def update_display():
    """Single update cycle: fetch → render → display."""
    logger.info("Starting update cycle...")

    # Fetch usage data
    logger.info("Fetching Claude Code usage...")
    claude_usage = fetch_claude_usage()
    for b in claude_usage:
        logger.info(f"  Claude {b.label}: {b.percent_remaining}%")

    logger.info("Fetching Codex usage...")
    codex_usage = fetch_codex_usage()
    for b in codex_usage:
        logger.info(f"  Codex {b.label}: {b.percent_remaining}%")

    # Render
    logger.info("Rendering dashboard...")
    img = render_dashboard(claude_usage, codex_usage)

    # Save a copy for debugging
    img.save("/tmp/usage-monitor-latest.png")

    # Display
    if display.is_available():
        logger.info("Updating e-ink display...")
        success = display.display_image(img)
        if success:
            logger.info("Display updated successfully")
        else:
            logger.error("Display update failed")
    else:
        logger.info("No display available — image saved to /tmp/usage-monitor-latest.png")

    logger.info("Update cycle complete")


def main():
    """Main loop: update, sleep, repeat."""
    logger.info("=" * 60)
    logger.info("Usage Monitor starting")
    logger.info(f"Refresh interval: {config.REFRESH_INTERVAL_MINUTES} minutes")
    logger.info(f"Display: {config.EPD_MODULE} ({config.EPD_WIDTH}×{config.EPD_HEIGHT})")
    logger.info(f"Timezone: {config.DISPLAY_TIMEZONE}")
    logger.info("=" * 60)

    # Check display
    if display.is_available():
        logger.info("E-ink display detected")
    else:
        logger.warning("E-ink display NOT available — running in headless mode")

    # Initial update
    try:
        update_display()
    except Exception as e:
        logger.error(f"Initial update failed: {e}", exc_info=True)

    # Refresh loop
    interval_seconds = config.REFRESH_INTERVAL_MINUTES * 60

    while _running:
        # Sleep in small increments so we can respond to signals
        for _ in range(interval_seconds):
            if not _running:
                break
            time.sleep(1)

        if _running:
            try:
                update_display()
            except Exception as e:
                logger.error(f"Update failed: {e}", exc_info=True)
                # Continue running — next cycle might work

    logger.info("Usage Monitor stopped")

    # Clear display on shutdown (optional)
    if display.is_available():
        try:
            display.clear_display()
        except Exception:
            pass


if __name__ == "__main__":
    main()
