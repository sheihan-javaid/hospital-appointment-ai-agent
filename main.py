from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
from typing import List
import datetime as dt
from pydantic import BaseModel

from database import init_db, Appointment, SessionLocal

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
    id: int
    patient_name: str
    reason: str | None
    start_time: dt.datetime
    cancelled: bool
    created_at: dt.datetime

class CancelAppointmentRequest(BaseModel):
    patient_name: str
    date: dt.date

class CancelAppointmentResponse(BaseModel):
    success: bool
    message: str

# Schedule
@app.post("/schedule_appointment/", response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    new_appointment = Appointment(
        patient_name=appointment.patient_name,
        reason=appointment.reason,
        start_time=appointment.start_time,
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    return new_appointment

# Cancel
@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
def cancel_appointment(request: CancelAppointmentRequest, db=Depends(get_db)):
    start_dt = dt.datetime.combine(request.date, dt.time.min)
    end_dt = dt.datetime.combine(request.date, dt.time.max)

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
def list_appointments(date: dt.date, db=Depends(get_db)):
    start_dt = dt.datetime.combine(date, dt.time.min)
    end_dt = dt.datetime.combine(date, dt.time.max)

    results = db.execute(
        select(Appointment)
        .where(Appointment.cancelled.is_(False))
        .where(Appointment.start_time >= start_dt)
        .where(Appointment.start_time <= end_dt)
        .order_by(Appointment.start_time)
    )

    return results.scalars().all()