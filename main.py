from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import datetime as dt
import re
import logging
import os

from pydantic import BaseModel, ConfigDict
from zoneinfo import ZoneInfo

from database import init_db, get_db, to_utc_naive, KOLKATA

try:
    from dateutil.parser import isoparse as _isoparse
except Exception:  # dateutil not installed
    _isoparse = None


# Configuration
DATE_INPUT_FORMAT = "%d-%m-%Y"
UTC = dt.timezone.utc
START_TIME_ERROR_DETAIL = (
    "Invalid start_time. Use ISO datetime (with timezone),\n"
    "or 'today/tomorrow at time', or 'dd-mm-yyyy HH:MM' (optionally am/pm)."
)


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hospital_ai_agent.main")


app = FastAPI(title="Hospital Appointment API")

# Allow origins configured via env var (comma-separated), otherwise allow none
_cors_origins = os.environ.get("CORS_ORIGINS")
if _cors_origins:
    origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
else:
    origins = []

if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def on_startup():
    # Initialize DB and other startup-only tasks
    try:
        init_db()
        logger.info("Database initialized")
    except Exception:
        logger.exception("Failed to initialize database on startup")


def kolkata_now() -> dt.datetime:
    return dt.datetime.now(KOLKATA)


def normalize_specialty_filter(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(
        r"\b(dr|doctor|doctors|any|available|availability|show|check|find|list|please|the|a|an|today|tomorrow|now|tonight|speciality|specialty)\b",
        " ",
        cleaned,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


# Models
class AppointmentRequest(BaseModel):
    patient_name: str
    reason: str | None = None
    start_time: str | dt.datetime


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={dt.datetime: lambda v: v.astimezone(KOLKATA).strftime("%Y-%m-%d %H:%M:%S")},
    )

    id: str
    patient_name: str
    reason: str | None
    start_time: dt.datetime
    cancelled: bool
    created_at: dt.datetime


class CancelAppointmentRequest(BaseModel):
    patient_name: str
    date: str | dt.date


class CancelAppointmentResponse(BaseModel):
    success: bool
    message: str


# Parsing helpers
def _parse_time_component(value: str) -> dt.time:
    normalized = value.strip().lower().replace(".", "")
    normalized = re.sub(r"\s+", " ", normalized)

    ampm = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", normalized)
    if ampm:
        hour = int(ampm.group(1))
        minute = int(ampm.group(2) or 0)
        meridiem = ampm.group(3)

        if hour < 1 or hour > 12 or minute < 0 or minute > 59:
            raise HTTPException(status_code=422, detail="Invalid 12-hour time")

        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        return dt.time(hour=hour, minute=minute)

    for fmt in ("%H:%M", "%H"):
        try:
            return dt.datetime.strptime(normalized, fmt).time()
        except ValueError:
            continue

    raise HTTPException(status_code=422, detail="Invalid time format")


def _parse_iso_datetime(s: str) -> dt.datetime | None:
    s = s.strip()
    if not s:
        return None

    # Prefer dateutil if available (handles more variants)
    if _isoparse is not None:
        try:
            return _isoparse(s)
        except Exception:
            return None

    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_request_date(value: str | dt.date | dt.datetime | None) -> dt.date:
    if value is None:
        return kolkata_now().date()

    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    normalized = str(value).strip().lower().replace("tommorow", "tomorrow")
    today = kolkata_now().date()

    if normalized == "today":
        return today
    if normalized == "tomorrow":
        return today + dt.timedelta(days=1)

    try:
        return dt.datetime.strptime(normalized, DATE_INPUT_FORMAT).date()
    except ValueError:
        raise HTTPException(status_code=422, detail="Date must be 'today', 'tomorrow', or dd-mm-yyyy")


def parse_start_time(value: str | dt.datetime) -> dt.datetime:
    """Parse start_time from multiple input forms and return timezone-aware datetime in KOLKATA."""
    now = kolkata_now()

    if isinstance(value, dt.datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            raise HTTPException(status_code=422, detail=START_TIME_ERROR_DETAIL)

        # try ISO parsing first
        parsed = _parse_iso_datetime(raw)

        # relative forms: today/tomorrow at <time>
        if parsed is None:
            normalized = re.sub(r"\s+", " ", raw.lower()).replace("tommorow", "tomorrow")
            rel = re.fullmatch(r"(today|tomorrow)(?:\s+at)?\s+(.+)", normalized)
            if rel:
                base = now.date() + (dt.timedelta(days=1) if rel.group(1) == "tomorrow" else dt.timedelta())
                parsed = dt.datetime.combine(base, _parse_time_component(rel.group(2)))

        # dd-mm-yyyy [time]
        if parsed is None:
            m = re.fullmatch(r"(\d{2}-\d{2}-\d{4})(?:\s+(.+))?", raw)
            if m:
                try:
                    parsed_date = dt.datetime.strptime(m.group(1), DATE_INPUT_FORMAT).date()
                    parsed_time = _parse_time_component(m.group(2) or "09:00")
                    parsed = dt.datetime.combine(parsed_date, parsed_time)
                except ValueError:
                    parsed = None

        if parsed is None:
            raise HTTPException(status_code=422, detail=START_TIME_ERROR_DETAIL)

    # Ensure timezone-aware in KOLKATA
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KOLKATA)
    else:
        parsed = parsed.astimezone(KOLKATA)

    # Sanity checks: year must be reasonable and time must be in future
    if parsed.year < (now.year - 1) or parsed.year > (now.year + 2):
        raise HTTPException(status_code=422, detail="start_time year looks incorrect")

    return parsed


# Health endpoint
@app.get("/now")
def get_now():
    now = kolkata_now()
    return {"iso": now.isoformat(), "date": now.strftime("%d-%m-%Y"), "time": now.strftime("%H:%M:%S")}


@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    # Log incoming payload for traceability
    try:
        logger.info("schedule_appointment request: %s", appointment.model_dump())
    except Exception:
        logger.info("schedule_appointment request (raw): %s", str(appointment))

    start_time = parse_start_time(appointment.start_time)
    now = kolkata_now()

    if start_time <= now:
        raise HTTPException(status_code=400, detail="Start time must be later than current time")

    doc = {
        "patient_name": appointment.patient_name,
        "reason": appointment.reason,
        "start_time": to_utc_naive(start_time),
        "cancelled": False,
        "created_at": to_utc_naive(now),
    }

    res = db.appointments.insert_one(doc)
    inserted = db.appointments.find_one({"_id": res.inserted_id})

    return {
        "id": str(inserted["_id"]),
        "patient_name": inserted["patient_name"],
        "reason": inserted.get("reason"),
        "start_time": inserted["start_time"].replace(tzinfo=UTC).astimezone(KOLKATA),
        "cancelled": inserted.get("cancelled", False),
        "created_at": inserted["created_at"].replace(tzinfo=UTC).astimezone(KOLKATA),
    }


@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(request: CancelAppointmentRequest, db=Depends(get_db)):
    request_date = parse_request_date(request.date)
    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)

    start_q = to_utc_naive(start_dt)
    end_q = to_utc_naive(end_dt)

    res = db.appointments.update_many(
        {"patient_name": request.patient_name, "start_time": {"$gte": start_q, "$lte": end_q}, "cancelled": False},
        {"$set": {"cancelled": True}},
    )

    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="No appointments found")

    return {"success": True, "message": f"Cancelled {res.modified_count} appointment(s)"}


@app.get("/list_appointments/", response_model=List[AppointmentResponse])
def list_appointments(date: str = "today", db=Depends(get_db)):
    request_date = parse_request_date(date)
    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)

    start_q = to_utc_naive(start_dt)
    end_q = to_utc_naive(end_dt)

    cursor = db.appointments.find({"cancelled": False, "start_time": {"$gte": start_q, "$lte": end_q}}).sort("start_time", 1)

    results = []
    for d in cursor:
        results.append(
            {
                "id": str(d["_id"]),
                "patient_name": d["patient_name"],
                "reason": d.get("reason"),
                "start_time": d["start_time"].replace(tzinfo=UTC).astimezone(KOLKATA),
                "cancelled": d.get("cancelled", False),
                "created_at": d["created_at"].replace(tzinfo=UTC).astimezone(KOLKATA),
            }
        )

    return results


@app.get("/check_doctor_availability/")
def check_doctor_availability(
    date: str | None = None,
    specialty: str | None = None,
    speciality: str | None = None,
    doctor_name: str | None = None,
    name: str | None = None,
    db=Depends(get_db),
):
    resolved_date = parse_request_date(date)
    resolved_specialty = specialty or speciality
    resolved_name = doctor_name or name

    query = {"available": True}
    if resolved_name:
        query["name"] = {"$regex": resolved_name.strip(), "$options": "i"}
    if resolved_specialty:
        sf = normalize_specialty_filter(resolved_specialty)
        if sf:
            query["specialty"] = {"$regex": sf, "$options": "i"}

    cursor = db.doctors.find(query)
    available_doctors = [{"name": d["name"], "specialty": d["specialty"]} for d in cursor]

    response = {"date": resolved_date.strftime(DATE_INPUT_FORMAT), "available_doctors": available_doctors}
    if not resolved_name and not resolved_specialty:
        response["any_available_doctor"] = available_doctors[0] if available_doctors else None

    return response
