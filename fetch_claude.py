"""
Fetch Claude Code usage limits via the Anthropic OAuth usage API.

Since /usage is an interactive-only slash command (doesn't work with
`claude -p`), we use the HTTP API directly. The token is sourced from:

  1. Claude Code's own credential storage on this machine
     (~/.claude/.credentials.json — written when you authenticate
     Claude Code via `claude setup-token` or browser login)
  2. config.CLAUDE_OAUTH_TOKEN (full JSON or bare access token)
  3. config.CLAUDE_CREDENTIALS_FILE

Auto-refreshes expired tokens and persists new ones to disk.

API response format (from reverse-engineering):
{
  "five_hour": { "utilization": 0.28, "resets_at": "2026-04-14T22:00:00Z" },
  "seven_day": { "utilization": 0.52, "resets_at": "2026-04-18T09:00:00Z" }
}
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

import config

logger = logging.getLogger(__name__)


@dataclass
class UsageBucket:
    """A single usage limit bucket."""
    label: str
    percent_remaining: float  # 0-100, or -1 if unavailable
    reset_time: Optional[datetime] = None
    raw: Optional[dict] = None


# --- Token persistence file (for refreshed tokens) ---
_TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".claude_token.json"
)

# --- Claude Code's own credential locations ---
_CC_CRED_PATHS = [
    Path.home() / ".claude" / ".credentials.json",
    Path.home() / ".claude" / "credentials.json",
]


def fetch_claude_usage() -> list[UsageBucket]:
    """Fetch Claude Code usage data via the OAuth API."""
    if requests is None:
        logger.error("requests library not installed")
        return _unavailable()

    token_data = _load_token_data()
    if not token_data or not token_data.get("accessToken"):
        logger.error(
            "No Claude token found. Either:\n"
            "  1. Run `claude setup-token` on your Mac, then on the Pi:\n"
            "     echo 'export CLAUDE_CODE_OAUTH_TOKEN=<token>' >> ~/.bashrc\n"
            "     Then run `claude` once so it writes ~/.claude/.credentials.json\n"
            "  2. Or paste the token into config.py CLAUDE_OAUTH_TOKEN"
        )
        return _unavailable()

    # Try the API call
    result = _call_usage_api(token_data["accessToken"])

    # If 401, try refreshing
    if result is None and token_data.get("refreshToken"):
        logger.info("Access token may be expired, attempting refresh...")
        refreshed = _refresh_token(token_data)
        if refreshed:
            result = _call_usage_api(refreshed["accessToken"])

    if result is not None:
        return result

    logger.warning("Could not fetch Claude usage data")
    return _unavailable()


def _unavailable() -> list[UsageBucket]:
    return [
        UsageBucket(label="Current session", percent_remaining=-1),
        UsageBucket(label="Weekly", percent_remaining=-1),
    ]


# --- Token Loading ---

def _load_token_data() -> Optional[dict]:
    """
    Load token data from multiple sources, in priority order:
    1. Our persisted refresh file (.claude_token.json)
    2. Claude Code's own credentials on this machine
    3. config.CLAUDE_OAUTH_TOKEN
    4. config.CLAUDE_CREDENTIALS_FILE
    """
    # 1. Our persisted token (has freshest refreshed data)
    data = _read_json_file(_TOKEN_FILE)
    if data and data.get("accessToken"):
        return data

    # 2. Claude Code's own credentials file on this Pi
    for cred_path in _CC_CRED_PATHS:
        if cred_path.is_file():
            data = _read_json_file(str(cred_path))
            if data:
                # Unwrap nested format
                if "claudeAiOauth" in data:
                    data = data["claudeAiOauth"]
                if data.get("accessToken"):
                    logger.info(f"Using Claude Code credentials from {cred_path}")
                    _save_token_data(data)
                    return data

    # 3. config.CLAUDE_OAUTH_TOKEN
    token_val = config.CLAUDE_OAUTH_TOKEN
    if token_val:
        if token_val.strip().startswith("{"):
            try:
                data = json.loads(token_val)
                if "claudeAiOauth" in data:
                    data = data["claudeAiOauth"]
                if data.get("accessToken"):
                    _save_token_data(data)
                    return data
            except json.JSONDecodeError:
                pass
        else:
            # Bare access token string
            return {"accessToken": token_val}

    # 4. config.CLAUDE_CREDENTIALS_FILE
    if config.CLAUDE_CREDENTIALS_FILE:
        data = _read_json_file(config.CLAUDE_CREDENTIALS_FILE)
        if data:
            if "claudeAiOauth" in data:
                data = data["claudeAiOauth"]
            if data.get("accessToken"):
                return data

    return None


def _read_json_file(path: str) -> Optional[dict]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None


def _save_token_data(data: dict):
    try:
        with open(_TOKEN_FILE, "w") as f:
            json.dump(data, f)
        os.chmod(_TOKEN_FILE, 0o600)
    except IOError as e:
        logger.warning(f"Could not save token file: {e}")


# --- API Calls ---

def _call_usage_api(access_token: str) -> Optional[list[UsageBucket]]:
    """Call the Anthropic OAuth usage endpoint."""
    try:
        resp = requests.get(
            config.CLAUDE_USAGE_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": "claude-code/2.1.108",
            },
            timeout=15,
        )

        if resp.status_code == 401:
            logger.debug("API returned 401")
            return None

        resp.raise_for_status()
        data = resp.json()
        logger.debug(f"Usage API response: {json.dumps(data, indent=2)}")

        buckets = []

        # Parse five_hour bucket
        fh = data.get("five_hour")
        if fh:
            buckets.append(_parse_bucket(fh, "Current session"))
        else:
            buckets.append(UsageBucket(label="Current session", percent_remaining=-1))

        # Parse seven_day bucket
        sd = data.get("seven_day")
        if sd:
            buckets.append(_parse_bucket(sd, "Weekly"))
        else:
            buckets.append(UsageBucket(label="Weekly", percent_remaining=-1))

        return buckets

    except requests.exceptions.HTTPError as e:
        logger.error(f"Usage API HTTP error: {e}")
        return None
    except Exception as e:
        logger.error(f"Usage API call failed: {e}")
        return None


def _parse_bucket(bucket_data: dict, label: str) -> UsageBucket:
    """Parse a usage bucket from the API response."""
    remaining = 100.0
    reset_time = None

    # The API returns "utilization" as a 0-1 float (fraction used)
    if "utilization" in bucket_data:
        used_fraction = float(bucket_data["utilization"])
        remaining = max(0, (1 - used_fraction) * 100)
    elif "percentRemaining" in bucket_data:
        remaining = float(bucket_data["percentRemaining"])
    elif "percent_remaining" in bucket_data:
        remaining = float(bucket_data["percent_remaining"])

    # Parse reset time
    for key in ("resets_at", "resetsAt", "reset_time", "resetTime"):
        val = bucket_data.get(key)
        if val:
            try:
                reset_time = datetime.fromisoformat(
                    str(val).replace("Z", "+00:00")
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


# --- Token Refresh ---

def _refresh_token(token_data: dict) -> Optional[dict]:
    """Use the refresh token to get a new access token."""
    refresh_token = token_data.get("refreshToken")
    if not refresh_token:
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
            logger.error(f"Token refresh returned {resp.status_code}: {resp.text}")
            return None

        new_data = resp.json()
        updated = {
            "accessToken": new_data.get("access_token", new_data.get("accessToken", "")),
            "refreshToken": new_data.get("refresh_token", new_data.get("refreshToken", refresh_token)),
            "expiresAt": new_data.get("expires_at", new_data.get("expiresAt", "")),
        }

        if updated["accessToken"]:
            _save_token_data(updated)
            logger.info("Token refreshed successfully")
            return updated

        return None

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    usage = fetch_claude_usage()
    for b in usage:
        print(f"{b.label}: {b.percent_remaining}% remaining | resets: {b.reset_time}")
