"""
Fetch Claude Code usage limits.

Three strategies in priority order:
  1. CLI — run `claude /usage` and parse the output (requires Claude Code
     installed and authenticated on this machine; zero token management)
  2. OAuth API with auto-refresh — uses a full token JSON blob (access +
     refresh token) and silently refreshes when the access token expires
  3. Static OAuth token — a bare access token string (will stop working
     once the token expires)

The recommended setup for a headless Pi:
  • On your Mac/PC run `claude setup-token`
  • Copy the output and set it as CLAUDE_CODE_OAUTH_TOKEN in the Pi's
    environment (~/.bashrc) or paste the full JSON into config.py
  • Install Claude Code on the Pi:
      curl -fsSL https://claude.ai/install.sh | bash
      echo 'export CLAUDE_CODE_OAUTH_TOKEN=<token>' >> ~/.bashrc
  • This script will then be able to run `claude /usage` directly
"""

import json
import os
import re
import subprocess
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

try:
    import requests
except ImportError:
    requests = None

import config

logger = logging.getLogger(__name__)


@dataclass
class UsageBucket:
    """A single usage limit bucket (e.g. 5-hour or weekly)."""
    label: str              # e.g. "Current session" or "Weekly"
    percent_remaining: float  # 0.0 to 100.0, or -1 if unavailable
    reset_time: Optional[datetime] = None
    raw: Optional[dict] = None


# ─── Token file for persisting refreshed credentials ─────────

_TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".claude_token.json"
)


def _load_token_data() -> Optional[dict]:
    """
    Load the full token JSON from, in order:
      1. The persisted token file (.claude_token.json)
      2. config.CLAUDE_OAUTH_TOKEN (if it's a JSON string)
      3. config.CLAUDE_CREDENTIALS_FILE
    Returns a dict with accessToken, refreshToken, expiresAt or None.
    """
    # 1. Persisted token file (has the freshest refreshed token)
    if os.path.isfile(_TOKEN_FILE):
        try:
            with open(_TOKEN_FILE, "r") as f:
                data = json.load(f)
            if "accessToken" in data:
                return data
        except (json.JSONDecodeError, IOError):
            pass

    # 2. config.CLAUDE_OAUTH_TOKEN — could be bare token or full JSON
    token_val = config.CLAUDE_OAUTH_TOKEN
    if token_val:
        # Try parsing as JSON first
        if token_val.strip().startswith("{"):
            try:
                data = json.loads(token_val)
                # Handle nested format: {"claudeAiOauth": {...}}
                if "claudeAiOauth" in data:
                    data = data["claudeAiOauth"]
                if "accessToken" in data:
                    _save_token_data(data)
                    return data
            except json.JSONDecodeError:
                pass
        # Bare token string
        return {"accessToken": token_val}

    # 3. Credentials file
    if config.CLAUDE_CREDENTIALS_FILE and os.path.isfile(config.CLAUDE_CREDENTIALS_FILE):
        try:
            with open(config.CLAUDE_CREDENTIALS_FILE, "r") as f:
                data = json.load(f)
            if "claudeAiOauth" in data:
                data = data["claudeAiOauth"]
            if "accessToken" in data:
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read credentials file: {e}")

    return None


def _save_token_data(data: dict):
    """Persist token data so refreshed tokens survive restarts."""
    try:
        with open(_TOKEN_FILE, "w") as f:
            json.dump(data, f)
        os.chmod(_TOKEN_FILE, 0o600)
    except IOError as e:
        logger.warning(f"Could not save token file: {e}")


# ─── Public API ───────────────────────────────────────────────

def fetch_claude_usage() -> list[UsageBucket]:
    """
    Fetch Claude Code usage data.
    Tries CLI first (most reliable, no token hassle), then API.
    """
    # Strategy 1: CLI
    result = _fetch_via_cli()
    if result:
        return result

    # Strategy 2: OAuth API with auto-refresh
    token_data = _load_token_data()
    if token_data:
        result = _fetch_via_api(token_data)
        if result:
            return result

    logger.warning("Could not fetch Claude Code usage from any source")
    return [
        UsageBucket(label="Current session", percent_remaining=-1),
        UsageBucket(label="Weekly", percent_remaining=-1),
    ]


# ─── Strategy 1: CLI ─────────────────────────────────────────

def _fetch_via_cli() -> Optional[list[UsageBucket]]:
    """
    Run `claude /usage` and parse the output.
    This is the preferred method — Claude Code handles all auth internally.
    """
    # Try different invocation styles
    commands = [
        ["claude", "-p", "/usage", "--output-format", "text"],
        ["claude", "-p", "/usage"],
    ]

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            if "%" in output:
                parsed = _parse_cli_output(output)
                if parsed:
                    logger.info("Successfully fetched Claude usage via CLI")
                    return parsed
        except FileNotFoundError:
            logger.debug("Claude Code CLI not found")
            return None
        except subprocess.TimeoutExpired:
            logger.error("Claude Code CLI timed out")
            continue
        except Exception as e:
            logger.error(f"Failed to run Claude CLI: {e}")
            continue

    return None


def _parse_cli_output(output: str) -> Optional[list[UsageBucket]]:
    """
    Parse the text output of `claude /usage`.

    Looks for patterns like:
      5h limit: [███████████████████░░] 82% left (resets 15:18)
      Weekly limit: [███████░░░░░░░░░░░░░░] 36% left (resets 03:08 on 22 Mar)
    Or similar format with percentage patterns.
    """
    buckets = []
    lines = output.strip().split("\n")

    for line in lines:
        line_lower = line.lower().strip()

        # Look for percentage patterns
        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:left|remaining)", line)
        if not pct_match:
            continue

        percent = float(pct_match.group(1))

        # Determine which bucket
        if "5h" in line_lower or "five" in line_lower or "session" in line_lower:
            label = "Current session"
        elif "week" in line_lower or "7" in line_lower or "seven" in line_lower:
            label = "Weekly"
        else:
            label = "limit"

        # Try to find reset time
        reset_time = None
        # Could parse time strings here in the future

        buckets.append(UsageBucket(
            label=label,
            percent_remaining=percent,
            reset_time=reset_time,
        ))

    return buckets if buckets else None


# ─── Strategy 2: OAuth API ───────────────────────────────────

def _fetch_via_api(token_data: dict) -> Optional[list[UsageBucket]]:
    """Fetch usage via the Anthropic OAuth usage endpoint, with auto-refresh."""
    if requests is None:
        logger.warning("requests library not installed, skipping API fetch")
        return None

    access_token = token_data.get("accessToken", "")
    if not access_token:
        return None

    # Check if token looks expired
    expires_at = token_data.get("expiresAt")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(exp_dt.tzinfo) >= exp_dt:
                logger.info("Access token expired, attempting refresh...")
                refreshed = _refresh_token(token_data)
                if refreshed:
                    token_data = refreshed
                    access_token = token_data["accessToken"]
                else:
                    logger.warning("Token refresh failed")
                    # Try anyway — server might still accept it
        except (ValueError, TypeError):
            pass

    # Make the API call
    result = _call_usage_api(access_token)
    if result is not None:
        return result

    # Got a failure — might be expired. Try refresh if we haven't already.
    if token_data.get("refreshToken"):
        logger.info("API call failed, attempting token refresh...")
        refreshed = _refresh_token(token_data)
        if refreshed:
            result = _call_usage_api(refreshed["accessToken"])
            if result is not None:
                return result

    return None


def _call_usage_api(access_token: str) -> Optional[list[UsageBucket]]:
    """Make the actual API call to fetch usage data."""
    try:
        resp = requests.get(
            config.CLAUDE_USAGE_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "usage-monitor/1.0",
            },
            timeout=15,
        )

        if resp.status_code == 401:
            logger.debug("API returned 401 — token may be expired")
            return None

        resp.raise_for_status()
        data = resp.json()

        buckets = []

        if "five_hour" in data and data["five_hour"]:
            buckets.append(_parse_api_bucket(data["five_hour"], "Current session"))
        else:
            buckets.append(UsageBucket(label="Current session", percent_remaining=-1))

        if "seven_day" in data and data["seven_day"]:
            buckets.append(_parse_api_bucket(data["seven_day"], "Weekly"))
        else:
            buckets.append(UsageBucket(label="Weekly", percent_remaining=-1))

        return buckets

    except Exception as e:
        logger.error(f"Usage API call failed: {e}")
        return None


def _refresh_token(token_data: dict) -> Optional[dict]:
    """
    Use the refresh token to get a new access token.
    Persists the new tokens to disk so they survive restarts.
    """
    refresh_token = token_data.get("refreshToken")
    if not refresh_token:
        logger.debug("No refresh token available")
        return None

    try:
        resp = requests.post(
            "https://console.anthropic.com/v1/oauth/token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "Content-Type": "application/json",
                "User-Agent": "usage-monitor/1.0",
            },
            timeout=15,
        )

        if resp.status_code != 200:
            logger.error(f"Token refresh returned {resp.status_code}")
            return None

        new_data = resp.json()

        # Build updated token data
        updated = {
            "accessToken": new_data.get("access_token", new_data.get("accessToken", "")),
            "refreshToken": new_data.get("refresh_token", new_data.get("refreshToken", refresh_token)),
            "expiresAt": new_data.get("expires_at", new_data.get("expiresAt", "")),
        }

        if updated["accessToken"]:
            _save_token_data(updated)
            logger.info("Token refreshed and saved successfully")
            return updated

        return None

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return None


def _parse_api_bucket(bucket_data: dict, label: str) -> UsageBucket:
    """Parse a usage bucket from API response."""
    remaining = 100.0
    reset_time = None

    if "percentRemaining" in bucket_data:
        remaining = float(bucket_data["percentRemaining"])
    elif "percent_remaining" in bucket_data:
        remaining = float(bucket_data["percent_remaining"])
    elif "used" in bucket_data and "limit" in bucket_data:
        used = float(bucket_data["used"])
        limit = float(bucket_data["limit"])
        if limit > 0:
            remaining = max(0, (1 - used / limit) * 100)

    for key in ("resetsAt", "resets_at", "reset_time", "resetTime"):
        if key in bucket_data and bucket_data[key]:
            try:
                reset_time = datetime.fromisoformat(
                    str(bucket_data[key]).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
            break

    return UsageBucket(
        label=label,
        percent_remaining=round(remaining, 1),
        reset_time=reset_time,
        raw=bucket_data,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    usage = fetch_claude_usage()
    for b in usage:
        print(f"{b.label}: {b.percent_remaining}% remaining | resets: {b.reset_time}")
