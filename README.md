# E-Ink Usage Monitor for Claude Code & Codex

A Raspberry Pi + Waveshare 7.5" e-ink display dashboard that shows your
Claude Code and OpenAI Codex usage limits at a glance, refreshing every 15 minutes.

```
┌──────────────────────────────────────────────────────────────────┐
│  800 × 480 e-ink  ·  15-min refresh  ·  EST timezone            │
│                                                                  │
│  CLAUDE CODE          ▓▓▓▓▓▓▓▓▓▓▓▓░░░░  72%                    │
│  5h session           resets 3:18 PM                             │
│                                                                  │
│  CLAUDE CODE          ▓▓▓▓▓▓▓▓░░░░░░░░  48%                    │
│  7-day weekly         resets Mon 9 AM                            │
│                                                                  │
│  CODEX                ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░  82%                    │
│  5h session           resets 5:43 PM                             │
│                                                                  │
│  CODEX                ▓▓▓▓░░░░░░░░░░░░  36%                     │
│  Weekly               resets Wed 3:08 AM                         │
│                                                                  │
│  Last updated: Apr 14, 2026 · 2:30 PM EST                       │
└──────────────────────────────────────────────────────────────────┘
```

## Architecture

```
usage-monitor/
├── config.py          # All configuration (tokens, display, timezone)
├── fetch_claude.py    # Fetch Claude Code usage via API
├── fetch_codex.py     # Fetch Codex usage via CLI or API
├── render.py          # Render the dashboard image with Pillow
├── display.py         # Drive the Waveshare e-ink display
├── main.py            # Orchestrator: fetch → render → display, loop
├── preview.py         # Desktop preview: renders to PNG (no display needed)
├── install.sh         # One-shot setup script for the Pi
├── usage-monitor.service  # systemd unit file for auto-start
└── fonts/             # Font files (downloaded by install.sh)
```

## Prerequisites

- Raspberry Pi (any model with 40-pin GPIO)
- Waveshare 7.5" V2 e-Paper HAT (800×480, black/white)
- Raspberry Pi OS (Bookworm or later)
- Python 3.9+
- SPI enabled (`sudo raspi-config` → Interface Options → SPI → Enable)

## Quick Start

### 1. Clone / copy this project to your Pi

```bash
scp -r usage-monitor/ pi@<your-pi-ip>:~/
```

### 2. Run the installer

```bash
cd ~/usage-monitor
chmod +x install.sh
./install.sh
```

This installs system dependencies, Python packages, and downloads fonts.

### 3. Configure your tokens

Edit `config.py` and fill in your credentials:

- **Claude Code**: You need your OAuth token. See the "Getting Your Claude
  Code Token" section below.
- **Codex**: You need your ChatGPT session token or API key.

### 4. Test with desktop preview (no display needed!)

```bash
python3 preview.py
```

This generates `preview.png` — open it to see exactly what the e-ink
display will show. Use this to iterate on the layout before your
display arrives.

### 5. Run on the Pi with display

```bash
python3 main.py
```

### 6. Enable auto-start on boot

```bash
sudo cp usage-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable usage-monitor
sudo systemctl start usage-monitor
```

## Getting Your Claude Code OAuth Token

Claude Code stores its OAuth token in your system keychain. On macOS:

```bash
security find-generic-password -s "claude-code-credentials" -w
```

On Linux, check:
```bash
# If using secret-tool (GNOME Keyring)
secret-tool lookup service claude-code-credentials

# Or check the credential file directly
cat ~/.claude/credentials.json
```

Copy the token value and paste it into `config.py` as `CLAUDE_OAUTH_TOKEN`.

**Note:** OAuth tokens expire periodically. You may need to refresh this
token by running `claude` on the machine where you're authenticated,
then re-extracting it.

## Getting Your Codex Session Info

Codex CLI uses your ChatGPT authentication. The simplest approach is to
run `codex` on your Pi (or the machine with the token), then the
fetch script will call `codex /status` and parse the output.

Alternatively, if you have an OpenAI API key, set it in `config.py`.

## Customization

- **Refresh interval**: Change `REFRESH_INTERVAL_MINUTES` in `config.py`
- **Timezone**: Change `DISPLAY_TIMEZONE` in `config.py` (default: US/Eastern)
- **Display model**: If you have a different Waveshare model, change
  `EPD_MODULE` in `config.py`
- **Layout**: Edit `render.py` to customize fonts, sizes, positions

## Troubleshooting

- **Blank display**: Make sure SPI is enabled and the HAT is seated properly
- **Import errors**: Run `install.sh` again or `pip install -r requirements.txt`
- **Token expired**: Re-extract your OAuth token (see above)
- **Preview looks wrong**: Adjust font sizes in `render.py` — the e-ink
  display is 800×480 at ~111 DPI
