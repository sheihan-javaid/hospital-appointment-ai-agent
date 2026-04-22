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

    # round to next slot
    discard = dt.timedelta(
        minutes=candidate.minute % SLOT_ROUND_MINUTES,
        seconds=candidate.second,
        microseconds=candidate.microsecond,
    )
    if discard.total_seconds() > 0:
        candidate += dt.timedelta(minutes=SLOT_ROUND_MINUTES) - discard

    if candidate.hour < BUSINESS_HOUR_START:
        candidate = candidate.replace(hour=BUSINESS_HOUR_START, minute=0, second=0, microsecond=0)

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

    if not text or not text.strip():
        raise TimeParseError("Empty time expression")

    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text, flags=re.IGNORECASE)
    text = text.lower().strip()

    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=KOLKATA)
    else:
        reference_time = reference_time.astimezone(KOLKATA)

    logger.debug("resolve_datetime: input=%r | reference=%s", text, reference_time)

    priority = detect_priority(text)
    if priority == "EARLIEST":
        return _resolve_earliest(reference_time)

    recognizer = _get_recognizer()
    results = recognizer.get_datetime_model().parse(text, reference_time)

    logger.debug("recognizer output: %s", results)

    if not results:
        logger.warning("Recognizer failed, trying fallback: %r", text)

        match = re.search(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})\s+(\d{1,2})\s*(am|pm)",
            text
        )

        if match:
            month, day, hour, meridian = match.groups()

            try:
                dt_obj = dt.datetime.strptime(
                    f"{month} {day} {hour} {meridian}",
                    "%B %d %I %p"
                )

                dt_obj = dt_obj.replace(
                    year=reference_time.year,
                    tzinfo=KOLKATA
                )

                # 🔥 future correction
                if dt_obj <= reference_time:
                    dt_obj = dt_obj.replace(year=reference_time.year + 1)

                return dt_obj

            except Exception as e:
                logger.warning("Fallback parse failed: %s", e)

        raise TimeParseError(f"Could not parse time: '{text}'")

    # ===================================================
    # NORMAL FLOW
    # ===================================================
    entity = results[0].resolution
    values = entity.get("values", [])

    if not values:
        raise TimeParseError("No valid datetime found")

    best = values[0]

    # -------------------------
    # CASE 1: FULL VALUE
    # -------------------------
    if "value" in best:
        dt_obj = dt.datetime.fromisoformat(best["value"])

    # -------------------------
    # CASE 2: TIMEX
    # -------------------------
    elif "timex" in best:
        timex = best["timex"]

        try:
            year = reference_time.year
            timex = timex.replace("XXXX", str(year))

            dt_obj = dt.datetime.fromisoformat(timex)

            if dt_obj <= reference_time:
                dt_obj = dt_obj.replace(year=year + 1)

        except Exception:
            raise TimeParseError(f"Could not parse time: '{text}'")

    else:
        raise TimeParseError(f"Unsupported datetime format: {best}")

    # -------------------------
    # FINAL NORMALIZATION
    # -------------------------
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=KOLKATA)

    return dt_obj.astimezone(KOLKATA)