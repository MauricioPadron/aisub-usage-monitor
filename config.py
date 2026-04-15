"""
Configuration for the e-ink usage monitor.
Fill in your credentials and adjust settings as needed.
"""

# --- Display Settings ---
EPD_WIDTH = 800
EPD_HEIGHT = 480
EPD_MODULE = "epd7in5_V2"  # Waveshare 7.5" V2 (800x480 B/W)

# --- Refresh ---
REFRESH_INTERVAL_MINUTES = 15

# --- Timezone ---
DISPLAY_TIMEZONE = "US/Eastern"

# --- Claude Code Credentials ---
# RECOMMENDED: Install Claude Code on the Pi and authenticate it.
# Then the monitor just runs `claude /usage` -- no tokens needed here.
#
#   On your Mac:  claude setup-token
#   On the Pi:    curl -fsSL https://claude.ai/install.sh | bash
#                 echo 'export CLAUDE_CODE_OAUTH_TOKEN=<token>' >> ~/.bashrc
#
# ALTERNATIVE: Paste the full JSON blob from your Mac's Keychain:
#   security find-generic-password -s "Claude Code-credentials" -w
# This includes a refresh token so the monitor can auto-renew.
#
# Format: full JSON string (with refresh) OR bare access token string
# Full JSON:  '{"accessToken":"sk-ant-oat01-...","refreshToken":"ant-rt01-...","expiresAt":"..."}'
# Bare token: "sk-ant-oat01-..."
CLAUDE_OAUTH_TOKEN = ""

# Path to credentials JSON file (alternative to pasting above)
# e.g. "/home/pi/.claude/.credentials.json"
CLAUDE_CREDENTIALS_FILE = ""

# Claude Code API endpoint for usage data
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# --- Codex Credentials ---
# Option A: Use the CLI (runs `codex /status` and parses output)
CODEX_USE_CLI = True

# Option B: OpenAI API key (for direct API access if available)
OPENAI_API_KEY = ""

# Option C: ChatGPT session cookie (advanced)
CODEX_SESSION_TOKEN = ""

# --- Fonts ---
# These are downloaded by install.sh into the fonts/ directory
import os
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

FONT_BOLD = os.path.join(_FONT_DIR, "IBMPlexSans-Bold.ttf")
FONT_MEDIUM = os.path.join(_FONT_DIR, "IBMPlexSans-Medium.ttf")
FONT_REGULAR = os.path.join(_FONT_DIR, "IBMPlexSans-Regular.ttf")
FONT_MONO = os.path.join(_FONT_DIR, "IBMPlexMono-Medium.ttf")

# Font sizes
FONT_SIZE_TITLE = 28
FONT_SIZE_LABEL = 20
FONT_SIZE_VALUE = 36
FONT_SIZE_DETAIL = 16
FONT_SIZE_FOOTER = 14

# --- Layout ---
# Padding from display edges
PADDING_X = 30
PADDING_Y = 20

# Bar dimensions
BAR_WIDTH = 500
BAR_HEIGHT = 24
BAR_RADIUS = 6
