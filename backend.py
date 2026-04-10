# Step1: Import Database Objects
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import select
import uvicorn
from typing import List

from database import init_db, Appointment, SessionLocal
import datetime as dt
from pydantic import BaseModel

init_db()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Step2: Create Data Contracts using Pydantic models
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

# Step3: Create FastAPI app and define endpoints
app = FastAPI()

# schedule appointment endpoint
@app.post("/schedule_appointment/", response_model=AppointmentResponse)
@app.post("/schedule_appointments/", include_in_schema=False, response_model=AppointmentResponse)
def schedule_appointment(appointment: AppointmentRequest, db=Depends(get_db)):
    new_appointment = Appointment(
        patient_name=appointment.patient_name,
        reason=appointment.reason,
        start_time=appointment.start_time,
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    return AppointmentResponse(
        id=new_appointment.id,
        patient_name=new_appointment.patient_name,
        reason=new_appointment.reason,
        start_time=new_appointment.start_time,
        cancelled=new_appointment.cancelled,
        created_at=new_appointment.created_at
    )

# cancel appointment endpoint
@app.post("/cancel_appointment/", response_model=CancelAppointmentResponse)
@app.post("/cancel_appointments/", include_in_schema=False, response_model=CancelAppointmentResponse)
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
        raise HTTPException(
            status_code=404,
            detail="No appointments found for the given patient and date."
        )

    for appointment in appointments:
        appointment.cancelled = True

    db.commit()

    return CancelAppointmentResponse(
        success=True,
        message=f"Cancelled {len(appointments)} appointment(s) for patient {request.patient_name} on {request.date}."
    )

# list appointments endpoint
@app.get("/list_appointment/", response_model=List[AppointmentResponse])
@app.get("/list_appointments/", include_in_schema=False, response_model=List[AppointmentResponse])
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

    appointments = results.scalars().all()

    booked_appointments = []
    for appointment in appointments:
        appointment_obj = AppointmentResponse(
            id=appointment.id,
            patient_name=appointment.patient_name,
            reason=appointment.reason,
            start_time=appointment.start_time,
            cancelled=appointment.cancelled,
            created_at=appointment.created_at
        )
        booked_appointments.append(appointment_obj)

    return booked_appointments

if __name__ == "__main__":
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)