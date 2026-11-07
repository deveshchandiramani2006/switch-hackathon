"""
ValidationService - field-level validation with helpful error messages.

Each validator returns (parsed_value, error_msg).
error_msg is None if valid; a descriptive string if not.
"""
import re
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


def validate_money(s: str) -> tuple:
    """Parse money strings like Rs50000, Rs5L, Rs1Cr, 50000. Returns (int, error)."""
    if not s or not s.strip():
        return 0, "Amount is required"

    cleaned = str(s).strip().upper()
    cleaned = (cleaned
               .replace("RS", "")
               .replace("INR", "")
               .replace("₹", "")
               .replace(",", "")
               .replace(" ", "")
               .strip())

    try:
        if cleaned.endswith("CR"):
            val = int(float(cleaned[:-2]) * 10_000_000)
        elif cleaned.endswith("L"):
            val = int(float(cleaned[:-1]) * 100_000)
        elif cleaned.endswith("K"):
            val = int(float(cleaned[:-1]) * 1_000)
        else:
            val = int(float(cleaned))
        if val < 0:
            return 0, "Amount cannot be negative"
        return val, None
    except (ValueError, IndexError):
        return 0, f"Invalid amount '{s}' - use: Rs50000, Rs5L, Rs1Cr, or just 50000"


def validate_date(s: str) -> tuple:
    """Parse date strings. Supports YYYY-MM-DD, relative terms. Returns (date, error)."""
    if not s or not s.strip():
        return None, "Date is required"

    s = s.strip()
    lower = s.lower()

    # Relative dates
    if lower == "today":
        return date.today(), None
    if lower == "tomorrow":
        return date.today() + timedelta(days=1), None
    if lower in ("next friday", "this friday"):
        today = date.today()
        days_ahead = 4 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead), None
    if lower in ("next monday", "this monday"):
        today = date.today()
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return today + timedelta(days=days_ahead), None

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d %Y",
        "%B %d %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date(), None
        except ValueError:
            continue

    return None, f"Invalid date '{s}' - use YYYY-MM-DD (e.g. 2026-11-15) or 'today' / 'tomorrow'"


def validate_url(s: str) -> tuple:
    """Validate a URL. Returns (url, error)."""
    if not s or not s.strip():
        return "", "URL is required"

    s = s.strip()
    if not (s.startswith("http://") or s.startswith("https://")):
        return "", f"URL must start with https:// - got: '{s}'"

    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    if not re.match(pattern, s):
        return "", f"Invalid URL format: '{s}'"

    return s, None


def validate_integer(s: str, min_val: int = None, max_val: int = None) -> tuple:
    """Validate a whole number within optional range. Returns (int, error)."""
    try:
        val = int(str(s).strip())
    except (ValueError, AttributeError):
        return 0, f"Must be a whole number - got: '{s}'"

    if min_val is not None and val < min_val:
        return 0, f"Must be at least {min_val} - got {val}"
    if max_val is not None and val > max_val:
        return 0, f"Must be at most {max_val} - got {val}"

    return val, None


def validate_severity(s: str) -> tuple:
    """Validate bug severity P0-P3. Returns (severity, error)."""
    valid = {
        "P0": "production down / data loss / security breach",
        "P1": "major feature broken, blocks users",
        "P2": "degraded experience, workaround exists",
        "P3": "minor / cosmetic",
    }
    s = s.strip().upper()
    if s not in valid:
        lines = [f"Invalid severity '{s}' - use:"]
        for k, v in valid.items():
            lines.append(f"  {k}: {v}")
        return "", "\n".join(lines)
    return s, None


def validate_role(s: str) -> tuple:
    """Validate tenant user role. Returns (role, error)."""
    valid = ("admin", "manager", "member", "viewer")
    s = s.strip().lower()
    if s not in valid:
        return "", f"Invalid role '{s}' - use: {', '.join(valid)}"
    return s, None
