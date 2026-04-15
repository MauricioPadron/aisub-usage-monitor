"""
Fetch OpenAI Codex usage limits.

Primary method: parse `codex /status` CLI output.
Fallback: Codex usage dashboard API (if session token provided).
"""

import re
import subprocess
import logging
from datetime import datetime
from typing import Optional

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
    Tries CLI first (most reliable), then API fallback.
    """
    if config.CODEX_USE_CLI:
        result = _fetch_via_cli()
        if result:
            return result

    # API fallback (if we have credentials)
    if config.CODEX_SESSION_TOKEN or config.OPENAI_API_KEY:
        result = _fetch_via_api()
        if result:
            return result

    logger.warning("Could not fetch Codex usage from any source")
    return [
        UsageBucket(label="Current session", percent_remaining=-1),
        UsageBucket(label="Weekly", percent_remaining=-1),
    ]


def _fetch_via_cli() -> Optional[list[UsageBucket]]:
    """
    Run `codex /status` and parse the output.

    Expected output looks something like:
    ╭───────────────────────────────────────────────╮
    │ >_ OpenAI Codex (v0.116.0)                    │
    │                                               │
    │ Model: gpt-5.4 (reasoning high)               │
    │ Account: user@example.com (Plus)               │
    │                                               │
    │ 5h limit: [███████████░░░░░░] 82% left         │
    │   (resets 15:18)                               │
    │ Weekly limit: [███░░░░░░░░░░] 36% left         │
    │   (resets 03:08 on 22 Mar)                     │
    ╰───────────────────────────────────────────────╯
    """
    # Try running codex with /status
    for cmd in [
        ["codex", "--print", "/status"],
        ["codex", "-p", "/status"],
    ]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=_get_codex_env(),
            )
            output = result.stdout + result.stderr
            if "%" in output:
                parsed = _parse_codex_output(output)
                if parsed:
                    return parsed
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            logger.error("Codex CLI timed out")
            continue
        except Exception as e:
            logger.error(f"Failed to run Codex CLI: {e}")
            continue

    # Also try a direct interactive approach with echo
    try:
        proc = subprocess.run(
            ["bash", "-c", "echo '/status' | codex 2>&1 | head -30"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_get_codex_env(),
        )
        output = proc.stdout
        if "%" in output:
            parsed = _parse_codex_output(output)
            if parsed:
                return parsed
    except Exception as e:
        logger.debug(f"Interactive codex approach failed: {e}")

    logger.info("Codex CLI not available or no output")
    return None


def _get_codex_env():
    """Build environment for codex subprocess."""
    import os
    env = os.environ.copy()
    if config.OPENAI_API_KEY:
        env["OPENAI_API_KEY"] = config.OPENAI_API_KEY
    return env


def _parse_codex_output(output: str) -> Optional[list[UsageBucket]]:
    """
    Parse Codex /status output for usage percentages and reset times.
    Handles various output formats.
    """
    buckets = []
    lines = output.strip().split("\n")

    # Join consecutive lines to handle wrapped reset times
    joined = " ".join(line.strip() for line in lines)

    # Pattern 1: "5h limit: ... XX% left (resets HH:MM)"
    # Pattern 2: "Weekly limit: ... XX% left (resets HH:MM on DD Mon)"
    patterns = [
        (r"5h\s+limit.*?(\d+(?:\.\d+)?)\s*%\s*left.*?resets?\s+([\d:]+(?:\s*(?:AM|PM))?)", "Current session"),
        (r"weekly\s+limit.*?(\d+(?:\.\d+)?)\s*%\s*left.*?resets?\s+([\d:]+(?:\s*(?:AM|PM))?\s*(?:on\s+\d+\s+\w+)?)", "Weekly"),
        # Fallback: any "XX% left" patterns
        (r"(\d+(?:\.\d+)?)\s*%\s*(?:left|remaining)", None),
    ]

    for pattern, label in patterns:
        matches = re.finditer(pattern, joined, re.IGNORECASE)
        for match in matches:
            percent = float(match.group(1))
            reset_str = match.group(2) if match.lastindex >= 2 else None

            # Auto-detect label if not preset
            actual_label = label
            if actual_label is None:
                context = joined[max(0, match.start() - 50):match.start()].lower()
                if "5h" in context or "session" in context:
                    actual_label = "Current session"
                elif "week" in context:
                    actual_label = "Weekly"
                else:
                    actual_label = "limit"

            # Avoid duplicates
            if any(b.label == actual_label for b in buckets):
                continue

            buckets.append(UsageBucket(
                label=actual_label,
                percent_remaining=percent,
                reset_time=None,  # raw time string stored if needed
            ))

    return buckets if buckets else None


def _fetch_via_api() -> Optional[list[UsageBucket]]:
    """
    Fetch usage from the Codex web dashboard API.
    Requires a valid ChatGPT session token.
    """
    if requests is None:
        return None

    # The Codex usage dashboard endpoint
    url = "https://chatgpt.com/codex/settings/usage"

    headers = {
        "Accept": "application/json",
        "User-Agent": "usage-monitor/1.0",
    }

    if config.CODEX_SESSION_TOKEN:
        headers["Authorization"] = f"Bearer {config.CODEX_SESSION_TOKEN}"
    elif config.OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {config.OPENAI_API_KEY}"

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Codex API returned {resp.status_code}")
            return None

        data = resp.json()
        # Parse based on whatever structure the API returns
        # This is speculative — adjust once you see actual response
        buckets = []

        if "five_hour" in data:
            buckets.append(_parse_api_bucket(data["five_hour"], "Current session"))
        if "weekly" in data:
            buckets.append(_parse_api_bucket(data["weekly"], "Weekly"))

        return buckets if buckets else None

    except Exception as e:
        logger.error(f"Codex API fetch failed: {e}")
        return None


def _parse_api_bucket(data: dict, label: str) -> UsageBucket:
    """Parse a single bucket from the API response."""
    remaining = 100.0

    if "percentRemaining" in data:
        remaining = float(data["percentRemaining"])
    elif "used" in data and "limit" in data:
        used = float(data["used"])
        limit = float(data["limit"])
        if limit > 0:
            remaining = max(0, (1 - used / limit) * 100)

    reset_time = None
    for key in ("resetsAt", "resets_at", "reset_time"):
        if key in data and data[key]:
            try:
                reset_time = datetime.fromisoformat(
                    str(data[key]).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
            break

    return UsageBucket(
        label=label,
        percent_remaining=round(remaining, 1),
        reset_time=reset_time,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    usage = fetch_codex_usage()
    for b in usage:
        print(f"{b.label}: {b.percent_remaining}% remaining | resets: {b.reset_time}")
