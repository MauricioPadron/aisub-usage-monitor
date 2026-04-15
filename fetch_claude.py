"""
Fetch Claude Code usage limits via the Anthropic OAuth usage API.

Returns a dict with session (5h) and weekly (7d) usage data including
percentage remaining and reset times.
"""

import json
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
    """A single usage limit bucket (e.g. 5-hour or 7-day)."""
    label: str          # e.g. "5h session" or "7-day weekly"
    percent_remaining: float  # 0.0 to 100.0
    reset_time: Optional[datetime] = None
    raw: Optional[dict] = None


def fetch_claude_usage() -> list[UsageBucket]:
    """
    Fetch Claude Code usage data.
    Tries the OAuth API first, falls back to CLI parsing.
    """
    # Try API approach first
    token = _get_token()
    if token:
        result = _fetch_via_api(token)
        if result:
            return result

    # Fall back to CLI
    result = _fetch_via_cli()
    if result:
        return result

    logger.warning("Could not fetch Claude Code usage from any source")
    return [
        UsageBucket(label="Current session", percent_remaining=-1),
        UsageBucket(label="Weekly", percent_remaining=-1),
    ]


def _get_token() -> Optional[str]:
    """Get the OAuth token from config or credentials file."""
    if config.CLAUDE_OAUTH_TOKEN:
        return config.CLAUDE_OAUTH_TOKEN

    if config.CLAUDE_CREDENTIALS_FILE:
        try:
            with open(config.CLAUDE_CREDENTIALS_FILE, "r") as f:
                creds = json.load(f)
                # Try common key names
                for key in ("token", "access_token", "oauth_token"):
                    if key in creds:
                        return creds[key]
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to read credentials file: {e}")

    return None


def _fetch_via_api(token: str) -> Optional[list[UsageBucket]]:
    """Fetch usage via the Anthropic OAuth usage endpoint."""
    if requests is None:
        logger.warning("requests library not installed, skipping API fetch")
        return None

    try:
        resp = requests.get(
            config.CLAUDE_USAGE_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "usage-monitor/1.0",
            },
            timeout=15,
        )

        if resp.status_code == 401:
            logger.error("Claude OAuth token expired or invalid")
            return None

        resp.raise_for_status()
        data = resp.json()

        buckets = []

        # Parse 5-hour bucket
        if "five_hour" in data and data["five_hour"]:
            fh = data["five_hour"]
            buckets.append(_parse_bucket(fh, "Current session"))
        else:
            buckets.append(UsageBucket(label="Current session", percent_remaining=-1))

        # Parse 7-day bucket
        if "seven_day" in data and data["seven_day"]:
            sd = data["seven_day"]
            buckets.append(_parse_bucket(sd, "Weekly"))
        else:
            buckets.append(UsageBucket(label="Weekly", percent_remaining=-1))

        return buckets

    except Exception as e:
        logger.error(f"Failed to fetch Claude usage via API: {e}")
        return None


def _parse_bucket(bucket_data: dict, label: str) -> UsageBucket:
    """Parse a usage bucket from API response."""
    remaining = 100.0
    reset_time = None

    # The API returns various formats; handle common ones
    if "percentRemaining" in bucket_data:
        remaining = float(bucket_data["percentRemaining"])
    elif "percent_remaining" in bucket_data:
        remaining = float(bucket_data["percent_remaining"])
    elif "used" in bucket_data and "limit" in bucket_data:
        used = float(bucket_data["used"])
        limit = float(bucket_data["limit"])
        if limit > 0:
            remaining = max(0, (1 - used / limit) * 100)

    # Parse reset time
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


def _fetch_via_cli() -> Optional[list[UsageBucket]]:
    """
    Fall back to running `claude /usage` and parsing the output.
    This requires `claude` to be installed and authenticated on this machine.
    """
    try:
        result = subprocess.run(
            ["claude", "/usage"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        return _parse_cli_output(output)
    except FileNotFoundError:
        logger.info("Claude Code CLI not found on this machine")
        return None
    except subprocess.TimeoutExpired:
        logger.error("Claude Code CLI timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to run Claude CLI: {e}")
        return None


def _parse_cli_output(output: str) -> Optional[list[UsageBucket]]:
    """
    Parse the text output of `claude /usage`.

    Expected output contains lines like:
      5h limit: [███████████████████░░] 82% left (resets 15:18)
      Weekly limit: [███████░░░░░░░░░░░░░░] 36% left (resets 03:08 on 22 Mar)

    Or similar format. We look for percentage patterns.
    """
    import re

    buckets = []
    lines = output.strip().split("\n")

    for line in lines:
        line_lower = line.lower().strip()

        # Look for percentage patterns like "82% left" or "82% remaining"
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
        reset_match = re.search(
            r"resets?\s+(\d{1,2}:\d{2}(?:\s*(?:AM|PM))?(?:\s+on\s+\d+\s+\w+)?)",
            line, re.IGNORECASE,
        )
        if reset_match:
            # Store as string for now; render.py will handle display
            pass

        buckets.append(UsageBucket(
            label=label,
            percent_remaining=percent,
            reset_time=reset_time,
        ))

    return buckets if buckets else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    usage = fetch_claude_usage()
    for b in usage:
        print(f"{b.label}: {b.percent_remaining}% remaining | resets: {b.reset_time}")
