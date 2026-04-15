from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import datetime as dt
import re
import logging
import os

from pydantic import BaseModel, ConfigDict
from zoneinfo import ZoneInfo

from database import init_db, get_db, to_utc_naive


# ---- Configuration ----
DATE_INPUT_FORMAT = "%d-%m-%Y"
UTC = dt.timezone.utc
MIN_ADVANCE_MINUTES = int(os.environ.get("MIN_ADVANCE_MINUTES", "15"))
MAX_FUTURE_DAYS = int(os.environ.get("MAX_FUTURE_DAYS", "365"))


# ---- Logging ----
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


# ---- Timezone helpers ----
def _get_kolkata_tz() -> dt.tzinfo:
    """Return a tzinfo for Asia/Kolkata, fallback to fixed offset if ZoneInfo unavailable."""
    try:
        return ZoneInfo("Asia/Kolkata")
    except Exception:
        # fallback to fixed +05:30
        return dt.timezone(dt.timedelta(hours=5, minutes=30))


KOLKATA = _get_kolkata_tz()


def kolkata_now() -> dt.datetime:
    return dt.datetime.now(KOLKATA)


# ---- App init ----
app = FastAPI(title="Hospital Appointment API")

# CORS (configure with CORS_ORIGINS env var if needed)
cors_origins = os.environ.get("CORS_ORIGINS")
if cors_origins:
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def startup():
    try:
        init_db()
        logger.info("Database initialized on startup")
    except Exception:
        logger.exception("Database initialization failed on startup")


# ---- Models ----
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


# ---- Parsing helpers ----
def _parse_time_component(value: str) -> dt.time:
    v = value.strip().lower().replace(".", "")
    v = re.sub(r"\s+", " ", v)

    # 12-hour
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", v)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        ampm = m.group(3)
        if not (1 <= h <= 12 and 0 <= mi <= 59):
            raise ValueError("invalid 12-hour time")
        if ampm == "pm" and h != 12:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
        return dt.time(hour=h, minute=mi)

    # 24-hour
    for fmt in ("%H:%M", "%H"):
        try:
            return dt.datetime.strptime(v, fmt).time()
        except ValueError:
            continue

    raise ValueError("unsupported time format")


def _parse_iso(s: str) -> Optional[dt.datetime]:
    s = s.strip()
    if not s:
        return None
    # try python's fromisoformat (handles +HH:MM); accept trailing Z
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None


def parse_request_date(value: str | dt.date | dt.datetime | None) -> dt.date:
    if value is None:
        return kolkata_now().date()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    s = str(value).strip().lower().replace("tommorow", "tomorrow")
    today = kolkata_now().date()
    if s == "today":
        return today
    if s == "tomorrow":
        return today + dt.timedelta(days=1)
    try:
        return dt.datetime.strptime(s, DATE_INPUT_FORMAT).date()
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Date must be today/tomorrow or dd-mm-yyyy")


def normalize_specialty_filter(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(
        r"\b(dr|doctor|doctors|any|available|availability|show|check|find|list|please|the|a|an|today|tomorrow|now|tonight|speciality|specialty)\b",
        " ",
        cleaned,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_start_time(value: str | dt.datetime) -> dt.datetime:
    now = kolkata_now()

    if isinstance(value, dt.datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            raise HTTPException(status_code=422, detail="start_time required")

        # try ISO
        parsed = _parse_iso(raw)

        # try relative today/tomorrow
        if parsed is None:
            norm = re.sub(r"\s+", " ", raw.lower()).replace("tommorow", "tomorrow")
            rel = re.fullmatch(r"(today|tomorrow)(?:\s+at)?\s+(.+)", norm)
            if rel:
                base = now.date() + (dt.timedelta(days=1) if rel.group(1) == "tomorrow" else dt.timedelta())
                try:
                    t = _parse_time_component(rel.group(2))
                    parsed = dt.datetime.combine(base, t)
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))

        # try dd-mm-yyyy
        if parsed is None:
            m = re.fullmatch(r"(\d{2}-\d{2}-\d{4})(?:\s+(.+))?", raw)
            if m:
                try:
                    d = dt.datetime.strptime(m.group(1), DATE_INPUT_FORMAT).date()
                    t = _parse_time_component(m.group(2) or "09:00")
                    parsed = dt.datetime.combine(d, t)
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))

        if parsed is None:
            raise HTTPException(status_code=422, detail="Invalid start_time format")

    # ensure timezone aware in KOLKATA
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KOLKATA)
    else:
        parsed = parsed.astimezone(KOLKATA)

    # Validate reasonable range
    if parsed.year < (now.year - 1) or parsed.year > (now.year + 2):
        raise HTTPException(status_code=422, detail="start_time year looks incorrect")

    # Enforce minimum advance
    min_allowed = now + dt.timedelta(minutes=MIN_ADVANCE_MINUTES)
    max_allowed = now + dt.timedelta(days=MAX_FUTURE_DAYS)
    if parsed < min_allowed:
        raise HTTPException(status_code=400, detail=f"Appointments must be at least {MIN_ADVANCE_MINUTES} minutes in the future")
    if parsed > max_allowed:
        raise HTTPException(status_code=422, detail=f"Appointments cannot be more than {MAX_FUTURE_DAYS} days in advance")

    return parsed


def appointment_to_response(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "patient_name": doc["patient_name"],
        "reason": doc.get("reason"),
        "start_time": doc["start_time"].replace(tzinfo=UTC).astimezone(KOLKATA),
        "cancelled": doc.get("cancelled", False),
        "created_at": doc["created_at"].replace(tzinfo=UTC).astimezone(KOLKATA),
    }


# ---- Endpoints ----
@app.get("/now")
def now_endpoint():
    now = kolkata_now()
    return {"iso": now.isoformat(), "date": now.strftime("%d-%m-%Y"), "time": now.strftime("%H:%M:%S %Z")}


@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appt: AppointmentRequest, db=Depends(get_db)):
    logger.info("Received schedule request for %s", appt.patient_name)
    start_time = parse_start_time(appt.start_time)
    now = kolkata_now()

    # Double-check
    if start_time <= now:
        raise HTTPException(status_code=400, detail="Start time must be later than current time")

    doc = {
        "patient_name": appt.patient_name,
        "reason": appt.reason,
        "start_time": to_utc_naive(start_time),
        "cancelled": False,
        "created_at": to_utc_naive(now),
    }

    res = db.appointments.insert_one(doc)
    inserted = db.appointments.find_one({"_id": res.inserted_id})
    return appointment_to_response(inserted)


@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(req: CancelAppointmentRequest, db=Depends(get_db)):
    request_date = parse_request_date(req.date)
    start_dt = dt.datetime.combine(request_date, dt.time.min, tzinfo=KOLKATA)
    end_dt = dt.datetime.combine(request_date, dt.time.max, tzinfo=KOLKATA)

    start_q = to_utc_naive(start_dt)
    end_q = to_utc_naive(end_dt)

    res = db.appointments.update_many({
        "patient_name": req.patient_name,
        "start_time": {"$gte": start_q, "$lte": end_q},
        "cancelled": False,
    }, {"$set": {"cancelled": True}})

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
    return [appointment_to_response(d) for d in cursor]


@app.get("/check_doctor_availability/")
def check_doctor_availability(date: Optional[str] = None, specialty: Optional[str] = None, speciality: Optional[str] = None, doctor_name: Optional[str] = None, name: Optional[str] = None, db=Depends(get_db)):
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
    doctors = [{"name": d["name"], "specialty": d["specialty"]} for d in cursor]
    return {"date": resolved_date.strftime(DATE_INPUT_FORMAT), "available_doctors": doctors}
