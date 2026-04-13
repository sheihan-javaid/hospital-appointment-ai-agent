from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
from typing import List
import datetime as dt
import re
from pydantic import BaseModel, ConfigDict

from database import init_db, Appointment, Doctor, SessionLocal

# Initialize DB
init_db()

app = FastAPI()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
    date: str | dt.date | None = None
    specialty: str | None = None
    doctor_name: str | None = None


def parse_request_date(value: str | dt.date | dt.datetime) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()

    if isinstance(value, dt.date):
        return value

    normalized_value = value.strip().lower()
    today = dt.date.today()

    if normalized_value == "today":
        return today

    if normalized_value == "tomorrow":
        return today + dt.timedelta(days=1)

    try:
        return dt.datetime.strptime(normalized_value, "%d %m %Y").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Date must be 'today', 'tomorrow', or in dd mm yyyy format like 13 04 2026",
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
            parts = normalized.split(" ")
            if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
                date_text = " ".join(parts[:3])
                time_text = " ".join(parts[3:]) if len(parts) > 3 else "09:00"

                try:
                    parsed_date = dt.datetime.strptime(date_text, "%d %m %Y").date()
                    parsed_time = parse_time_component(time_text)
                    parsed = dt.datetime.combine(parsed_date, parsed_time)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Invalid start_time. Use ISO datetime, 'today/tomorrow at time', "
                            "or 'dd mm yyyy HH:MM' (optionally with am/pm)."
                        ),
                    ) from exc

        if parsed is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Invalid start_time. Use ISO datetime, 'today/tomorrow at time', "
                    "or 'dd mm yyyy HH:MM' (optionally with am/pm)."
                ),
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

    new_appointment_return_obj = AppointmentResponse(
        id=new_appointment.id,
        patient_name=new_appointment.patient_name,
        reason=new_appointment.reason,
        start_time=new_appointment.start_time,
        cancelled=new_appointment.cancelled,
        created_at=new_appointment.created_at
    )

    return new_appointment_return_obj

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

#check doctor availability
@app.post("/check_doctor_availability/")
def check_doctor_availability(request: CheckDoctorAvailabilityRequest, db=Depends(get_db)):
    date = parse_request_date(request.date or "today")
    start_dt = dt.datetime.combine(date, dt.time.min)
    end_dt = dt.datetime.combine(date, dt.time.max)

    doctors_query = select(Doctor).where(Doctor.available.is_(True))
    if request.doctor_name:
        doctors_query = doctors_query.where(Doctor.name.ilike(f"%{request.doctor_name.strip()}%"))
    if request.specialty:
        doctors_query = doctors_query.where(Doctor.specialty.ilike(f"%{request.specialty.strip()}%"))

    doctors = db.execute(doctors_query).scalars().all()

    # Get all appointments for the date
    appointments = db.execute(
        select(Appointment)
        .where(Appointment.cancelled.is_(False))
        .where(Appointment.start_time >= start_dt)
        .where(Appointment.start_time <= end_dt)
    ).scalars().all()

    # For simplicity, assume each doctor can only have one appointment per day
    available_doctors = []
    for doctor in doctors:
        has_appointment = any(
            appt for appt in appointments if appt.reason == doctor.specialty
        )
        if not has_appointment:
            available_doctors.append(doctor)

    available_doctor_names = [doctor.name for doctor in available_doctors]

    if not request.doctor_name and not request.specialty:
        return {
            "date": date.strftime("%d %m %Y"),
            "any_available_doctor": available_doctor_names[0] if available_doctor_names else None,
            "available_doctors": available_doctor_names,
        }

    return {
        "date": date.strftime("%d %m %Y"),
        "available_doctors": available_doctor_names,
    }