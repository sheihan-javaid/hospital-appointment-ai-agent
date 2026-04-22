from recognizers_text import Culture
from recognizers_date_time import DateTimeRecognizer
from zoneinfo import ZoneInfo
import datetime as dt
import functools
import logging

logger = logging.getLogger("time_parser")

KOLKATA = ZoneInfo("Asia/Kolkata")

# -------------------------
# RECOGNIZER CACHE
# -------------------------
@functools.lru_cache(maxsize=1)
def _get_recognizer() -> DateTimeRecognizer:
    return DateTimeRecognizer(Culture.English)


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
# EARLIEST SLOT CONSTANTS
# -------------------------
EARLIEST_ADVANCE_MINUTES = 180  # 3-hour buffer for "asap"
SLOT_ROUND_MINUTES       = 15   # round up to next 15-min boundary
BUSINESS_HOUR_START      = 9    # 09:00 inclusive
BUSINESS_HOUR_END        = 20   # 20:00 EXCLUSIVE — booking at 20:00 → next day 09:00


# -------------------------
# EXCEPTIONS
# -------------------------
class TimeParseError(Exception):
    pass


# -------------------------
# PRIORITY DETECTION
# -------------------------
def detect_priority(text: str) -> str | None:
    text_lower = text.lower().strip()
    for phrase in sorted(PRIORITY_PHRASES, key=len, reverse=True):
        if phrase in text_lower:
            return PRIORITY_PHRASES[phrase]
    return None


# -------------------------
# EARLIEST SLOT RESOLVER
# -------------------------
def _resolve_earliest(reference_time: dt.datetime) -> dt.datetime:
    candidate = reference_time + dt.timedelta(minutes=EARLIEST_ADVANCE_MINUTES)

    # Round up to next 15-min slot
    discard = dt.timedelta(
        minutes=candidate.minute % SLOT_ROUND_MINUTES,
        seconds=candidate.second,
        microseconds=candidate.microsecond,
    )
    if discard.total_seconds() > 0:
        candidate += dt.timedelta(minutes=SLOT_ROUND_MINUTES) - discard

    # Clamp to business hours
    # 20:00 is EXCLUDED — >= 20:00 pushes to next day
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

    logger.debug("_resolve_earliest: reference=%s → slot=%s", reference_time, candidate)
    return candidate.astimezone(KOLKATA)


# -------------------------
# MAIN RESOLVER
# -------------------------
def resolve_datetime(text: str, reference_time: dt.datetime) -> dt.datetime:
    """
    Converts natural language → absolute datetime (Asia/Kolkata).

    Resolution order:
      1. Normalize reference_time to KOLKATA
      2. Priority phrase check  → _resolve_earliest()
      3. recognizers-text NLP   → structured datetime parse
    """
    if not text or not text.strip():
        raise TimeParseError("Empty time expression")

    # ── Step 1: ensure reference_time is KOLKATA-aware ───────────
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=KOLKATA)
    else:
        reference_time = reference_time.astimezone(KOLKATA)

    logger.debug("resolve_datetime: input=%r | reference=%s", text, reference_time)

    # ── Step 2: priority phrases ──────────────────────────────────
    priority = detect_priority(text)
    if priority == "EARLIEST":
        return _resolve_earliest(reference_time)

    # ── Step 3: NLP datetime recognition ─────────────────────────
    recognizer = _get_recognizer()
    results = recognizer.get_date_time_model().parse(text, reference_time)

    logger.debug("recognizer output: %s", results)

    if not results:
        logger.warning("Unparseable time expression: %r", text)
        raise TimeParseError(f"Could not parse time: '{text}'")

    entity = results[0].resolution
    values = entity.get("values", [])

    if not values:
        logger.warning("No values in recognizer output for: %r", text)
        raise TimeParseError("No valid datetime found in recognizer output")

    best = values[0]

    if "value" not in best:
        logger.warning("Unsupported format for: %r → %s", text, best)
        raise TimeParseError(f"Unsupported datetime format returned: {best}")

    dt_obj = dt.datetime.fromisoformat(best["value"])

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=KOLKATA)

    return dt_obj.astimezone(KOLKATA)