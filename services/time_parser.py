import dateparser
import pendulum
import datetime as dt
from zoneinfo import ZoneInfo
import logging
import re

logger = logging.getLogger("time_parser")

KOLKATA = ZoneInfo("Asia/Kolkata")

# -------------------------
# PRIORITY PHRASES
# -------------------------
PRIORITY_PHRASES = {
    "as soon as possible": "EARLIEST",
    "earliest possible time": "EARLIEST",
    "earliest slot available": "EARLIEST",
    "first available slot": "EARLIEST",
    "earliest available": "EARLIEST",
    "right away": "EARLIEST",
    "asap": "EARLIEST",
    "urgent": "EARLIEST",
}

# -------------------------
# EARLIEST SLOT CONSTANTS
# -------------------------
EARLIEST_ADVANCE_MINUTES = 120
SLOT_ROUND_MINUTES = 15
BUSINESS_HOUR_START = 9
BUSINESS_HOUR_END = 20
MAX_DAYS_AHEAD = 365

# -------------------------
# TIME WORD MAPPING
# -------------------------
TIME_MAP = {
    "morning": "09:00",
    "afternoon": "15:00",
    "evening": "18:00",
    "night": "19:00",
    "tonight": "19:00",
    "noon": "12:00",
}

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
    ref = pendulum.instance(reference_time).in_timezone("Asia/Kolkata")
    candidate = ref.add(minutes=EARLIEST_ADVANCE_MINUTES)

    result = _apply_rules(candidate, ref)

    # enforce MAX_DAYS_AHEAD cap after business-hour adjustment
    if result > ref.add(days=MAX_DAYS_AHEAD):
        raise TimeParseError("DATE_TOO_FAR")

    return result


# -------------------------
# DATE-ONLY RESOLVER (for cancel / list flows)
# -------------------------
def resolve_date(text: str, reference_time: dt.datetime) -> dt.date:
    """
    Resolves a natural language date expression to a dt.date.
    Accepts day names, relative words, and partial dates:
      "today", "tomorrow", "monday", "next friday",
      "april 23rd", "24th april", "23 april", etc.

    Does NOT apply ambiguity checks — a bare day name like
    "monday" is intentionally valid here.

    Raises TimeParseError on empty or unparseable input,
    or if the resolved date is in the past or beyond MAX_DAYS_AHEAD.
    """
    if not text or not text.strip():
        raise TimeParseError("EMPTY_INPUT")

    text = text.lower().strip()

    # normalize ordinals: "23rd" → "23", "4th" → "4"
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)

    # ensure timezone
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=KOLKATA)
    else:
        reference_time = reference_time.astimezone(KOLKATA)

    ref = pendulum.instance(reference_time)

    logger.debug("resolve_date: input=%r | reference=%s", text, ref)

    parsed = dateparser.parse(
        text,
        settings={
            "RELATIVE_BASE": ref,
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "Asia/Kolkata",
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
    )

    if not parsed:
        logger.warning("Unparseable date expression: %r", text)
        raise TimeParseError("UNPARSABLE_DATE")

    result_date = pendulum.instance(parsed).in_timezone("Asia/Kolkata").date()

    # must not be in the past
    today = ref.date()
    if result_date < today:
        raise TimeParseError("DATE_IN_PAST")

    # must be within allowed range
    if result_date > ref.add(days=MAX_DAYS_AHEAD).date():
        raise TimeParseError("DATE_TOO_FAR")

    return result_date


# -------------------------
# MAIN RESOLVER (for schedule flow)
# -------------------------
def resolve_datetime(text: str, reference_time: dt.datetime) -> dt.datetime:

    if not text or not text.strip():
        raise TimeParseError("EMPTY_INPUT")

    original_text = text
    text = text.lower().strip()

    # normalize ordinals (22nd → 22)
    text = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', text)

    # normalize "10am" → "10 am"
    text = re.sub(r'(\d)(am|pm)', r'\1 \2', text)

    # ensure timezone
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=KOLKATA)
    else:
        reference_time = reference_time.astimezone(KOLKATA)

    ref = pendulum.instance(reference_time)

    logger.debug("resolve_datetime: input=%r | reference=%s", text, ref)

    # ---------------- PRIORITY ----------------
    if detect_priority(text) == "EARLIEST":
        return _resolve_earliest(reference_time)

    # ---------------- TIME WORD MAPPING ----------------
    for word, val in TIME_MAP.items():
        text = re.sub(rf"\b{word}\b", val, text)

    # ---------------- PARSE ----------------
    dt_obj = dateparser.parse(
        text,
        settings={
            "RELATIVE_BASE": ref,
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "Asia/Kolkata",
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
    )

    if not dt_obj:
        logger.warning("Unparseable time expression: %r", original_text)
        raise TimeParseError("UNPARSABLE_TIME")

    dt_obj = pendulum.instance(dt_obj).in_timezone("Asia/Kolkata")

    # ---------------- AMBIGUITY CHECK ----------------
    if _is_ambiguous(original_text):
        logger.warning("Ambiguous time expression: %r", original_text)
        raise TimeParseError("AMBIGUOUS_TIME")

    # ---------------- FUTURE CORRECTION ----------------
    max_iterations = MAX_DAYS_AHEAD
    iterations = 0
    while dt_obj <= ref:
        if iterations >= max_iterations:
            raise TimeParseError("UNPARSABLE_TIME")
        dt_obj = dt_obj.add(days=1)
        iterations += 1

    # ---------------- RANGE LIMIT ----------------
    if dt_obj > ref.add(days=MAX_DAYS_AHEAD):
        raise TimeParseError("DATE_TOO_FAR")

    # ---------------- FINAL RULES ----------------
    dt_obj = _apply_rules(dt_obj, ref)

    # ---------------- POST-RULE RANGE CHECK ----------------
    if dt_obj > ref.add(days=MAX_DAYS_AHEAD):
        raise TimeParseError("DATE_TOO_FAR")

    return dt_obj.in_timezone("Asia/Kolkata")


# -------------------------
# APPLY BUSINESS RULES
# -------------------------
def _apply_rules(dt_obj: pendulum.DateTime, ref: pendulum.DateTime) -> pendulum.DateTime:

    # round up to next slot boundary
    if dt_obj.minute % SLOT_ROUND_MINUTES != 0:
        dt_obj = dt_obj.add(
            minutes=(SLOT_ROUND_MINUTES - dt_obj.minute % SLOT_ROUND_MINUTES)
        ).replace(second=0, microsecond=0)

    # too early → snap to opening time same day
    if dt_obj.hour < BUSINESS_HOUR_START:
        dt_obj = dt_obj.replace(hour=BUSINESS_HOUR_START, minute=0, second=0, microsecond=0)

    # too late → snap to opening time next day
    elif dt_obj.hour >= BUSINESS_HOUR_END:
        dt_obj = dt_obj.add(days=1).replace(
            hour=BUSINESS_HOUR_START, minute=0, second=0, microsecond=0
        )

    # after business-hour adjustment, ensure still in the future
    if dt_obj <= ref:
        dt_obj = dt_obj.add(days=1).replace(
            hour=BUSINESS_HOUR_START, minute=0, second=0, microsecond=0
        )

    return dt_obj


# -------------------------
# AMBIGUITY DETECTOR (schedule flow only)
# -------------------------
def _is_ambiguous(text: str) -> bool:
    text = text.strip().lower()
    vague_patterns = [
        r"^\d{1,2}$",
        r"^(?:morning|afternoon|evening|night|tonight|noon)$",
        r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow)$",
    ]

    return any(re.fullmatch(p, text) for p in vague_patterns)