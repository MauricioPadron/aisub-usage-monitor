#!/bin/bash
# ─── Usage Monitor Install Script ──────────────────────────────
# Run this on your Raspberry Pi to set up all dependencies.

set -e

echo "╔══════════════════════════════════════════════════╗"
echo "║   Usage Monitor — Raspberry Pi Setup             ║"
echo "╚══════════════════════════════════════════════════╝"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 1. System packages ──────────────────────────────────────
echo "→ Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-pil \
    python3-numpy \
    libopenjp2-7 \
    libtiff6 \
    libatlas-base-dev \
    fonts-dejavu-core \
    git

# ── 2. Enable SPI (if not already) ──────────────────────────
echo "→ Checking SPI..."
if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=spi=on" /boot/config.txt 2>/dev/null; then
    echo "  ⚠ SPI may not be enabled."
    echo "  Run: sudo raspi-config → Interface Options → SPI → Enable"
    echo "  Then reboot."
fi

# ── 3. Python virtual environment ───────────────────────────
echo "→ Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv --system-site-packages venv
fi
source venv/bin/activate

# ── 4. Python packages ──────────────────────────────────────
echo "→ Installing Python packages..."
pip install --quiet --upgrade pip
pip install --quiet \
    Pillow \
    requests \
    pytz \
    RPi.GPIO \
    spidev \
    waveshare-epaper

# ── 5. Waveshare library (from GitHub, as backup) ───────────
echo "→ Ensuring Waveshare e-Paper library is available..."
if ! python3 -c "import waveshare_epd" 2>/dev/null && \
   ! python3 -c "import epaper" 2>/dev/null; then
    echo "  Cloning Waveshare e-Paper repo..."
    if [ ! -d "e-Paper" ]; then
        git clone --depth 1 https://github.com/waveshare/e-Paper.git
    fi
    # Symlink the library
    WAVESHARE_LIB="e-Paper/RaspberryPi_JetsonNano/python/lib"
    if [ -d "$WAVESHARE_LIB" ]; then
        ln -sf "$(realpath $WAVESHARE_LIB/waveshare_epd)" waveshare_epd
        echo "  Linked waveshare_epd library"
    fi
fi

# ── 6. Download fonts ───────────────────────────────────────
echo "→ Downloading fonts..."
FONT_DIR="$SCRIPT_DIR/fonts"
mkdir -p "$FONT_DIR"

# IBM Plex Sans — clean, technical, great for dashboards
PLEX_VERSION="v6.4.2"
PLEX_BASE="https://github.com/IBM/plex/releases/download/%40ibm%2Fplex-sans%40${PLEX_VERSION}"

download_font() {
    local url="$1"
    local dest="$2"
    if [ ! -f "$dest" ]; then
        echo "  Downloading $(basename $dest)..."
        wget -q -O "$dest" "$url" 2>/dev/null || \
        curl -sL -o "$dest" "$url" 2>/dev/null || \
        echo "  ⚠ Failed to download $(basename $dest)"
    fi
}

# Try Google Fonts CDN (more reliable)
GFONTS="https://github.com/google/fonts/raw/main/ofl"

download_font "${GFONTS}/ibmplexsans/IBMPlexSans-Bold.ttf" "$FONT_DIR/IBMPlexSans-Bold.ttf"
download_font "${GFONTS}/ibmplexsans/IBMPlexSans-Medium.ttf" "$FONT_DIR/IBMPlexSans-Medium.ttf"
download_font "${GFONTS}/ibmplexsans/IBMPlexSans-Regular.ttf" "$FONT_DIR/IBMPlexSans-Regular.ttf"
download_font "${GFONTS}/ibmplexmono/IBMPlexMono-Medium.ttf" "$FONT_DIR/IBMPlexMono-Medium.ttf"

# Verify fonts exist, fall back to system fonts
for font_file in IBMPlexSans-Bold.ttf IBMPlexSans-Medium.ttf IBMPlexSans-Regular.ttf IBMPlexMono-Medium.ttf; do
    if [ ! -f "$FONT_DIR/$font_file" ] || [ ! -s "$FONT_DIR/$font_file" ]; then
        echo "  ⚠ $font_file missing, will fall back to DejaVu Sans"
    fi
done

# ── 7. Create systemd service ───────────────────────────────
echo "→ Generating systemd service file..."
cat > "$SCRIPT_DIR/usage-monitor.service" << EOF
[Unit]
Description=E-Ink Usage Monitor for Claude Code & Codex
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/main.py
Restart=always
RestartSec=60
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo
echo "╔══════════════════════════════════════════════════╗"
echo "║   Setup complete!                                ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║   Next steps:                                    ║"
echo "║   1. Edit config.py with your tokens             ║"
echo "║   2. Test: source venv/bin/activate               ║"
echo "║           python3 preview.py                     ║"
echo "║   3. Run: python3 main.py                        ║"
echo "║   4. Auto-start:                                 ║"
echo "║      sudo cp usage-monitor.service               ║"
echo "║           /etc/systemd/system/                   ║"
echo "║      sudo systemctl daemon-reload                ║"
echo "║      sudo systemctl enable usage-monitor         ║"
echo "║      sudo systemctl start usage-monitor          ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
