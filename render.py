"""
Render the usage dashboard to a Pillow Image (800×480, 1-bit).

Designed for e-ink: high contrast black/white, clear typography,
thick progress bars, and generous spacing.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

import config
from fetch_claude import UsageBucket

logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font, falling back to default if missing."""
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        logger.warning(f"Font not found: {path}, using default")
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _get_tz(tz_name: str):
    """Get a timezone object, trying pytz then zoneinfo then fixed offset."""
    try:
        import pytz
        return pytz.timezone(tz_name)
    except (ImportError, Exception):
        pass
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except (ImportError, Exception):
        pass
    from datetime import timezone as tz_mod
    return tz_mod(timedelta(hours=-5))


def _now_local() -> datetime:
    """Get current time in the configured timezone."""
    tz = _get_tz(config.DISPLAY_TIMEZONE)
    return datetime.now(tz)


def _format_reset_time(reset_dt: Optional[datetime], tz_name: str) -> str:
    """Format a reset datetime for display."""
    if reset_dt is None:
        return ""

    tz = _get_tz(tz_name)
    try:
        local_dt = reset_dt.astimezone(tz)
    except Exception:
        local_dt = reset_dt

    now = datetime.now(local_dt.tzinfo) if local_dt.tzinfo else datetime.now()
    delta = local_dt - now

    if local_dt.date() == now.date():
        return f"resets {local_dt.strftime('%-I:%M %p')}"
    if delta.days <= 1:
        return f"resets tomorrow {local_dt.strftime('%-I:%M %p')}"
    return f"resets {local_dt.strftime('%a %-I:%M %p')}"


def _get_bar_label(percent: float) -> str:
    """Get a status label for the percentage."""
    if percent < 0:
        return "N/A"
    if percent <= 10:
        return "CRITICAL"
    if percent <= 25:
        return "LOW"
    return ""


# ─── Logo Rendering ──────────────────────────────────────────────

def _draw_claude_logo(draw: ImageDraw.Draw, x: int, y: int, size: int = 26):
    """
    Draw a simplified Anthropic/Claude logo mark.
    A starburst with 6 rounded rays — the recognizable Claude sparkle.
    """
    cx = x + size // 2
    cy = y + size // 2
    r_outer = size // 2 - 1
    r_inner = size // 5

    for i in range(6):
        angle = math.radians(i * 60 - 90)
        ox = cx + int(r_outer * math.cos(angle))
        oy = cy + int(r_outer * math.sin(angle))
        draw.line([(cx, cy), (ox, oy)], fill=0, width=3)
        # Rounded tip
        tip_r = 3
        draw.ellipse([ox - tip_r, oy - tip_r, ox + tip_r, oy + tip_r], fill=0)

    # Center dot
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=0)


def _draw_codex_logo(draw: ImageDraw.Draw, x: int, y: int, size: int = 26):
    """
    Draw a simplified OpenAI/Codex logo mark.
    A hexagonal ring with inner connecting lines — the OpenAI flower shape.
    """
    cx = x + size // 2
    cy = y + size // 2
    r = size // 2 - 1

    # Outer hexagon
    points = []
    for i in range(6):
        angle = math.radians(i * 60 - 90)
        px = cx + int(r * math.cos(angle))
        py = cy + int(r * math.sin(angle))
        points.append((px, py))

    for i in range(6):
        draw.line([points[i], points[(i + 1) % 6]], fill=0, width=3)

    # Inner connecting lines (flower pattern)
    r_inner = int(r * 0.5)
    inner_points = []
    for i in range(6):
        angle = math.radians(i * 60 - 90)
        px = cx + int(r_inner * math.cos(angle))
        py = cy + int(r_inner * math.sin(angle))
        inner_points.append((px, py))

    for i in range(6):
        draw.line([points[i], inner_points[(i + 2) % 6]], fill=0, width=2)


# ─── Main Renderer ────────────────────────────────────────────────

def render_dashboard(
    claude_usage: list[UsageBucket],
    codex_usage: list[UsageBucket],
) -> Image.Image:
    """
    Render the full dashboard to an 800×480 1-bit image.

    The content block (bars, labels, logos) is horizontally centered
    on the canvas while the title and footer span the full width.
    """
    W = config.EPD_WIDTH
    H = config.EPD_HEIGHT
    PX = config.PADDING_X
    PY = config.PADDING_Y

    # Create white canvas
    img = Image.new("1", (W, H), 1)
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_title = _load_font(config.FONT_BOLD, config.FONT_SIZE_TITLE)
    font_label = _load_font(config.FONT_MEDIUM, config.FONT_SIZE_LABEL)
    font_value = _load_font(config.FONT_BOLD, config.FONT_SIZE_VALUE)
    font_detail = _load_font(config.FONT_REGULAR, config.FONT_SIZE_DETAIL)
    font_footer = _load_font(config.FONT_MONO, config.FONT_SIZE_FOOTER)
    font_section = _load_font(config.FONT_BOLD, 22)

    # ── Calculate centered content X offset ───────────────────
    # Content block = bar (500) + gap (15) + pct area (~80) = ~595
    content_w = config.BAR_WIDTH + 15 + 80
    content_x = (W - content_w) // 2

    y = PY

    # ── Title Bar (centered) ──────────────────────────────────
    title_text = "AI Subscription Usage Monitor"
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((W - title_w) // 2, y), title_text, font=font_title, fill=0)

    y += 34

    # Separator line (full width)
    draw.line([(PX, y), (W - PX, y)], fill=0, width=2)
    y += 10

    # ── Claude Code Section ───────────────────────────────────
    y = _draw_section(
        draw, y, content_x, W,
        section_title="Claude Code",
        buckets=claude_usage,
        font_section=font_section,
        font_value=font_value,
        font_label=font_label,
        font_detail=font_detail,
        draw_logo=_draw_claude_logo,
    )

    y += 4

    # Mid separator — dotted line (full width)
    for x_dot in range(PX, W - PX, 8):
        draw.line([(x_dot, y), (x_dot + 4, y)], fill=0, width=1)
    y += 8

    # ── Codex Section ─────────────────────────────────────────
    y = _draw_section(
        draw, y, content_x, W,
        section_title="Codex",
        buckets=codex_usage,
        font_section=font_section,
        font_value=font_value,
        font_label=font_label,
        font_detail=font_detail,
        draw_logo=_draw_codex_logo,
    )

    # ── Footer (centered) ────────────────────────────────────
    now = _now_local()
    footer_text = f"Last updated: {now.strftime('%b %d, %Y  %-I:%M %p')} EST"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    footer_w = footer_bbox[2] - footer_bbox[0]
    draw.text(
        ((W - footer_w) // 2, H - PY - 18),
        footer_text,
        font=font_footer,
        fill=0,
    )

    # Bottom border line (full width)
    draw.line([(PX, H - PY - 24), (W - PX, H - PY - 24)], fill=0, width=1)

    return img


def _draw_section(
    draw: ImageDraw.Draw,
    y: int,
    cx: int,       # left edge of centered content block
    w: int,        # full canvas width
    section_title: str,
    buckets: list[UsageBucket],
    font_section: ImageFont.FreeTypeFont,
    font_value: ImageFont.FreeTypeFont,
    font_label: ImageFont.FreeTypeFont,
    font_detail: ImageFont.FreeTypeFont,
    draw_logo=None,
) -> int:
    """Draw a section with logo + plain title text, then usage bars."""

    logo_size = 26
    logo_gap = 8

    # ── Section title row: [logo] [title] ──
    if draw_logo:
        draw_logo(draw, cx, y, size=logo_size)

    text_x = cx + logo_size + logo_gap if draw_logo else cx
    title_bbox = draw.textbbox((0, 0), section_title, font=font_section)
    title_h = title_bbox[3] - title_bbox[1]
    text_y = y + (logo_size - title_h) // 2

    draw.text((text_x, text_y), section_title, font=font_section, fill=0)

    y += logo_size + 6

    # ── Usage bars ──
    for bucket in buckets:
        y = _draw_usage_bar(
            draw, y, cx, w,
            bucket=bucket,
            font_value=font_value,
            font_label=font_label,
            font_detail=font_detail,
        )
        y += 2

    return y


def _draw_usage_bar(
    draw: ImageDraw.Draw,
    y: int,
    cx: int,
    w: int,
    bucket: UsageBucket,
    font_value: ImageFont.FreeTypeFont,
    font_label: ImageFont.FreeTypeFont,
    font_detail: ImageFont.FreeTypeFont,
) -> int:
    """Draw a single usage bar with label and percentage. Returns new y."""

    bar_w = config.BAR_WIDTH
    bar_h = config.BAR_HEIGHT
    percent = bucket.percent_remaining

    # ── Row 1: Label + Percentage ──
    draw.text((cx, y), bucket.label, font=font_label, fill=0)

    pct_text = "N/A" if percent < 0 else f"{percent:.0f}%"
    pct_bbox = draw.textbbox((0, 0), pct_text, font=font_value)
    pct_w = pct_bbox[2] - pct_bbox[0]

    bar_x = cx
    pct_x = bar_x + bar_w + 15
    draw.text((pct_x, y - 6), pct_text, font=font_value, fill=0)

    status = _get_bar_label(percent)
    if status:
        draw.text((pct_x + pct_w + 10, y + 2), status, font=font_detail, fill=0)

    y += 22

    # ── Row 2: Progress Bar ──
    bar_y = y
    draw.rounded_rectangle(
        [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
        radius=config.BAR_RADIUS,
        outline=0,
        width=2,
    )

    if percent > 0:
        fill_w = max(4, int(bar_w * min(percent, 100) / 100))
        draw.rounded_rectangle(
            [bar_x + 3, bar_y + 3, bar_x + 3 + fill_w - 6, bar_y + bar_h - 3],
            radius=max(1, config.BAR_RADIUS - 2),
            fill=0,
        )

    y += bar_h + 2

    # ── Row 3: Reset time ──
    reset_text = _format_reset_time(bucket.reset_time, config.DISPLAY_TIMEZONE)
    if reset_text:
        draw.text((bar_x, y), reset_text, font=font_detail, fill=0)
        y += 16
    else:
        y += 2

    return y


# ─── Standalone test ──────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import timedelta, timezone

    now_utc = datetime.now(timezone.utc)

    claude = [
        UsageBucket("Current session", 72.0, now_utc + timedelta(hours=2, minutes=48)),
        UsageBucket("Weekly", 48.0, now_utc + timedelta(days=3, hours=5)),
    ]
    codex = [
        UsageBucket("Current session", 82.0, now_utc + timedelta(hours=3, minutes=13)),
        UsageBucket("Weekly", 36.0, now_utc + timedelta(days=2, hours=1)),
    ]

    img = render_dashboard(claude, codex)
    img.save("test_render.png")
    print("Saved test_render.png")
