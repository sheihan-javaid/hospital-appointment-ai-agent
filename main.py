from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
from typing import List
import datetime as dt
import re
from pydantic import BaseModel, ConfigDict, Field

from database import init_db, Appointment, Doctor, get_db

DATE_INPUT_FORMAT = "%d-%m-%Y"
START_TIME_ERROR_DETAIL = (
    "Invalid start_time. Use ISO datetime, 'today/tomorrow at time', "
    "or 'dd-mm-yyyy HH:MM' (optionally with am/pm)."
)

# Initialize DB
init_db()

app = FastAPI()

# Models
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

class CheckDoctorAvailabilityRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str | dt.date | None = None
    specialty: str | None = Field(default=None, alias="speciality")
    doctor_name: str | None = Field(default=None, alias="name")


def normalize_specialty_filter(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"\b(dr|doctor|doctors|speciality|specialty)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_request_date(value: str | dt.date | dt.datetime) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    normalized_value = value.strip().lower().replace("tommorow", "tomorrow")
    today = dt.date.today()

    if normalized_value == "today":
        return today

    if normalized_value == "tomorrow":
        return today + dt.timedelta(days=1)

    try:
        return dt.datetime.strptime(normalized_value, DATE_INPUT_FORMAT).date()
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
        normalized = re.sub(r"\s+", " ", raw.lower())
        normalized = normalized.replace("tommorow", "tomorrow")

        # Accept ISO datetime payloads first.
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None

        if parsed is None:
            relative_match = re.fullmatch(r"(today|tomorrow)(?:\s+at)?\s+(.+)", normalized)
            if relative_match:
                base_date = dt.date.today()
                if relative_match.group(1) == "tomorrow":
                    base_date += dt.timedelta(days=1)

                try:
                    parsed_time = parse_time_component(relative_match.group(2))
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail="Invalid time format. Try values like '2 pm', '2:30 pm', or '14:30'.",
                    ) from exc

                parsed = dt.datetime.combine(base_date, parsed_time)

        if parsed is None:
            # ✅ FIX: Updated to parse dd-mm-yyyy date format (dash-separated)
            # Matches: "13-04-2026 14:30" or "13-04-2026 2pm" etc.
            date_time_match = re.fullmatch(
                r"(\d{2}-\d{2}-\d{4})(?:\s+(.+))?", normalized
            )
            if date_time_match:
                date_text = date_time_match.group(1)
                time_text = date_time_match.group(2) or "09:00"

                try:
                    parsed_date = dt.datetime.strptime(date_text, "%d-%m-%Y").date()
                    parsed_time = parse_time_component(time_text)
                    parsed = dt.datetime.combine(parsed_date, parsed_time)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=START_TIME_ERROR_DETAIL,
                    ) from exc

        if parsed is None:
            raise HTTPException(
                status_code=422,
                detail=START_TIME_ERROR_DETAIL,
            )

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)

    return parsed.astimezone(dt.timezone.utc)


# Schedule
@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)
    start_time = parse_start_time(appointment.start_time)

    if start_time < now:
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

# Cancel
@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(request: CancelAppointmentRequest, db=Depends(get_db)):
    request_date = parse_request_date(request.date)
    start_dt = dt.datetime.combine(request_date, dt.time.min)
    end_dt = dt.datetime.combine(request_date, dt.time.max)

    results = db.execute(
        select(Appointment)
        .where(Appointment.patient_name == request.patient_name)
        .where(Appointment.start_time >= start_dt)
        .where(Appointment.start_time <= end_dt)
        .where(Appointment.cancelled.is_(False))
    )

    appointments = results.scalars().all()

    if not appointments:
        raise HTTPException(status_code=404, detail="No appointments found")

    for a in appointments:
        a.cancelled = True

    db.commit()

    return {
        "success": True,
        "message": f"Cancelled {len(appointments)} appointment(s)"
    }

# List
@app.get("/list_appointments/", response_model=List[AppointmentResponse])
def list_appointments(date: str, db=Depends(get_db)):
    request_date = parse_request_date(date)
    start_dt = dt.datetime.combine(request_date, dt.time.min)
    end_dt = dt.datetime.combine(request_date, dt.time.max)

    results = db.execute(
        select(Appointment)
        .where(Appointment.cancelled.is_(False))
        .where(Appointment.start_time >= start_dt)
        .where(Appointment.start_time <= end_dt)
        .order_by(Appointment.start_time)
    )

    return results.scalars().all()

def _build_doctor_availability_response(request: CheckDoctorAvailabilityRequest, db):
    date = parse_request_date(request.date or "today")

    # Build query for available doctors, optionally filtered by name and/or specialty
    doctors_query = select(Doctor).where(Doctor.available.is_(True))

    if request.doctor_name:
        doctor_name_filter = request.doctor_name.strip()
        doctors_query = doctors_query.where(Doctor.name.ilike(f"%{doctor_name_filter}%"))

    if request.specialty:
        specialty_filter = normalize_specialty_filter(request.specialty)
        if specialty_filter:
            doctors_query = doctors_query.where(Doctor.specialty.ilike(f"%{specialty_filter}%"))

    # ✅ FIX: Removed the broken appointment-conflict check that compared
    # appt.reason == doctor.specialty (an unreliable heuristic with no
    # doctor_id on Appointment).  The Doctor.available flag is the source
    # of truth for availability; all doctors passing the query above are
    # considered available on the requested date.
    doctors = db.execute(doctors_query).scalars().all()
    available_doctor_names = [doctor.name for doctor in doctors]

    if not request.doctor_name and not request.specialty:
        return {
            "date": date.strftime(DATE_INPUT_FORMAT),
            "any_available_doctor": available_doctor_names[0] if available_doctor_names else None,
            "available_doctors": available_doctor_names,
        }

    return {
        "date": date.strftime(DATE_INPUT_FORMAT),
        "available_doctors": available_doctor_names,
    }


# Check doctor availability
@app.post("/check_doctor_availability/")
def check_doctor_availability(request: CheckDoctorAvailabilityRequest, db=Depends(get_db)):
    return _build_doctor_availability_response(request, db)


@app.get("/check_doctor_availability/")
def check_doctor_availability_get(
    date: str | None = None,
    specialty: str | None = None,
    speciality: str | None = None,
    doctor_name: str | None = None,
    name: str | None = None,
    db=Depends(get_db),
):
    resolved_specialty = specialty or speciality
    resolved_doctor_name = doctor_name or name

    request = CheckDoctorAvailabilityRequest(
        date=date,
        specialty=resolved_specialty,
        doctor_name=resolved_doctor_name,
    )
    return _build_doctor_availability_response(request, db)