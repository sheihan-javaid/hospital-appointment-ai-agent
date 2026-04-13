from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
from typing import List
import datetime as dt
import re
from pydantic import BaseModel, ConfigDict

from database import init_db, Appointment, Doctor, get_db

DATE_INPUT_FORMAT = "%d-%m-%Y"
START_TIME_ERROR_DETAIL = (
    "Invalid start_time. Use ISO datetime, 'today/tomorrow at time', "
    "or 'dd-mm-yyyy HH:MM' (optionally with am/pm)."
)

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
init_db()
app = FastAPI()

class AppointmentRequest(BaseModel):
    patient_name: str
    reason: str
    start_time: str | dt.datetime


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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

def normalize_specialty_filter(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(
        r"\b(dr|doctor|doctors|any|available|availability|show|check|find|finds|list|please|the|a|an|today|tomorrow|tommorow|now|tonight|speciality|specialty)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_request_date(value: str | dt.date | dt.datetime | None) -> dt.date:
    if value is None:
        return dt.datetime.now(IST).date()

    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    normalized = value.strip().lower().replace("tommorow", "tomorrow")
    today = dt.datetime.now(IST).date()

    if normalized == "today":
        return today

    if normalized == "tomorrow":
        return today + dt.timedelta(days=1)

    try:
        return dt.datetime.strptime(normalized, DATE_INPUT_FORMAT).date()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Date must be 'today', 'tomorrow', or in dd-mm-yyyy format like 13-04-2026",
        ) from exc


def parse_time_component(value: str) -> dt.time:
    normalized = value.strip().lower().replace(".", "")
    normalized = re.sub(r"\s+", " ", normalized)

    am_pm_match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", normalized)
    if am_pm_match:
        hour = int(am_pm_match.group(1))
        minute = int(am_pm_match.group(2) or 0)
        meridiem = am_pm_match.group(3)

        if hour < 1 or hour > 12 or minute < 0 or minute > 59:
            raise ValueError("Invalid 12-hour time")

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

    raise ValueError("Unsupported time format")


def parse_start_time(value: str | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        raw = value.strip()
        normalized = re.sub(r"\s+", " ", raw.lower()).replace("tommorow", "tomorrow")
        parsed = None

        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass

        if parsed is None:
            rel = re.fullmatch(r"(today|tomorrow)(?:\s+at)?\s+(.+)", normalized)
            if rel:
                base = dt.datetime.now(IST).date() + (
                    dt.timedelta(days=1) if rel.group(1) == "tomorrow" else dt.timedelta()
                )
                try:
                    parsed = dt.datetime.combine(base, parse_time_component(rel.group(2)))
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail="Invalid time format. Try values like '2 pm', '2:30 pm', or '14:30'.",
                    ) from exc

        if parsed is None:
            m = re.fullmatch(r"(\d{2}-\d{2}-\d{4})(?:\s+(.+))?", normalized)
            if m:
                try:
                    parsed_date = dt.datetime.strptime(m.group(1), DATE_INPUT_FORMAT).date()
                    parsed_time = parse_time_component(m.group(2) or "09:00")
                    parsed = dt.datetime.combine(parsed_date, parsed_time)
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=START_TIME_ERROR_DETAIL) from exc

        if parsed is None:
            raise HTTPException(status_code=422, detail=START_TIME_ERROR_DETAIL)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(dt.timezone.utc)

@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    start_time = parse_start_time(appointment.start_time)

    if start_time.astimezone(IST) < dt.datetime.now(IST):
        raise HTTPException(status_code=400, detail="Start time must be later than current time")

    new_appointment = Appointment(
        patient_name=appointment.patient_name,
        reason=appointment.reason,
        start_time=start_time,
    )
    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)
    return new_appointment


@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(request: CancelAppointmentRequest, db=Depends(get_db)):
    request_date = parse_request_date(request.date)
    start_dt = dt.datetime.combine(request_date, dt.time.min)
    end_dt = dt.datetime.combine(request_date, dt.time.max)

    appointments = db.execute(
        select(Appointment)
        .where(Appointment.patient_name == request.patient_name)
        .where(Appointment.start_time >= start_dt)
        .where(Appointment.start_time <= end_dt)
        .where(Appointment.cancelled.is_(False))
    ).scalars().all()

    if not appointments:
        raise HTTPException(status_code=404, detail="No appointments found")

    for a in appointments:
        a.cancelled = True
    db.commit()

    return {"success": True, "message": f"Cancelled {len(appointments)} appointment(s)"}


@app.get("/list_appointments/", response_model=List[AppointmentResponse])
def list_appointments(date: str = "today", db=Depends(get_db)):
    request_date = parse_request_date(date)
    start_dt = dt.datetime.combine(request_date, dt.time.min)
    end_dt = dt.datetime.combine(request_date, dt.time.max)

    return db.execute(
        select(Appointment)
        .where(Appointment.cancelled.is_(False))
        .where(Appointment.start_time >= start_dt)
        .where(Appointment.start_time <= end_dt)
        .order_by(Appointment.start_time)
    ).scalars().all()


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

    doctors_query = select(Doctor).where(Doctor.available.is_(True))

    if resolved_name:
        doctors_query = doctors_query.where(
            Doctor.name.ilike(f"%{resolved_name.strip()}%")
        )

    if resolved_specialty:
        sf = normalize_specialty_filter(resolved_specialty)
        if sf:
            doctors_query = doctors_query.where(
                Doctor.specialty.ilike(f"%{sf}%")
            )

    doctors = db.execute(doctors_query).scalars().all()

    available_doctors = [
        {"name": d.name, "specialty": d.specialty} for d in doctors
    ]

    response = {
        "date": resolved_date.strftime(DATE_INPUT_FORMAT),
        "available_doctors": available_doctors,
    }

    if not resolved_name and not resolved_specialty:
        response["any_available_doctor"] = available_doctors[0] if available_doctors else None

    return response