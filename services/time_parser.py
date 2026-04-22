from recognizers_text import Culture
from recognizers_date_time import recognize_datetime
import datetime as dt
from zoneinfo import ZoneInfo

KOLKATA = ZoneInfo("Asia/Kolkata")


class TimeParseError(Exception):
    pass


def resolve_datetime(text: str, reference_time: dt.datetime):
    """
    Converts natural language → absolute datetime
    NO guessing, only structured output.
    """

    if not text or not text.strip():
        raise TimeParseError("Empty time expression")

    results = recognize_datetime(
        text,
        Culture.English,
        reference=reference_time,
    )

    if not results:
        raise TimeParseError(f"Could not parse time: {text}")

    # Take best candidate
    entity = results[0].resolution

    values = entity.get("values", [])
    if not values:
        raise TimeParseError("No valid datetime found")

    best = values[0]

    # Handle single datetime
    if "value" in best:
        parsed = best["value"]
        dt_obj = dt.datetime.fromisoformat(parsed)

        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=KOLKATA)

        return dt_obj.astimezone(KOLKATA)

    raise TimeParseError("Unsupported datetime format returned")