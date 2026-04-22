from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import datetime as dt
import logging
import os
import uuid

from pydantic import BaseModel, ConfigDict
from zoneinfo import ZoneInfo

from database import init_db, get_db, to_utc_naive
from services.time_parser import resolve_datetime, TimeParseError


# -------------------------
# CONFIG
# -------------------------
UTC = dt.timezone.utc
KOLKATA = ZoneInfo("Asia/Kolkata")

MIN_ADVANCE_MINUTES = int(os.environ.get("MIN_ADVANCE_MINUTES", "15"))
MAX_FUTURE_DAYS = int(os.environ.get("MAX_FUTURE_DAYS", "365"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Hospital Appointment API")


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
    start_time: str | dt.datetime


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_name: str
    reason: Optional[str]
    start_time: dt.datetime
    cancelled: bool
    created_at: dt.datetime


class CancelAppointmentRequest(BaseModel):
    patient_name: str
    date: str | dt.date


class CancelAppointmentResponse(BaseModel):
    success: bool
    message: str


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
# TIME PARSING (ONLY NLP HERE)
# -------------------------
def parse_start_time(value: str | dt.datetime) -> dt.datetime:
    now = kolkata_now()

    # already datetime
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = resolve_datetime(str(value), now)
        except TimeParseError:
            raise HTTPException(
                status_code=422,
                detail="Could not understand date/time. Try 'tomorrow 5 pm' or 'next Monday 10 am'"
            )

    parsed = normalize_to_ist(parsed)

    # -------------------------
    # VALIDATION LAYER
    # -------------------------
    if parsed <= now:
        raise HTTPException(
            status_code=400,
            detail="Start time must be in the future"
        )

    min_allowed = now + dt.timedelta(minutes=MIN_ADVANCE_MINUTES)
    max_allowed = now + dt.timedelta(days=MAX_FUTURE_DAYS)

    if parsed.date() == now.date() and parsed < min_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum {MIN_ADVANCE_MINUTES} minutes advance required"
        )

    if parsed > max_allowed:
        raise HTTPException(
            status_code=422,
            detail="Appointment too far in future"
        )

    return parsed


def parse_request_date(value: str | dt.date | dt.datetime | None) -> dt.date:
    now = kolkata_now()

    if value is None:
        return now.date()

    if isinstance(value, dt.datetime):
        return normalize_to_ist(value).date()

    if isinstance(value, dt.date):
        return value

    raw = str(value).strip().lower()

    if raw == "today":
        return now.date()

    if raw == "tomorrow":
        return (now + dt.timedelta(days=1)).date()

    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Date must be 'today', 'tomorrow', or YYYY-MM-DD"
        )


# -------------------------
# RESPONSE MAPPER
# -------------------------
def appointment_to_response(doc: dict) -> dict:
    return {
        "id": doc.get("appointment_id", str(doc["_id"])),
        "patient_name": doc["patient_name"],
        "reason": doc.get("reason"),
        "start_time": doc["start_time"].replace(tzinfo=UTC).astimezone(KOLKATA),
        "cancelled": doc.get("cancelled", False),
        "created_at": doc["created_at"].replace(tzinfo=UTC).astimezone(KOLKATA),
    }


# -------------------------
# ENDPOINTS
# -------------------------
@app.get("/now")
def now_endpoint():
    now = kolkata_now()
    return {
        "iso": now.isoformat(),
        "date": now.date().isoformat(),
        "time": now.strftime("%H:%M:%S"),
    }


@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appt: AppointmentRequest, db=Depends(get_db)):
    now = kolkata_now()

    start_time = parse_start_time(appt.start_time)

    appt_id = f"APPT-{uuid.uuid4().hex[:8].upper()}"

    doc = {
        "appointment_id": appt_id,
        "patient_name": appt.patient_name,
        "reason": appt.reason,
        "start_time": to_utc_naive(start_time),
        "cancelled": False,
        "created_at": to_utc_naive(now),
    }

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
        raise HTTPException(status_code=404, detail="No appointments found")

    return {
        "success": True,
        "message": f"Cancelled {res.modified_count} appointment(s)"
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
    date: Optional[str] = None,
    specialty: Optional[str] = None,
    speciality: Optional[str] = None,
    doctor_name: Optional[str] = None,
    name: Optional[str] = None,
    db=Depends(get_db),
):
    resolved_date = parse_request_date(date)

    resolved_specialty = specialty or speciality
    resolved_name = doctor_name or name

    query = {"available": True}

    if resolved_name:
        query["name"] = {"$regex": resolved_name.strip(), "$options": "i"}

    if resolved_specialty:
        query["specialty"] = {
            "$regex": resolved_specialty.strip(),
            "$options": "i"
        }

    doctors = [
        {"name": d["name"], "specialty": d["specialty"]}
        for d in db.doctors.find(query)
    ]

    return {
        "date": resolved_date.isoformat(),
        "available_doctors": doctors,
    }