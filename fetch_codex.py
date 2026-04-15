"""
Fetch OpenAI Codex usage limits.

The `codex /status` interactive command doesn't reliably show usage
percentages in its output. Instead we:

  1. Try the Codex usage web API (chatgpt.com/codex/settings/usage)
  2. Fall back to scraping usage from the Codex CLI's internal
     rate-limit polling endpoint (if we can find a session token)
  3. Fall back to parsing `codex /status` output as a last resort

For now, the most reliable approach is to have the user check their
usage at https://chatgpt.com/codex/settings/usage and we can parse
that, or use the OpenAI API if they have a key.

If neither API approach works, this module returns "unavailable"
and the display will show N/A for Codex limits.
"""

import json
import os
import re
import subprocess
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

import config
from fetch_claude import UsageBucket  # reuse the same dataclass

logger = logging.getLogger(__name__)


def fetch_codex_usage() -> list[UsageBucket]:
    """
    Fetch Codex usage data.
    Tries multiple strategies.
    """
    # Strategy 1: CLI /status (parse whatever we can get)
    if config.CODEX_USE_CLI:
        result = _fetch_via_cli()
        if result:
            return result

    # Strategy 2: Direct API (if we have credentials)
    if config.OPENAI_API_KEY or config.CODEX_SESSION_TOKEN:
        result = _fetch_via_api()
        if result:
            return result

    # Strategy 3: Try reading from Codex's local config/cache
    result = _fetch_from_local_cache()
    if result:
        return result

    logger.warning("Could not fetch Codex usage from any source")
    return [
        UsageBucket(label="Current session", percent_remaining=-1),
        UsageBucket(label="Weekly", percent_remaining=-1),
    ]


# --- Strategy 1: CLI ---

def _fetch_via_cli() -> Optional[list[UsageBucket]]:
    """
    Try to get usage info from the Codex CLI.
    The interactive /status doesn't show percentages reliably,
    but we try various approaches.
    """
    # Try the non-interactive approach
    for cmd in [
        ["codex", "exec", "/status"],
        ["codex", "--print", "/status"],
    ]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                env=_get_codex_env(),
            )
            output = result.stdout + result.stderr
            if "%" in output:
                parsed = _parse_codex_output(output)
                if parsed:
                    return parsed
        except FileNotFoundError:
            break  # codex not installed
        except subprocess.TimeoutExpired:
            continue
        except Exception as e:
            logger.debug(f"Codex CLI attempt failed: {e}")
            continue

    return None


def _get_codex_env():
    env = os.environ.copy()
    if config.OPENAI_API_KEY:
        env["OPENAI_API_KEY"] = config.OPENAI_API_KEY
    return env


def _parse_codex_output(output: str) -> Optional[list[UsageBucket]]:
    """Parse Codex output for usage percentages."""
    buckets = []
    joined = " ".join(output.strip().split("\n"))

    patterns = [
        (r"5h\s+limit.*?(\d+(?:\.\d+)?)\s*%\s*left", "Current session"),
        (r"weekly\s+limit.*?(\d+(?:\.\d+)?)\s*%\s*left", "Weekly"),
        (r"(\d+(?:\.\d+)?)\s*%\s*(?:left|remaining)", None),
    ]

    for pattern, label in patterns:
        matches = re.finditer(pattern, joined, re.IGNORECASE)
        for match in matches:
            percent = float(match.group(1))
            actual_label = label
            if actual_label is None:
                context = joined[max(0, match.start() - 50):match.start()].lower()
                if "5h" in context or "session" in context:
                    actual_label = "Current session"
                elif "week" in context:
                    actual_label = "Weekly"
                else:
                    actual_label = "limit"

            if any(b.label == actual_label for b in buckets):
                continue

            buckets.append(UsageBucket(
                label=actual_label,
                percent_remaining=percent,
            ))

    return buckets if buckets else None


# --- Strategy 2: API ---

def _fetch_via_api() -> Optional[list[UsageBucket]]:
    """Try to fetch usage from OpenAI's API."""
    if requests is None:
        return None

    # There's no official public endpoint for Codex usage data.
    # The web dashboard at chatgpt.com/codex/settings/usage requires
    # a browser session. If the user has an API key, we can at least
    # check rate limit headers, but that doesn't give us plan usage.
    #
    # For now, return None and rely on CLI or local cache.
    return None


# --- Strategy 3: Local cache ---

def _fetch_from_local_cache() -> Optional[list[UsageBucket]]:
    """
    Check if Codex stores usage/rate-limit data locally.
    Codex CLI may cache rate limit info in its config directory.
    """
    cache_paths = [
        Path.home() / ".codex" / "usage.json",
        Path.home() / ".codex" / "rate-limits.json",
        Path.home() / ".config" / "codex" / "usage.json",
    ]

    for path in cache_paths:
        if path.is_file():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                # Try to parse whatever format we find
                buckets = []
                if "five_hour" in data or "5h" in str(data):
                    # Similar format to Claude
                    pass
                if buckets:
                    return buckets
            except (json.JSONDecodeError, IOError):
                continue

    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    usage = fetch_codex_usage()
    for b in usage:
        print(f"{b.label}: {b.percent_remaining}% remaining | resets: {b.reset_time}")
