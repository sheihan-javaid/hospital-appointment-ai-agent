from recognizers_text import Culture
from recognizers_date_time import DateTimeRecognizer
from zoneinfo import ZoneInfo
import datetime as dt
import functools
import logging
import re  

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
EARLIEST_ADVANCE_MINUTES = 180
SLOT_ROUND_MINUTES       = 15
BUSINESS_HOUR_START      = 9
BUSINESS_HOUR_END        = 20


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

    discard = dt.timedelta(
        minutes=candidate.minute % SLOT_ROUND_MINUTES,
        seconds=candidate.second,
        microseconds=candidate.microsecond,
    )
    if discard.total_seconds() > 0:
        candidate += dt.timedelta(minutes=SLOT_ROUND_MINUTES) - discard

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
    if not text or not text.strip():
        raise TimeParseError("Empty time expression")

    # 🔥 STEP 0: CLEAN INPUT (fix "24th", "22nd", etc.)
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text, flags=re.IGNORECASE)

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
    results = recognizer.get_datetime_model().parse(text, reference_time)

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

    # -------------------------
    # CASE 1: FULL VALUE
    # -------------------------
    if "value" in best:
        dt_obj = dt.datetime.fromisoformat(best["value"])

    # -------------------------
    # CASE 2: TIMEX (MISSING YEAR)
    # -------------------------
    elif "timex" in best:
        timex = best["timex"]

        try:
            year = reference_time.year
            timex = timex.replace("XXXX", str(year))

            dt_obj = dt.datetime.fromisoformat(timex)

            # 🔥 Ensure future date
            if dt_obj <= reference_time:
                dt_obj = dt_obj.replace(year=year + 1)

        except Exception:
            logger.warning("Failed TIMEX parsing: %r → %s", text, best)
            raise TimeParseError(f"Could not parse time: '{text}'")

    # -------------------------
    # ❌ UNKNOWN FORMAT
    # -------------------------
    else:
        logger.warning("Unsupported format for: %r → %s", text, best)
        raise TimeParseError(f"Unsupported datetime format returned: {best}")

    # -------------------------
    # FINAL NORMALIZATION
    # -------------------------
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=KOLKATA)

    return dt_obj.astimezone(KOLKATA)