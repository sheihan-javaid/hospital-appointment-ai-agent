from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import re
import datetime as dt
import logging
import os
import uuid

from pydantic import BaseModel, ConfigDict
from zoneinfo import ZoneInfo

from database import init_db, get_db, to_utc_naive
from services.time_parser import resolve_datetime, resolve_date, TimeParseError
from services.specialty_normalizer import normalize_specialty

# -------------------------
# CONFIG
# -------------------------
UTC = dt.timezone.utc
KOLKATA = ZoneInfo("Asia/Kolkata")

MIN_ADVANCE_MINUTES = int(os.environ.get("MIN_ADVANCE_MINUTES", "15"))
MAX_FUTURE_DAYS = int(os.environ.get("MAX_FUTURE_DAYS", "365"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="VAPI Safe Hospital Appointment API")

# -------------------------
# CORS
# -------------------------
cors_origins = os.environ.get("CORS_ORIGINS")
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# -------------------------
# STARTUP
# -------------------------
@app.on_event("startup")
def startup():
    try:
        init_db()
        logger.info("Database initialized")
    except Exception:
        logger.exception("DB init failed")

# -------------------------
# MODELS
# -------------------------
class AppointmentRequest(BaseModel):
    patient_name: str
    reason: Optional[str] = None
    start_time: str   
    doctor_name: Optional[str] = None
    doctor_id: Optional[str] = None

class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_name: str
    reason: Optional[str]
    start_time: dt.datetime
    start_date: str        
    start_time_str: str    
    cancelled: bool
    created_at: dt.datetime
    doctor_name: Optional[str]
    doctor_id: Optional[str]

class CancelAppointmentRequest(BaseModel):
    patient_name: str
    date: str | dt.date

class CancelAppointmentResponse(BaseModel):
    success: bool
    message: str

# -------------------------
# TIME PARSE ERROR MESSAGES
# Human-readable versions of TimeParseError codes for VAPI responses.
# -------------------------
TIME_PARSE_ERROR_MESSAGES = {
    "EMPTY_INPUT":            "Please provide a time for the appointment.",
    "UNPARSABLE_TIME":        "I couldn't understand that time. Could you say it differently?",
    "AMBIGUOUS_TIME":         "That time is ambiguous. Could you be more specific?",
    "DATE_TOO_FAR":           "Appointments can only be booked up to a year in advance.",
    "OUTSIDE_BUSINESS_HOURS": "Appointments are only available between 9am and 8pm.",
}

DATE_PARSE_ERROR_MESSAGES = {
    "EMPTY_INPUT":      "Please provide a date.",
    "UNPARSABLE_DATE":  "I couldn't understand that date. Try saying 'today', 'tomorrow', a day name like 'Monday', or a date like 'April 25'.",
    "DATE_IN_PAST":     "That date has already passed. Please provide a future date.",
    "DATE_TOO_FAR":     "That date is too far ahead. Please choose a date within the next year.",
}

# -------------------------
# TIME HELPERS
# -------------------------
def kolkata_now() -> dt.datetime:
    return dt.datetime.now(KOLKATA)


def normalize_to_ist(dt_obj: dt.datetime) -> dt.datetime:
    if dt_obj.tzinfo is None:
        return dt_obj.replace(tzinfo=KOLKATA)
    return dt_obj.astimezone(KOLKATA)

# -------------------------
# SINGLE SOURCE OF TRUTH TIME PARSER (schedule flow)
# -------------------------
def parse_start_time(value: str) -> dt.datetime:
    now = kolkata_now()

    if not isinstance(value, str):
        value = str(value)
    value = value.strip()

    try:
        parsed = resolve_datetime(value, now)
    except TimeParseError as e:
        msg = TIME_PARSE_ERROR_MESSAGES.get(str(e), "I couldn't process that time.")
        raise HTTPException(status_code=422, detail=msg)

    parsed = normalize_to_ist(parsed)

    # Only validation main.py owns: minimum advance notice.
    # Future guarantee and MAX_FUTURE_DAYS are enforced inside resolve_datetime.
    min_allowed = now + dt.timedelta(minutes=MIN_ADVANCE_MINUTES)
    if parsed < min_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Appointments require at least {MIN_ADVANCE_MINUTES} minutes advance notice.",
        )

    return parsed

# -------------------------
def parse_request_date(value: str | dt.date | None) -> dt.date:
    now = kolkata_now()

    if value is None or (isinstance(value, str) and not value.strip()):
        # FIX: log a warning so silent fallbacks are visible
        logger.warning(
            "parse_request_date called with empty/None value — "
            "defaulting to today (%s). Check that the AI is sending "
            "the correct date parameter.",
            now.date().isoformat(),
        )
        return now.date()

    if isinstance(value, dt.date):
        return value

    raw = str(value).strip()

    # fast path: already a valid ISO date string
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        pass

    # natural language path — delegate to resolve_date
    try:
        return resolve_date(raw, now)
    except TimeParseError as e:
        msg = DATE_PARSE_ERROR_MESSAGES.get(str(e), "I couldn't understand that date.")
        raise HTTPException(status_code=422, detail=msg)

# -------------------------
# RESPONSE MAPPER (SAFE TZ)
# -------------------------
def appointment_to_response(doc: dict) -> dict:
    start_time = doc["start_time"]
    created_at = doc["created_at"]

    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    start_time = start_time.astimezone(KOLKATA)

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    created_at = created_at.astimezone(KOLKATA)

    return {
        "id": doc.get("appointment_id", str(doc["_id"])),
        "patient_name": doc["patient_name"],
        "reason": doc.get("reason"),
        "start_time": start_time,
        "start_date": start_time.strftime("%A, %d %B %Y"),
        "start_time_str": start_time.strftime("%I:%M %p").lstrip("0"),
        "cancelled": doc.get("cancelled", False),
        "created_at": created_at,
        "doctor_name": doc.get("doctor_name"),
        "doctor_id": doc.get("doctor_id"),
    }

# -------------------------
# ENDPOINTS
# -------------------------
@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appt: AppointmentRequest, db=Depends(get_db)):
    now = kolkata_now()
    start_time = parse_start_time(appt.start_time)

    appt_id = f"APPT-{uuid.uuid4().hex[:8].upper()}"

    # Resolve doctor_name / doctor_id if provided; prefer doctor_id as canonical identifier
    resolved_doctor_name = appt.doctor_name
    resolved_doctor_id = appt.doctor_id

    if resolved_doctor_id:
        found = db.doctors.find_one({"doctor_id": resolved_doctor_id})
        if not found:
            raise HTTPException(status_code=400, detail="No doctor found with that doctor_id.")
        if not resolved_doctor_name:
            resolved_doctor_name = found.get("name")
    elif resolved_doctor_name:
        # try exact-ish match first, then looser match
        matches = list(db.doctors.find({"name": {"$regex": f'^{resolved_doctor_name.strip()}$', "$options": "i"}}))
        if len(matches) == 0:
            matches = list(db.doctors.find({"name": {"$regex": resolved_doctor_name.strip(), "$options": "i"}}))
        if len(matches) == 0:
            raise HTTPException(status_code=400, detail="No matching doctor found for that name.")
        if len(matches) > 1:
            raise HTTPException(status_code=409, detail="Multiple doctors match that name; please provide doctor_id to disambiguate.")
        resolved_doctor_id = matches[0].get("doctor_id")

    doc = {
        "appointment_id": appt_id,
        "patient_name": appt.patient_name,
        "reason": appt.reason,
        "start_time": to_utc_naive(start_time),
        "cancelled": False,
        "created_at": to_utc_naive(now),
    }

    if resolved_doctor_name:
        doc["doctor_name"] = resolved_doctor_name
    if resolved_doctor_id:
        doc["doctor_id"] = resolved_doctor_id

    db.appointments.insert_one(doc)
    return appointment_to_response(doc)


@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(req: CancelAppointmentRequest, db=Depends(get_db)):
    request_date = parse_request_date(req.date)

    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)

    res = db.appointments.update_many(
        {
            "patient_name": req.patient_name,
            "start_time": {
                "$gte": to_utc_naive(start_dt),
                "$lte": to_utc_naive(end_dt),
            },
            "cancelled": False,
        },
        {"$set": {"cancelled": True}},
    )

    if res.modified_count == 0:
        raise HTTPException(status_code=404, detail="No appointments found for that name and date.")

    return {
        "success": True,
        "message": f"Cancelled {res.modified_count} appointment(s).",
    }


@app.get("/list_appointments/", response_model=List[AppointmentResponse])
def list_appointments(date: str = "today", db=Depends(get_db)):
    request_date = parse_request_date(date)

    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)

    cursor = db.appointments.find(
        {
            "cancelled": False,
            "start_time": {
                "$gte": to_utc_naive(start_dt),
                "$lte": to_utc_naive(end_dt),
            },
        }
    ).sort("start_time", 1)

    return [appointment_to_response(d) for d in cursor]

@app.get("/check_doctor_availability/")
def check_doctor_availability(
    date: str = "today",           
    specialty: Optional[str] = None,
    speciality: Optional[str] = None,
    doctor_name: Optional[str] = None,
    name: Optional[str] = None,
    db=Depends(get_db),
):
    resolved_date = parse_request_date(date)

    # FIX: log the resolved date so bugs in AI tool calls are immediately visible
    logger.info("check_doctor_availability: resolved date = %s (raw input = %r)", resolved_date.isoformat(), date)

    if isinstance(speciality, str) and speciality.strip():
        resolved_specialty = speciality.strip()
    elif isinstance(specialty, str) and specialty.strip():
        resolved_specialty = specialty.strip()
    else:
        resolved_specialty = None

    resolved_name = doctor_name or name

    query = {"available": True}

    if resolved_name:
        query["name"] = {"$regex": re.escape(resolved_name.strip()), "$options": "i"}

    if resolved_specialty:
        mapped = normalize_specialty(resolved_specialty)
        query["specialty"] = {"$regex": re.escape(mapped), "$options": "i"}

    doctors = [
        {"name": d.get("name"), "specialty": d.get("specialty"), "doctor_id": d.get("doctor_id")}
        for d in db.doctors.find(query)
    ]

    return {
        "date": resolved_date.isoformat(),
        "available_doctors": doctors,
    }