# services/time_parser.py

from recognizers_text import Culture
from recognizers_date_time import recognize_datetime
import datetime as dt
from zoneinfo import ZoneInfo

KOLKATA = ZoneInfo("Asia/Kolkata")

# -------------------------
# PRIORITY PHRASES
# -------------------------
PRIORITY_PHRASES = {
    "as soon as possible":     "EARLIEST",
    "earliest possible time":  "EARLIEST",
    "earliest slot available": "EARLIEST",
    "first available slot":    "EARLIEST",
    "earliest available":      "EARLIEST",
    "right away":              "EARLIEST",
    "asap":                    "EARLIEST",
    "urgent":                  "EARLIEST",
}

# -------------------------
# EARLIEST TIME CONSTANTS
# -------------------------
EARLIEST_ADVANCE_MINUTES = 180   # 3 hours buffer for "asap"
SLOT_ROUND_MINUTES       = 15    # round up to next 15-min slot
BUSINESS_HOUR_START      = 9     # 09:00
BUSINESS_HOUR_END        = 20    # 20:00


# -------------------------
# EXCEPTIONS
# -------------------------
class TimeParseError(Exception):
    pass


# -------------------------
# PRIORITY DETECTION
# -------------------------
def detect_priority(text: str) -> str | None:
    """
    Scans input for priority phrases.
    Checks longest phrases first to avoid partial false matches
    e.g. 'earliest available' matching before 'earliest slot available'.
    """
    text_lower = text.lower().strip()
    for phrase in sorted(PRIORITY_PHRASES, key=len, reverse=True):
        if phrase in text_lower:
            return PRIORITY_PHRASES[phrase]
    return None


# -------------------------
# EARLIEST SLOT RESOLVER
# -------------------------
def _resolve_earliest(reference_time: dt.datetime) -> dt.datetime:
    """
    Resolves 'asap / earliest' to a concrete datetime:
      1. Add EARLIEST_ADVANCE_MINUTES to reference_time
      2. Round up to next SLOT_ROUND_MINUTES boundary
      3. Clamp to business hours:
           < 09:00  → 09:00 same day
           > 20:00  → 09:00 next business day
    """
    # Step 1 — add buffer
    candidate = reference_time + dt.timedelta(minutes=EARLIEST_ADVANCE_MINUTES)

    # Step 2 — round up to next 15-min slot
    discard = dt.timedelta(
        minutes=candidate.minute % SLOT_ROUND_MINUTES,
        seconds=candidate.second,
        microseconds=candidate.microsecond,
    )
    if discard.total_seconds() > 0:
        candidate += dt.timedelta(minutes=SLOT_ROUND_MINUTES) - discard

    # Step 3 — clamp to business hours
    if candidate.hour < BUSINESS_HOUR_START:
        candidate = candidate.replace(
            hour=BUSINESS_HOUR_START, minute=0, second=0, microsecond=0
        )
    elif candidate.hour >= BUSINESS_HOUR_END:
        next_day = candidate.date() + dt.timedelta(days=1)
        candidate = dt.datetime(
            next_day.year, next_day.month, next_day.day,
            BUSINESS_HOUR_START, 0, 0,
            tzinfo=KOLKATA,
        )

    return candidate.astimezone(KOLKATA)


# -------------------------
# MAIN RESOLVER
# -------------------------
def resolve_datetime(text: str, reference_time: dt.datetime) -> dt.datetime:
    """
    Converts natural language → absolute datetime (Asia/Kolkata).

    Resolution order:
      1. Priority phrase check  → _resolve_earliest()
      2. recognizers-text NLP   → structured datetime parse
    """
    if not text or not text.strip():
        raise TimeParseError("Empty time expression")

    # ── Step 1: priority phrases ──────────────────────────────────
    priority = detect_priority(text)
    if priority == "EARLIEST":
        return _resolve_earliest(reference_time)

    # ── Step 2: NLP datetime recognition ─────────────────────────
    results = recognize_datetime(
        text,
        Culture.English,
        reference=reference_time,
    )

    if not results:
        raise TimeParseError(f"Could not parse time: '{text}'")

    entity = results[0].resolution
    values = entity.get("values", [])

    if not values:
        raise TimeParseError("No valid datetime found in recognizer output")

    best = values[0]

    if "value" not in best:
        raise TimeParseError(f"Unsupported datetime format returned: {best}")

    dt_obj = dt.datetime.fromisoformat(best["value"])

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=KOLKATA)

    return dt_obj.astimezone(KOLKATA)