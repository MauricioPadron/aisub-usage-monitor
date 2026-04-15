"""
Drive the Waveshare 7.5" V2 e-Paper display.

Wraps the waveshare_epd library for simple init → display → sleep cycles.
Falls back gracefully when not running on a Raspberry Pi (for development).
"""

import logging
from PIL import Image

import config

logger = logging.getLogger(__name__)

# Track whether we're on real hardware
_epd_available = False
_epd_module = None

try:
    # Try the pip-installed package first
    import epaper
    _epd_module = epaper.epaper(config.EPD_MODULE).EPD()
    _epd_available = True
    logger.info(f"Loaded e-paper module via epaper package: {config.EPD_MODULE}")
except Exception:
    try:
        # Try the waveshare_epd library (from their GitHub repo)
        from waveshare_epd import epd7in5_V2 as epd_driver
        _epd_module = epd_driver.EPD()
        _epd_available = True
        logger.info("Loaded e-paper module via waveshare_epd")
    except ImportError:
        logger.warning(
            "Waveshare e-paper library not available. "
            "Display calls will be no-ops. Use preview.py for testing."
        )


def is_available() -> bool:
    """Check if the e-paper display is available."""
    return _epd_available


def display_image(img: Image.Image) -> bool:
    """
    Display an image on the e-ink screen.

    Args:
        img: A PIL Image, should be 800×480, mode "1" (1-bit).

    Returns:
        True if displayed successfully, False otherwise.
    """
    if not _epd_available:
        logger.warning("Display not available, skipping")
        return False

    try:
        epd = _epd_module

        # Initialize
        logger.info("Initializing e-paper display...")
        epd.init()

        # Ensure correct size
        if img.size != (config.EPD_WIDTH, config.EPD_HEIGHT):
            logger.warning(
                f"Image size {img.size} doesn't match display "
                f"({config.EPD_WIDTH}×{config.EPD_HEIGHT}), resizing"
            )
            img = img.resize(
                (config.EPD_WIDTH, config.EPD_HEIGHT),
                Image.LANCZOS,
            )

        # Convert to 1-bit if needed
        if img.mode != "1":
            img = img.convert("1")

        # Display the image
        logger.info("Sending image to display...")
        epd.display(epd.getbuffer(img))

        # Put display to sleep to save power
        logger.info("Display updated, entering sleep mode")
        epd.sleep()

        return True

    except Exception as e:
        logger.error(f"Failed to update display: {e}")
        try:
            _epd_module.sleep()
        except Exception:
            pass
        return False


def clear_display() -> bool:
    """Clear the display to white."""
    if not _epd_available:
        return False

    try:
        epd = _epd_module
        epd.init()
        epd.Clear()
        epd.sleep()
        logger.info("Display cleared")
        return True
    except Exception as e:
        logger.error(f"Failed to clear display: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    if is_available():
        print("Display is available! Clearing...")
        clear_display()
    else:
        print("Display not available (not on Pi or library missing)")
        print("Use preview.py to test rendering")
