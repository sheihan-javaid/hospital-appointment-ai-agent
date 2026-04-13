from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
from typing import List
import datetime as dt
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
    start_time: dt.datetime

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
    date: str | dt.date


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


# Schedule
@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    now = dt.datetime.now(dt.timezone.utc)

    start_time = appointment.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=dt.timezone.utc)

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
    date = parse_request_date(request.date)
    start_dt = dt.datetime.combine(date, dt.time.min)
    end_dt = dt.datetime.combine(date, dt.time.max)

    # Get all doctors
    doctors = db.execute(select(Doctor)).scalars().all()

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
        if doctor.available:
            has_appointment = any(
                appt for appt in appointments if appt.reason == doctor.specialty
            )
            if not has_appointment:
                available_doctors.append(doctor)

    return {"available_doctors": [doctor.name for doctor in available_doctors]}